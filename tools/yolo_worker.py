"""Hilo de fondo reutilizable para captura webcam + inferencia YOLO.

Pensado para usar con webcam en WSL2 sobre USB/IP (con sus quirks):
  - Backend V4L2 + MJPG explicito.
  - Buffer V4L2 reducido a 1.
  - Reintenta abrir el device si falla repetidamente.
  - Timestamp monotonico (no se ve afectado por suspend/resume de Windows).
  - Contador de frames para detectar 'cuelgues' del thread.

Uso tipico (ver examples/patrol_and_alert.py, fetch_object.py, guard_mode.py):

    from tools.yolo_worker import YoloCaptureThread, open_camera, get_class_id

    cap = open_camera(0, width=640, height=480)
    yolo = YOLO("yolov8n.pt")
    target_id = get_class_id(yolo, "person")

    worker = YoloCaptureThread(cap, 0, yolo, target_id)
    worker.start()
    # ...
    frame, detection, fps, ts, count = worker.latest()
    # ...
    worker.stop_event.set()
    worker.join()
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2


# Defaults globales (puedes sobreescribirlos desde el cliente)
YOLO_IMGSZ = 192
YOLO_CONF = 0.55
MAX_BBOX_AREA_FRAC = 0.85
MIN_BBOX_AREA_FRAC = 0.01
MAX_READ_FAILS = 30


def open_camera(index: int, width: int = 640, height: int = 480, fps: int = 30):
    """Abre la camara con backend V4L2 + MJPG (lo que funciona en WSL2)."""
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    ok, _ = cap.read()
    if not ok:
        cap.release()
        return None
    return cap


def get_class_id(yolo, class_name: str) -> Optional[int]:
    """Devuelve el id COCO para 'person', 'bottle', etc."""
    for cid, name in yolo.names.items():
        if name == class_name:
            return cid
    return None


def list_class_names(yolo) -> list[str]:
    """Lista todas las clases COCO disponibles."""
    return sorted(yolo.names.values())


class YoloCaptureThread(threading.Thread):
    """Hilo de fondo: lee webcam + corre YOLO + publica (frame, [detecciones], fps).

    A diferencia de follow_yolo.py original (que devuelve la deteccion mas
    grande), aqui devolvemos TODAS las detecciones del target_class para que
    el cliente decida (filtrado, lock-on, multiples objetivos, etc.).
    """

    def __init__(self, cap, cap_index: int, yolo, target_class_id: int,
                 imgsz: int = YOLO_IMGSZ, conf: float = YOLO_CONF):
        super().__init__(daemon=True)
        self.cap = cap
        self.cap_index = cap_index
        self.yolo = yolo
        self.target_class_id = target_class_id
        self.imgsz = imgsz
        self.conf = conf

        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_detections: list[Tuple[float, float, float, float, float]] = []
        # cada deteccion: (x1, y1, x2, y2, confidence)
        self._latest_ts = 0.0
        self._yolo_fps_smoothed = 0.0
        self._read_fails = 0
        self._frame_count = 0

    def _reopen_camera(self) -> bool:
        try:
            self.cap.release()
        except Exception:
            pass
        time.sleep(0.5)
        cap = open_camera(self.cap_index)
        if cap is None:
            print("[yolo_worker] no se pudo reabrir la camara", flush=True)
            return False
        self.cap = cap
        print("[yolo_worker] camara reabierta OK", flush=True)
        return True

    def run(self):
        t_last = time.monotonic()
        try:
            while not self.stop_event.is_set():
                try:
                    ok, frame = self.cap.read()
                except Exception as e:
                    print(f"[yolo_worker] cap.read() raised: {e}", flush=True)
                    ok = False

                if not ok:
                    self._read_fails += 1
                    if self._read_fails >= MAX_READ_FAILS:
                        self._read_fails = 0
                        self._reopen_camera()
                    else:
                        time.sleep(0.01)
                    continue

                self._read_fails = 0

                try:
                    results = self.yolo.predict(frame, verbose=False,
                                                imgsz=self.imgsz, conf=self.conf)
                except Exception as e:
                    print(f"[yolo_worker] yolo.predict raised: {e}", flush=True)
                    continue

                detections = self._extract_detections(results, frame.shape[0] * frame.shape[1])

                now = time.monotonic()
                dt = now - t_last
                t_last = now
                fps = 1.0 / max(dt, 1e-3)
                self._yolo_fps_smoothed = 0.9 * self._yolo_fps_smoothed + 0.1 * fps

                with self._lock:
                    self._latest_frame = frame
                    self._latest_detections = detections
                    self._latest_ts = now
                    self._frame_count += 1
        except Exception as e:
            import traceback
            print(f"[yolo_worker] thread DIED: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    def _extract_detections(self, results, frame_area):
        """Devuelve lista de (x1, y1, x2, y2, conf) del target_class, filtradas."""
        out = []
        if not results:
            return out
        boxes = results[0].boxes
        if boxes is None:
            return out
        max_area = frame_area * MAX_BBOX_AREA_FRAC
        min_area = frame_area * MIN_BBOX_AREA_FRAC
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            if cls_id != self.target_class_id:
                continue
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            area = (x2 - x1) * (y2 - y1)
            if area > max_area or area < min_area:
                continue
            confidence = float(boxes.conf[i].item())
            out.append((x1, y1, x2, y2, confidence))
        return out

    def latest(self):
        """Devuelve (frame, detections, yolo_fps, ts, frame_count)."""
        with self._lock:
            return (
                self._latest_frame,
                list(self._latest_detections),
                self._yolo_fps_smoothed,
                self._latest_ts,
                self._frame_count,
            )
