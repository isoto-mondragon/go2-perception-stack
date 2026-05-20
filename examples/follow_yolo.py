#!/usr/bin/env python3
"""Sigue a un objeto detectado por YOLOv8 usando la webcam.

Arquitectura con threads:
  - Hilo 'capture+yolo': lee camara y corre YOLO continuamente. Publica la
    ultima (frame, deteccion).
  - Hilo principal: a 20Hz lee la ultima (frame, deteccion), envia comando
    al perro y refresca la ventana de OpenCV.

Asi la ventana sigue fluida aunque YOLO en CPU tarde 200-500ms por frame.

El mismo script vale para SIM y REAL: cambias mode y network.

Setup:
  pip install ultralytics opencv-python

Uso:
  1. Arranca el simulador (en SIM):
       python tools/play_dds.py Unitree-Go2-Flat \
         --checkpoint-file=<ruta a model.pt> --network=lo
  2. En otra terminal:
       python examples/follow_yolo.py
"""

import sys
import threading
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.go2_controller import Go2Controller

try:
    from ultralytics import YOLO
except ImportError:
    raise SystemExit(
        "Falta ultralytics. Instala con:  pip install ultralytics opencv-python"
    )


# ============================================================
# Config
# ============================================================
MODE = "sim"             # "sim" o "real"
NETWORK = "lo"           # "lo" para sim, "enp5s0" (o tu interfaz) para real

TARGET_CLASS = "person"
CAMERA_INDEX = 0

# Parametros de control
MAX_VX = 0.5
MAX_WZ = 0.8
DEAD_ZONE_PX = 50
TARGET_BBOX_H_PX = 400   # sube si la persona sale grande en tu camara
KP_YAW = 1.5
KP_FORWARD = 1.0
CONTROL_RATE_HZ = 20
YOLO_IMGSZ = 192         # tamano de inferencia (mas pequeno -> mas rapido en CPU)
YOLO_CONF = 0.55         # confianza minima YOLO (sube si hay muchos falsos positivos)
MAX_BBOX_AREA_FRAC = 0.85  # ignora detecciones que cubran > 85% del frame
MIN_BBOX_AREA_FRAC = 0.01  # ignora detecciones diminutas (ruido)
STALE_FRAME_TIMEOUT_S = 1.0  # si no llega frame nuevo en este tiempo -> stop al perro
MAX_READ_FAILS = 30      # tras tantos fallos consecutivos de cap.read -> intenta reopen


