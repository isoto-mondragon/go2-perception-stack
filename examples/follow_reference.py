#!/usr/bin/env python3
"""Demo: el perro SOLO sigue al objeto/persona que ENSENAS en una foto.

Diferencia con follow_yolo.py:
  - follow_yolo.py sigue al detection "mas grande" de TARGET_CLASS
    (cualquier persona en el frame, por ejemplo).
  - follow_reference.py te pide una foto de referencia, calcula su
    "huella visual" (histograma HSV de color) y solo sigue al detection
    que mas se parezca a la referencia.

Util para:
  - "Que el perro me siga solo a MI" (foto de tu camiseta).
  - "Que vaya a por esa botella concreta de un grupo".
  - "Que reaccione solo al companero con peto naranja".

Como preparar la foto de referencia:
  Recorta una imagen del objetivo (jpg o png). Cuanto mejor centrada y
  limpia (sin fondo), mas robusto el matching.
  Ejemplo: foto de tu cara + camiseta, fondo blanco.

Uso:
  python examples/follow_reference.py --reference /ruta/a/foto.jpg

  # Opcionalmente cambiar la clase objetivo si no es persona:
  python examples/follow_reference.py --reference foto.jpg --target bottle
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

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
CAMERA_INDEX = 0

# Control
MAX_VX = 0.5
MAX_WZ = 0.8
DEAD_ZONE_PX = 50
TARGET_BBOX_H_PX = 400
KP_YAW = 1.5
KP_FORWARD = 1.0
CONTROL_RATE_HZ = 20

# Matching: minimo de similitud con la referencia para considerar un match.
# Histograma HSV, escala 0..1. Subir => mas estricto. Bajar => mas permisivo.
SIM_THRESHOLD = 0.45
# Histograma HSV: bins de H y S
HIST_BINS = (50, 60)


# ============================================================
# Reidentificacion por histograma HSV (no necesita modelos extra)
# ============================================================
def compute_hsv_hist(image_bgr):
    """Histograma 2D (H,S) normalizado. Robusto a cambios de iluminacion suaves."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, HIST_BINS, [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()


def hist_similarity(hist_a, hist_b):
    """Similitud en [0, 1]. 1 = identicas."""
    # Bhattacharyya distance: 0 (identicas) .. 1 (totalmente distintas)
    d = cv2.compareHist(hist_a.astype("float32"), hist_b.astype("float32"),
                        cv2.HISTCMP_BHATTACHARYYA)
    return float(1.0 - d)


