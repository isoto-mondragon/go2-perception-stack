#!/usr/bin/env python3
"""Demo: busca y aproximate. El perro gira buscando un objeto, va a por el.

Comportamiento:
  Estado SEARCH:
    - Gira en sitio (~0.7 rad/s) hasta detectar el TARGET_CLASS.
    - Si no encuentra nada durante mucho tiempo, sigue girando indefinidamente.

  Estado APPROACH:
    - Avanza hacia el objeto: combina (vx, wz) para acercarse en linea.
    - Si el bbox es lo bastante grande -> el objeto esta CERCA -> pasa a ARRIVED.

  Estado ARRIVED:
    - Para de moverse. Imprime mensaje.
    - Si el objeto sale del frame durante > N s -> vuelve a SEARCH.

Concepto pedagogico: busqueda + aproximacion. Diferente al follow tipico
porque NO depende de que el objeto se mueva: el perro va activamente a
buscarlo aunque sea estatico.

Cambia TARGET_CLASS para objetivos distintos:
  "sports ball", "bottle", "cup", "cell phone", "book", "backpack", "chair"...

Lista completa: python -c "from ultralytics import YOLO; print(YOLO('yolov8n.pt').names)"
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

TARGET_CLASS = "person"   # prueba "bottle", "cup", "cell phone"...
CAMERA_INDEX = 0

# Busqueda
SEARCH_WZ = 0.7              # rad/s mientras gira buscando

# Aproximacion
APPROACH_KP_YAW = 1.2
APPROACH_MAX_WZ = 0.8
APPROACH_VX_MAX = 0.5
APPROACH_KP_DIST = 1.5
DEAD_ZONE_PX = 35

# Cerca/lejos: ha "llegado" cuando el bbox ocupa este % del alto del frame.
# Relativo al frame para que sirva con cualquier clase:
#   - "person":               0.70-0.85 (cuando estas cerca llenas el frame)
#   - "sports ball", "cup":   0.25-0.40 (objetos chicos)
#   - "bottle", "cell phone": 0.40-0.55
ARRIVED_BBOX_H_FRAC = 0.75
LOST_TIMEOUT_S = 2.0         # tras este tiempo sin ver el objeto -> SEARCH

CONTROL_RATE_HZ = 20


def biggest_detection(detections):
    if not detections:
        return None
    return max(detections, key=lambda d: (d[2] - d[0]) * (d[3] - d[1]))


def main():
    print(f"[fetch] modo={MODE} | target={TARGET_CLASS}")

    print("Cargando YOLOv8n...")
    yolo = YOLO("yolov8n.pt")
    target_id = get_class_id(yolo, TARGET_CLASS)
    if target_id is None:
        raise SystemExit(f"Clase '{TARGET_CLASS}' no existe en COCO. Mira las clases con: \n"
                         f"  python -c \"from ultralytics import YOLO; print(YOLO('yolov8n.pt').names)\"")

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

    state = "SEARCH"
    last_seen_t = 0.0
    arrived_h_px = frame_h * ARRIVED_BBOX_H_FRAC
    print(f"[fetch] umbral ARRIVED = {arrived_h_px:.0f}px (= {ARRIVED_BBOX_H_FRAC*100:.0f}% del alto de {frame_h}px)")

    period = 1.0 / CONTROL_RATE_HZ
    print(f"[fetch] Inicio en {state}. Pulsa 'q' en la ventana para salir.")

    try:
        while True:
            t_loop = time.monotonic()
            frame, detections, fps, _, _ = worker.latest()
            if frame is None:
                time.sleep(period)
                continue

            target = biggest_detection(detections)
            seen = target is not None

            if state == "SEARCH":
                if seen:
                    state = "APPROACH"
                    last_seen_t = time.monotonic()
                    print(f"[fetch] {TARGET_CLASS} encontrado -> APPROACH")
                else:
                    dog.set_velocity(vx=0, vy=0, wz=SEARCH_WZ)

            elif state == "APPROACH":
                if seen:
                    last_seen_t = time.monotonic()
                    x1, y1, x2, y2, _conf = target
                    cx = (x1 + x2) / 2.0
                    bbox_h = y2 - y1

                    # Yaw para centrarlo
                    err_x = (cx - frame_w / 2.0) / (frame_w / 2.0)
                    if abs(cx - frame_w / 2.0) < DEAD_ZONE_PX:
                        wz = 0.0
                    else:
                        wz = -APPROACH_KP_YAW * err_x
                        wz = max(-APPROACH_MAX_WZ, min(APPROACH_MAX_WZ, wz))

                    # Cerca?
                    if bbox_h >= arrived_h_px:
                        state = "ARRIVED"
                        dog.stop()
                        print(f"[fetch] LLEGADO al {TARGET_CLASS}. -> ARRIVED")
                        continue

                    # Forward proporcional a la distancia (bbox pequeno -> mas vel)
                    err_dist = (arrived_h_px - bbox_h) / arrived_h_px
                    vx = APPROACH_KP_DIST * err_dist
                    vx = max(0.0, min(APPROACH_VX_MAX, vx))

                    # Si esta muy descentrado, prioriza girar (no avances)
                    if abs(err_x) > 0.3:
                        vx *= 0.3

                    dog.set_velocity(vx=vx, vy=0, wz=wz)
                else:
                    # Lo perdi de vista
                    dog.stop()
                    if time.monotonic() - last_seen_t > LOST_TIMEOUT_S:
                        state = "SEARCH"
                        print(f"[fetch] objeto perdido -> SEARCH")

            elif state == "ARRIVED":
                dog.stop()
                if not seen:
                    if time.monotonic() - last_seen_t > LOST_TIMEOUT_S:
                        state = "SEARCH"
                        print("[fetch] objeto desaparecio -> SEARCH")
                else:
                    last_seen_t = time.monotonic()
                    # Si el bbox se hace pequeno (el objeto se aleja) -> APPROACH de nuevo
                    x1, y1, x2, y2, _ = target
                    if (y2 - y1) < arrived_h_px * 0.7:
                        state = "APPROACH"
                        print("[fetch] el objeto se aleja -> APPROACH")

            # --- Display ---
            disp = frame.copy()
            if target is not None:
                x1, y1, x2, y2, conf = target
                color = {
                    "SEARCH":   (200, 200, 0),
                    "APPROACH": (0, 200, 0),
                    "ARRIVED":  (0, 165, 255),
                }[state]
                cv2.rectangle(disp, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(disp, f"{TARGET_CLASS} {conf:.2f}", (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(disp, f"STATE: {state}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            cv2.putText(disp, f"YOLO: {fps:.1f} fps", (10, frame_h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("fetch_object", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed = time.monotonic() - t_loop
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\n[fetch] Interrumpido.")
    finally:
        worker.stop_event.set()
        worker.join(timeout=2.0)
        dog.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
