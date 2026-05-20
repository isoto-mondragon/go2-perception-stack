#!/usr/bin/env python3
"""Demo: perro de vigilancia. Patrulla y se gira hacia un intruso.

Comportamiento:
  Estado PATROL:
    - Avanza 4s, gira 90 grados a la derecha (~1.7s), repite.
    - Continuamente corre YOLO.
    - Si detecta el TARGET_CLASS -> pasa a estado ALERT.

  Estado ALERT:
    - Para de avanzar.
    - Rota para apuntar al intruso (lo centra en el frame).
    - Imprime un aviso en terminal.
    - Si el intruso desaparece > N segundos -> vuelve a PATROL.

Concepto pedagogico: maquina de estados con interrupcion por percepcion.

Para SIM:
  Terminal 1:  python tools/play_dds.py Unitree-Go2-Flat \
                  --checkpoint-file=<model.pt> --network=lo
  Terminal 2:  python examples/patrol_and_alert.py

Para REAL: cambia MODE="real" y NETWORK="enp5s0" (tu interfaz Ethernet).
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

TARGET_CLASS = "person"   # "person", "cat", "dog", "car"...
CAMERA_INDEX = 0

# Patrol: avanza/gira en bucle
PATROL_VX = 0.4              # m/s mientras avanza
PATROL_FORWARD_S = 4.0       # segundos avanzando antes de girar
PATROL_TURN_WZ = 1.0         # rad/s al girar
PATROL_TURN_S = 1.7          # segundos girando (≈ 90 deg si wz=1.0)

# Alert: rotacion hacia el intruso
ALERT_KP_YAW = 1.2
ALERT_MAX_WZ = 1.0
ALERT_DEAD_ZONE_PX = 40
ALERT_LOST_TIMEOUT_S = 2.5   # tras este tiempo sin verlo, vuelve a patrullar

CONTROL_RATE_HZ = 20


def biggest_detection(detections):
    """De una lista de (x1,y1,x2,y2,conf), devuelve la de mayor area."""
    if not detections:
        return None
    return max(detections, key=lambda d: (d[2] - d[0]) * (d[3] - d[1]))


def main():
    print(f"[patrol] modo={MODE} | target={TARGET_CLASS}")

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

    # ---- Estado ----
    state = "PATROL"
    patrol_phase = "forward"   # "forward" o "turn"
    patrol_phase_start = time.monotonic()
    last_seen_t = 0.0

    period = 1.0 / CONTROL_RATE_HZ
    print(f"[patrol] Estado inicial: {state}. Pulsa 'q' en la ventana para salir.")

    try:
        while True:
            t_loop = time.monotonic()
            frame, detections, fps, _, _ = worker.latest()
            if frame is None:
                time.sleep(period)
                continue

            target = biggest_detection(detections)
            seen = target is not None

            # --- Maquina de estados ---
            if state == "PATROL":
                if seen:
                    state = "ALERT"
                    last_seen_t = time.monotonic()
                    print("[patrol] !!! INTRUSO DETECTADO. -> ALERT")
                    dog.stop()
                else:
                    # Continuar patrullando: forward -> turn -> forward -> ...
                    elapsed = time.monotonic() - patrol_phase_start
                    if patrol_phase == "forward":
                        dog.set_velocity(vx=PATROL_VX, vy=0, wz=0)
                        if elapsed >= PATROL_FORWARD_S:
                            patrol_phase = "turn"
                            patrol_phase_start = time.monotonic()
                            print("[patrol] giro 90 deg")
                    else:  # "turn"
                        dog.set_velocity(vx=0, vy=0, wz=-PATROL_TURN_WZ)   # giro derecha
                        if elapsed >= PATROL_TURN_S:
                            patrol_phase = "forward"
                            patrol_phase_start = time.monotonic()
                            print("[patrol] avanza")

            elif state == "ALERT":
                if seen:
                    last_seen_t = time.monotonic()
                    # Centrar el target en el frame con yaw
                    x1, y1, x2, y2, _conf = target
                    cx = (x1 + x2) / 2.0
                    err_x = (cx - frame_w / 2.0) / (frame_w / 2.0)
                    if abs(cx - frame_w / 2.0) < ALERT_DEAD_ZONE_PX:
                        wz = 0.0
                    else:
                        wz = -ALERT_KP_YAW * err_x
                        wz = max(-ALERT_MAX_WZ, min(ALERT_MAX_WZ, wz))
                    dog.set_velocity(vx=0, vy=0, wz=wz)
                else:
                    # No lo veo. Espera ALERT_LOST_TIMEOUT_S antes de volver a patrullar
                    dog.stop()
                    if time.monotonic() - last_seen_t > ALERT_LOST_TIMEOUT_S:
                        state = "PATROL"
                        patrol_phase = "forward"
                        patrol_phase_start = time.monotonic()
                        print("[patrol] sin intruso, volviendo a PATROL")

            # --- Display ---
            disp = frame.copy()
            if target is not None:
                x1, y1, x2, y2, conf = target
                color = (0, 0, 255) if state == "ALERT" else (0, 255, 0)
                cv2.rectangle(disp, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(disp, f"{TARGET_CLASS} {conf:.2f}", (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            color_state = (0, 0, 255) if state == "ALERT" else (255, 255, 0)
            cv2.putText(disp, f"STATE: {state}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color_state, 2)
            if state == "PATROL":
                cv2.putText(disp, f"phase: {patrol_phase}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            cv2.putText(disp, f"YOLO: {fps:.1f} fps", (10, frame_h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("patrol_and_alert", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed = time.monotonic() - t_loop
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\n[patrol] Interrumpido.")
    finally:
        worker.stop_event.set()
        worker.join(timeout=2.0)
        dog.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