def build_reference_hist(image_path: str, yolo, target_class_id: int):
    """Carga la foto y devuelve su histograma HSV.

    Si YOLO detecta el target_class en la foto, usamos la bbox detectada
    (mas robusto). Si no, usamos la imagen entera (asume recorte limpio).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise SystemExit(f"No se pudo leer la imagen: {image_path}")

    # Intenta auto-recortar con YOLO
    results = yolo.predict(img, verbose=False, imgsz=320, conf=0.3)
    if results and results[0].boxes is not None:
        boxes = results[0].boxes
        best_area = 0.0
        best_crop = None
        for i in range(len(boxes)):
            if int(boxes.cls[i].item()) != target_class_id:
                continue
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            area = (x2 - x1) * (y2 - y1)
            if area > best_area:
                best_area = area
                best_crop = img[int(y1):int(y2), int(x1):int(x2)]
        if best_crop is not None and best_crop.size > 0:
            print(f"[ref] YOLO detecto el objetivo en la referencia, usando crop.")
            return compute_hsv_hist(best_crop), best_crop

    print("[ref] YOLO no detecto el objetivo en la referencia. Uso la imagen entera.")
    return compute_hsv_hist(img), img


# ============================================================
# Logica del controlador (igual que follow_yolo)
# ============================================================
def compute_command(target, frame_w):
    if target is None:
        return 0.0, 0.0, 0.0

    x1, y1, x2, y2 = target[:4]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True,
                    help="Ruta a la foto de referencia del objetivo")
    ap.add_argument("--target", default="person",
                    help="Clase COCO del objetivo (person, bottle, cup, etc.)")
    ap.add_argument("--mode", default=MODE, choices=["sim", "real"])
    ap.add_argument("--network", default=NETWORK)
    ap.add_argument("--conf", type=float, default=0.30,
                    help="Confianza minima de YOLO. Baja a 0.15-0.25 si tu objeto no se detecta")
    ap.add_argument("--threshold", type=float, default=SIM_THRESHOLD,
                    help="Umbral de similitud HSV (0..1). Sube=mas estricto, baja=mas permisivo")
    ap.add_argument("--debug", action="store_true",
                    help="Muestra TODAS las detecciones de YOLO en gris para diagnostico")
    ap.add_argument("--memory", type=float, default=0.5,
                    help="Segundos durante los que recordamos la ultima deteccion buena "
                         "aunque YOLO parpadee. Sube si tu deteccion es muy inestable.")
    args = ap.parse_args()

    print(f"[follow_ref] modo={args.mode} | target={args.target} | ref={args.reference}")

    print("Cargando YOLOv8n...")
    yolo = YOLO("yolov8n.pt")
    target_id = get_class_id(yolo, args.target)
    if target_id is None:
        raise SystemExit(f"Clase '{args.target}' no existe en COCO")

    print("Procesando imagen de referencia...")
    ref_hist, ref_crop = build_reference_hist(args.reference, yolo, target_id)
    cv2.imshow("REFERENCE", cv2.resize(ref_crop, (200, 200)))
    cv2.waitKey(1)  # forzar display

    cap = open_camera(CAMERA_INDEX)
    if cap is None:
        raise SystemExit("No se pudo abrir la camara")
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    dog = Go2Controller(mode=args.mode, network=args.network)
    dog.stand_up()
    time.sleep(1.0)

    # En modo debug, queremos ver TODAS las detecciones, no solo la clase objetivo.
    # Para eso usamos un target_id "ficticio" que nunca matchea y luego lo
    # ignoramos: corremos YOLO con confianza baja y filtramos en el cliente.
    # Mas simple: usamos un YoloCaptureThread con la clase objetivo y un
    # segundo "debug worker" si --debug, pero por simplicidad bajamos conf.
    worker = YoloCaptureThread(cap, CAMERA_INDEX, yolo, target_id, conf=args.conf)
    worker.start()
    threshold = args.threshold
    print("Esperando primer frame...")
    while worker.latest()[0] is None:
        time.sleep(0.1)

    period = 1.0 / CONTROL_RATE_HZ
    last_cmd = (0.0, 0.0, 0.0)
    # Memoria temporal: si YOLO pierde el objeto unos frames, mantenemos
    # la ultima deteccion buena durante args.memory segundos.
    last_match = None        # (x1, y1, x2, y2, conf, sim)
    last_match_ts = 0.0
    print(f"[follow_ref] Activo. YOLO conf={args.conf:.2f}  sim threshold={threshold:.2f}  "
          f"memory={args.memory:.1f}s. Pulsa 'q' en la ventana para salir.")

    try:
        while True:
            t_loop = time.monotonic()
            frame, detections, fps, _, _ = worker.latest()
            if frame is None:
                time.sleep(period)
                continue

            # Para cada deteccion, computar similitud con referencia
            best = None       # (x1, y1, x2, y2, conf, sim)
            scored_all = []   # para visualizar
            for x1, y1, x2, y2, conf in detections:
                crop = frame[int(y1):int(y2), int(x1):int(x2)]
                if crop.size == 0:
                    continue
                hist = compute_hsv_hist(crop)
                sim = hist_similarity(ref_hist, hist)
                scored_all.append((x1, y1, x2, y2, conf, sim))
                if sim >= threshold:
                    if best is None or sim > best[5]:
                        best = (x1, y1, x2, y2, conf, sim)

            # Memoria temporal: si YOLO perdio el objeto en este frame
            # pero lo teniamos hace poco, reutilizamos la ultima deteccion.
            now = time.monotonic()
            is_stale_match = False
            if best is not None:
                last_match = best
                last_match_ts = now
            elif last_match is not None and (now - last_match_ts) < args.memory:
                best = last_match
                is_stale_match = True
            else:
                last_match = None  # expirada

            # Control
            vx, vy, wz = compute_command(best, frame_w)
            if (abs(vx - last_cmd[0]) > 0.01 or
                abs(vy - last_cmd[1]) > 0.01 or
                abs(wz - last_cmd[2]) > 0.01):
                dog.set_velocity(vx, vy, wz)
                last_cmd = (vx, vy, wz)

            # Display
            disp = frame.copy()
            # Dibujar todas las detecciones cuyo bbox fue scoreado este frame
            for x1, y1, x2, y2, conf, sim in scored_all:
                if best is not None and not is_stale_match and (x1, y1) == best[:2]:
                    color = (0, 255, 0)         # match fresco: verde
                    label = f"MATCH sim={sim:.2f}"
                else:
                    color = (100, 100, 200)     # no match: rojo apagado
                    label = f"{args.target} sim={sim:.2f}"
                cv2.rectangle(disp, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(disp, label, (int(x1), max(int(y1) - 8, 18)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            # Si estamos en "memoria" (YOLO perdio el objeto pero recordamos),
            # dibujamos la ultima bbox conocida en amarillo
            if is_stale_match and best is not None:
                x1, y1, x2, y2, _, sim = best
                age = now - last_match_ts
                cv2.rectangle(disp, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
                cv2.putText(disp, f"MEMORY {age:.2f}s sim={sim:.2f}",
                            (int(x1), max(int(y1) - 8, 18)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            cv2.putText(disp, f"vx={vx:+.2f}  wz={wz:+.2f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(disp, f"YOLO: {fps:.1f} fps  yolo_conf={args.conf:.2f}  thr={threshold:.2f}",
                        (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)
            cv2.putText(disp, f"{args.target} detectados: {len(detections)}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)
            if best is None:
                if len(detections) == 0:
                    msg = f"NO {args.target.upper()} EN FRAME"
                else:
                    best_sim = max((s[5] for s in scored_all), default=0.0)
                    msg = f"NO MATCH (mejor sim={best_sim:.2f})"
                cv2.putText(disp, msg, (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("follow_reference", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed = time.monotonic() - t_loop
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\n[follow_ref] Interrumpido.")
    finally:
        worker.stop_event.set()
        worker.join(timeout=2.0)
        dog.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
