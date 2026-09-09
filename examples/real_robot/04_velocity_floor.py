#!/usr/bin/env python3
"""Fase 6 — Primer test en el SUELO con velocidades pequenas.

Una vez validadas las fases 4 y 5, bajamos al perro a una zona despejada
y le damos comandos suaves. Suelta el peso poco a poco.

REQUISITOS:
  - Zona despejada de al menos 3x3 m.
  - Has validado Fase 5 con exito.
  - Suelo no resbaladizo.
  - Tu mano cerca del switch fisico por si acaso.

Para subir las velocidades progresivamente, edita VX_LIST y WZ_LIST y
relanza el script.

Uso:
  1. Ajusta NETWORK abajo.
  2. python3 examples/real_robot/04_velocity_floor.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
NETWORK = "eth0"

# Lista de velocidades a probar en secuencia.
# Sube los valores poco a poco a medida que ganes confianza.
VX_LIST = [0.20, 0.30, 0.50]      # m/s forward
WZ_LIST = [0.30, 0.60, 1.00]      # rad/s yaw
DURATION_S = 3.0                   # cuanto dura cada paso
GAP_S = 2.0                        # pausa entre pasos

# ============================================================
# Setup paths
# ============================================================
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller


def announce(msg):
    print(msg, flush=True)


def main():
    print(f"[fase6] Conectando al Go2 real via {NETWORK}...")
    print("[fase6] EL PERRO DEBE ESTAR EN EL SUELO en zona despejada.")
    print("[fase6] Si tienes dudas, Ctrl+C ahora. Empezamos en 5s...")
    time.sleep(5)

    try:
        dog = Go2Controller(mode="real", network=NETWORK)
    except Exception as e:
        print(f"[fase6] FAIL: no se pudo conectar: {e}")
        sys.exit(1)

    try:
        announce(">>> StandUp")
        dog.stand_up()
        time.sleep(4)

        # Forward incremental
        for vx in VX_LIST:
            announce(f">>> Forward vx={vx:+.2f} m/s durante {DURATION_S}s")
            dog.set_velocity(vx=vx, vy=0, wz=0)
            time.sleep(DURATION_S)
            dog.stop()
            time.sleep(GAP_S)

        # Backward incremental (mismo modulo)
        for vx in VX_LIST:
            announce(f">>> Backward vx={-vx:+.2f} m/s durante {DURATION_S}s")
            dog.set_velocity(vx=-vx, vy=0, wz=0)
            time.sleep(DURATION_S)
            dog.stop()
            time.sleep(GAP_S)

        # Yaw incremental
        for wz in WZ_LIST:
            announce(f">>> Yaw wz={wz:+.2f} rad/s durante {DURATION_S}s")
            dog.set_velocity(vx=0, vy=0, wz=wz)
            time.sleep(DURATION_S)
            dog.stop()
            time.sleep(GAP_S)

        print("[fase6] Test en suelo COMPLETADO OK")

    except KeyboardInterrupt:
        print("\n[fase6] Interrumpido por usuario.")
    finally:
        print("[fase6] Parando perro y sentando para acabar.")
        dog.stop()
        time.sleep(0.5)
        try:
            dog.sit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