# ============================================================
# Hilo de fondo: captura + YOLO
# ============================================================
class CaptureYoloThread(threading.Thread):
    """Lee la camara y corre YOLO continuamente.

    Robusto a fallos de la camara:
      - Si cap.read() falla varias veces seguidas, intenta reabrir el device.
      - Timestamp del ultimo frame leido (para detectar 'cuelgues' desde fuera).
    """

    def __init__(self, cap, cap_index, yolo, target_class_id):
        super().__init__(daemon=True)
        self.cap = cap
        self.cap_index = cap_index    # para poder reabrir
        self.yolo = yolo
        self.target_class_id = target_class_id
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_detection = None
        self._latest_ts = 0.0
        self._yolo_fps_smoothed = 0.0
        self._read_fails = 0
        self._frame_count = 0

    def _reopen_camera(self):
        """Intenta reabrir el device de la camara."""
        try:
            self.cap.release()
        except Exception:
            pass
        time.sleep(0.5)
        cap = cv2.VideoCapture(self.cap_index, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            self.cap = cap
            print("\n[capture] camara reabierta OK", flush=True)
            return True
        print("\n[capture] no se pudo reabrir la camara", flush=True)
        return False

    def run(self):
        t_last = time.monotonic()
        self._frame_count = 0
        try:
            while not self.stop_event.is_set():
                try:
                    ok, frame = self.cap.read()
                except Exception as e:
                    print(f"\n[capture] cap.read() raised: {e}", flush=True)
                    self._read_fails += 1
                    if self._read_fails >= MAX_READ_FAILS:
                        self._read_fails = 0
                        self._reopen_camera()
                    time.sleep(0.05)
                    continue

                if not ok:
                    self._read_fails += 1
                    if self._read_fails >= MAX_READ_FAILS:
                        print(f"\n[capture] {self._read_fails} lecturas fallidas, reabriendo camara", flush=True)
                        self._read_fails = 0
                        self._reopen_camera()
                    else:
                        time.sleep(0.01)
                    continue

                self._read_fails = 0

                try:
                    results = self.yolo.predict(frame, verbose=False, imgsz=YOLO_IMGSZ, conf=YOLO_CONF)
                    detection = self._find_best_detection(results, frame.shape[0] * frame.shape[1])
                except Exception as e:
                    print(f"\n[capture] yolo.predict raised: {e}", flush=True)
                    continue

                now = time.monotonic()
                dt = now - t_last
                t_last = now
                fps = 1.0 / max(dt, 1e-3)
                self._yolo_fps_smoothed = 0.9 * self._yolo_fps_smoothed + 0.1 * fps

                with self._lock:
                    self._latest_frame = frame
                    self._latest_detection = detection
                    self._latest_ts = now
                    self._frame_count += 1
        except Exception as e:
            print(f"\n[capture] thread DIED with: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def latest(self):
        with self._lock:
            return (
                self._latest_frame,
                self._latest_detection,
                self._yolo_fps_smoothed,
                self._latest_ts,
                self._frame_count,
            )

    def _find_best_detection(self, results, frame_area):
        """Devuelve el bbox mas grande de la clase objetivo, filtrando absurdos.

        Ignora bboxes que cubran > MAX_BBOX_AREA_FRAC del frame (suelen ser
        falsos positivos cuando algo tapa la camara) o < MIN_BBOX_AREA_FRAC
        (ruido / cosas demasiado pequenas para seguir).
        """
        if not results:
            return None
        boxes = results[0].boxes
        if boxes is None:
            return None
        max_area = frame_area * MAX_BBOX_AREA_FRAC
        min_area = frame_area * MIN_BBOX_AREA_FRAC
        best = None
        best_area = 0.0
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            if cls_id != self.target_class_id:
                continue
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            area = (x2 - x1) * (y2 - y1)
            if area > max_area or area < min_area:
                continue  # falso positivo demasiado grande o pequeno
            if area > best_area:
                best_area = area
                best = (x1, y1, x2, y2)
        return best


# ============================================================
# Logica de control
# ============================================================
def compute_command(detection, frame_w, frame_h):
    """Convierte (bbox o None) en (vx, vy, wz)."""
    if detection is None:
        return 0.0, 0.0, 0.0

    x1, y1, x2, y2 = detection
    cx = (x1 + x2) / 2.0
    bbox_h = y2 - y1

    err_x = (cx - frame_w / 2.0) / (frame_w / 2.0)

    if abs(cx - frame_w / 2.0) < DEAD_ZONE_PX:
        wz = 0.0
    else:
        wz = -KP_YAW * err_x
        wz = max(-MAX_WZ, min(MAX_WZ, wz))

    err_dist = (TARGET_BBOX_H_PX - bbox_h) / TARGET_BBOX_H_PX
    if err_dist > 0.1:
        vx = KP_FORWARD * err_dist
        vx = max(0.0, min(MAX_VX, vx))
    elif err_dist < -0.1:
        vx = KP_FORWARD * err_dist
        vx = max(-MAX_VX, min(0.0, vx))
    else:
        vx = 0.0

    return vx, 0.0, wz


# ============================================================
# Main
# ============================================================
def main():
    print(f"Modo: {MODE} | Network: {NETWORK} | Target: {TARGET_CLASS}")

    print("Cargando YOLOv8n...")
    yolo = YOLO("yolov8n.pt")
    target_class_id = None
    for cid, name in yolo.names.items():
        if name == TARGET_CLASS:
            target_class_id = cid
            break
    if target_class_id is None:
        raise SystemExit(f"Clase '{TARGET_CLASS}' no existe en COCO")
    print(f"YOLO listo. target_class_id={target_class_id}")

    # Camara con backend V4L2 + MJPG (necesario en WSL2 + usbipd)
    if isinstance(CAMERA_INDEX, int):
        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
    else:
        cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir la camara {CAMERA_INDEX}")

    ok, _ = cap.read()
    if not ok:
        raise SystemExit(f"Camara {CAMERA_INDEX} abierta pero no entrega frames")

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camara: {frame_w}x{frame_h}")

    # Perro
    dog = Go2Controller(mode=MODE, network=NETWORK)
    dog.stand_up()
    time.sleep(1.0)

    # Reducir buffer V4L2 para no acumular frames viejos
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    # Arranca hilo de captura+YOLO en background
    worker = CaptureYoloThread(cap, CAMERA_INDEX, yolo, target_class_id)
    worker.start()

    # Espera a que llegue la primera deteccion (o timeout)
    print("Esperando primer frame procesado por YOLO...")
    t0 = time.monotonic()
    while time.monotonic() - t0 < 10.0:
        frame, _, _, _, _ = worker.latest()
        if frame is not None:
            break
        time.sleep(0.1)
    if worker.latest()[0] is None:
        worker.stop_event.set()
        worker.join()
        cap.release()
        raise SystemExit("Timeout esperando frame de YOLO.")

    print("Loop principal a 20Hz. Pulsa 'q' en la ventana para salir.")

    period = 1.0 / CONTROL_RATE_HZ
    last_cmd = (0.0, 0.0, 0.0)
    stale_warning_shown = False

    last_frame_count = 0
    last_progress_t = time.monotonic()

    try:
        while True:
            t_loop = time.monotonic()

            frame, detection, yolo_fps, frame_ts, frame_count = worker.latest()
            if frame is None:
                time.sleep(period)
                continue

            age = time.monotonic() - frame_ts

            # Diagnostico real: el thread esta produciendo nuevos frames?
            if frame_count > last_frame_count:
                last_frame_count = frame_count
                last_progress_t = time.monotonic()

            seconds_without_progress = time.monotonic() - last_progress_t
            is_stale = seconds_without_progress > STALE_FRAME_TIMEOUT_S

            if is_stale:
                if not stale_warning_shown:
                    print(f"\n[main] Thread de captura sin progreso desde hace {seconds_without_progress:.1f}s. Parando perro.", flush=True)
                    print(f"       frame_count={frame_count}, thread.is_alive()={worker.is_alive()}", flush=True)
                    stale_warning_shown = True
                dog.set_velocity(0.0, 0.0, 0.0)
                last_cmd = (0.0, 0.0, 0.0)
                vx = vy = wz = 0.0
            else:
                if stale_warning_shown:
                    print("\n[main] Frames frescos de nuevo, reanudando control.", flush=True)
                    stale_warning_shown = False
                vx, vy, wz = compute_command(detection, frame_w, frame_h)
                if (abs(vx - last_cmd[0]) > 0.01 or
                    abs(vy - last_cmd[1]) > 0.01 or
                    abs(wz - last_cmd[2]) > 0.01):
                    dog.set_velocity(vx, vy, wz)
                    last_cmd = (vx, vy, wz)

            # Display
            disp = frame.copy()
            if detection is not None and not is_stale:
                x1, y1, x2, y2 = [int(v) for v in detection]
                cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(disp, TARGET_CLASS, (x1, max(y1 - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(disp, f"vx={vx:+.2f}  wz={wz:+.2f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(disp, f"YOLO: {yolo_fps:.1f} fps  frames={frame_count}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            if is_stale:
                cv2.putText(disp, f"!! NO PROGRESS ({seconds_without_progress:.1f}s) !!", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("follow_yolo", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed = time.monotonic() - t_loop
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        worker.stop_event.set()
        worker.join(timeout=2.0)
        dog.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
