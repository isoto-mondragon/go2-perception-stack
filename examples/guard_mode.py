#!/usr/bin/env python3
"""Demo: centinela. El perro se queda en sitio y SOLO gira para seguirte.

Comportamiento:
  - No avanza ni retrocede NUNCA (vx = 0 siempre, vy = 0 siempre).
  - Solo emite wz para mantener al TARGET centrado en el frame.
  - Si hay varias personas, sigue a la mas grande (mas cercana visualmente).
  - Si nadie, espera quieto.

Concepto pedagogico: control puramente reactivo de 1 grado de libertad (yaw).
Util para entender el "lazo P" mas simple: error_horizontal -> wz.

Tambien sirve como base para "robot torreta" o "robot recepcionista".
"""

import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.go2_controller import Go2Controller
from tools.yolo_worker import YoloCaptureThread, open_camera, get_class_id

try:
    from ultralytics import YOLO
except ImportError:
    raise SystemExit("pip install ultralytics opencv-python")


# ============================================================
# Config
# ============================================================
MODE = "sim"
NETWORK = "lo"

TARGET_CLASS = "person"
CAMERA_INDEX = 0

# Lazo de yaw
KP_YAW = 1.4              # ganancia proporcional
MAX_WZ = 0.9              # rad/s maximo
DEAD_ZONE_PX = 25         # error horizontal en pixels para "centrado"
CONTROL_RATE_HZ = 20


def biggest_detection(detections):
    if not detections:
        return None
    return max(detections, key=lambda d: (d[2] - d[0]) * (d[3] - d[1]))


def main():
    print(f"[guard] modo={MODE} | target={TARGET_CLASS}")

    print("Cargando YOLOv8n...")
    yolo = YOLO("yolov8n.pt")
    target_id = get_class_id(yolo, TARGET_CLASS)
    if target_id is None:
        raise SystemExit(f"Clase '{TARGET_CLASS}' no existe en COCO")

    cap = open_camera(CAMERA_INDEX)
    if cap is None:
        raise SystemExit("No se pudo abrir la camara")
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    dog = Go2Controller(mode=MODE, network=NETWORK)
    dog.stand_up()
    time.sleep(1.0)

    worker = YoloCaptureThread(cap, CAMERA_INDEX, yolo, target_id)
    worker.start()
    print("Esperando primer frame...")
    while worker.latest()[0] is None:
        time.sleep(0.1)

    period = 1.0 / CONTROL_RATE_HZ
    print("[guard] Centinela activo. Pulsa 'q' en la ventana para salir.")

    try:
        while True:
            t_loop = time.monotonic()
            frame, detections, fps, _, _ = worker.latest()
            if frame is None:
                time.sleep(period)
                continue

            target = biggest_detection(detections)

            if target is None:
                wz = 0.0
                err_x_px = 0.0
            else:
                x1, y1, x2, y2, _conf = target
                cx = (x1 + x2) / 2.0
                err_x_px = cx - frame_w / 2.0
                if abs(err_x_px) < DEAD_ZONE_PX:
                    wz = 0.0
                else:
                    err_x_norm = err_x_px / (frame_w / 2.0)
                    wz = -KP_YAW * err_x_norm
                    wz = max(-MAX_WZ, min(MAX_WZ, wz))

            dog.set_velocity(vx=0.0, vy=0.0, wz=wz)

            # --- Display ---
            disp = frame.copy()

            # Bbox del target (verde fijo, sin parpadeo de color)
            if target is not None:
                x1, y1, x2, y2, conf = target
                cv2.rectangle(disp, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(disp, f"{TARGET_CLASS} {conf:.2f}", (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Banda central que marca la "deadzone": si el target esta DENTRO -> wz=0
            cx_frame = frame_w // 2
            cv2.rectangle(disp,
                          (cx_frame - DEAD_ZONE_PX, 0),
                          (cx_frame + DEAD_ZONE_PX, frame_h),
                          (50, 50, 50), 1)
            cv2.line(disp, (cx_frame, 0), (cx_frame, frame_h), (100, 100, 100), 1)

            # Barra horizontal indicadora del error y de la accion del lazo de control.
            # Centrada en cx_frame. La aguja se desplaza con la posicion del target.
            bar_y = frame_h - 35
            bar_h = 14
            bar_w = frame_w - 40
            bar_x0 = 20
            cv2.rectangle(disp, (bar_x0, bar_y), (bar_x0 + bar_w, bar_y + bar_h),
                          (60, 60, 60), -1)
            cv2.line(disp, (bar_x0 + bar_w // 2, bar_y),
                     (bar_x0 + bar_w // 2, bar_y + bar_h), (180, 180, 180), 1)
            if target is not None:
                # Color de la aguja: verde si dentro de deadzone, naranja/rojo si lejos.
                if abs(err_x_px) < DEAD_ZONE_PX:
                    needle_color = (0, 255, 0)
                    state_label = "CENTERED"
                elif abs(err_x_px) < frame_w * 0.25:
                    needle_color = (0, 165, 255)
                    state_label = "TRACKING"
                else:
                    needle_color = (0, 80, 255)
                    state_label = "CORRECTING"
                # Posicion proporcional al error normalizado.
                err_norm = err_x_px / (frame_w / 2.0)
                err_norm = max(-1.0, min(1.0, err_norm))
                needle_x = bar_x0 + bar_w // 2 + int(err_norm * (bar_w // 2 - 5))
                cv2.rectangle(disp, (needle_x - 4, bar_y - 4),
                              (needle_x + 4, bar_y + bar_h + 4), needle_color, -1)
            else:
                state_label = "NO TARGET"

            # HUD textual
            cv2.putText(disp, f"GUARD MODE  [{state_label}]", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(disp, f"wz={wz:+.2f} rad/s   err_x={err_x_px:+.0f}px", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 2)
            cv2.putText(disp, f"YOLO: {fps:.1f} fps", (10, bar_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("guard_mode", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed = time.monotonic() - t_loop
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\n[guard] Interrumpido.")
    finally:
        worker.stop_event.set()
        worker.join(timeout=2.0)
        dog.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
