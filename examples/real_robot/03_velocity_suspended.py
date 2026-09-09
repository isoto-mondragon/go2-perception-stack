#!/usr/bin/env python3
"""Fase 5 — Velocidad MINIMA con el perro suspendido.

Test progresivo de comandos de velocidad pequenos. El perro DEBE estar
suspendido. Solo veras las patas moviendose en el aire (forward / back
/ yaw). El cuerpo apenas se desplaza porque no hay traccion.

REQUISITOS:
  - El perro suspendido en mesa o arnes.
  - Has validado Fase 4 (StandUp/Sit funcionan).
  - Cable Ethernet sin riesgo de enrollarse en las patas.

Uso:
  1. Ajusta NETWORK abajo.
  2. python3 examples/real_robot/03_velocity_suspended.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
NETWORK = "eth0"

# Velocidades muy bajas para el test suspendido
VX_TEST = 0.10        # m/s forward / backward
WZ_TEST = 0.30        # rad/s yaw
DURATION_S = 2.0      # cuanto dura cada paso
GAP_S = 2.0           # pausa entre pasos

# ============================================================
# Setup paths
# ============================================================
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller


def announce(msg):
    print(msg, flush=True)


def main():
    print(f"[fase5] Conectando al Go2 real via {NETWORK}...")
    print("[fase5] EL PERRO DEBE ESTAR SUSPENDIDO. Si no, Ctrl+C ahora.")
    time.sleep(3)

    try:
        dog = Go2Controller(mode="real", network=NETWORK)
    except Exception as e:
        print(f"[fase5] FAIL: no se pudo conectar: {e}")
        sys.exit(1)

    try:
        announce(">>> StandUp")
        dog.stand_up()
        time.sleep(4)

        announce(f">>> Forward vx={VX_TEST:+.2f} m/s durante {DURATION_S}s")
        dog.set_velocity(vx=VX_TEST, vy=0, wz=0)
        time.sleep(DURATION_S)
        dog.stop()
        time.sleep(GAP_S)

        announce(f">>> Backward vx={-VX_TEST:+.2f} m/s durante {DURATION_S}s")
        dog.set_velocity(vx=-VX_TEST, vy=0, wz=0)
        time.sleep(DURATION_S)
        dog.stop()
        time.sleep(GAP_S)

        announce(f">>> Yaw izq wz={WZ_TEST:+.2f} rad/s durante {DURATION_S}s")
        dog.set_velocity(vx=0, vy=0, wz=WZ_TEST)
        time.sleep(DURATION_S)
        dog.stop()
        time.sleep(GAP_S)

        announce(f">>> Yaw der wz={-WZ_TEST:+.2f} rad/s durante {DURATION_S}s")
        dog.set_velocity(vx=0, vy=0, wz=-WZ_TEST)
        time.sleep(DURATION_S)
        dog.stop()

        print("[fase5] Test velocidades COMPLETADO OK")

    except KeyboardInterrupt:
        print("\n[fase5] Interrumpido por usuario.")
    finally:
        print("[fase5] Parando.")
        dog.stop()


if __name__ == "__main__":
    main()
