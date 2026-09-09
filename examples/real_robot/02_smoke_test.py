#!/usr/bin/env python3
"""Fase 4 — Smoke test del Go2 real.

Solo levanta y sienta. SIN desplazamiento. Movimientos predecibles.

REQUISITOS:
  - El perro DEBE estar suspendido (en mesa o arnes), las patas
    sin tocar el suelo.
  - Hayas validado Fase 3 (01_dds_check.py imprime OK).

Uso:
  1. Ajusta NETWORK abajo.
  2. python3 examples/real_robot/02_smoke_test.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
NETWORK = "eth0"

# ============================================================
# Setup paths
# ============================================================
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller


def step(msg, duration_s):
    """Imprime una accion y espera duration_s. Permite Ctrl+C limpio."""
    print(msg, flush=True)
    try:
        time.sleep(duration_s)
    except KeyboardInterrupt:
        print("\n[fase4] Interrumpido por usuario.")
        raise


def main():
    print(f"[fase4] Conectando al Go2 real via {NETWORK}...")
    print("[fase4] EL PERRO DEBE ESTAR SUSPENDIDO. Si no lo esta, Ctrl+C ahora.")
    time.sleep(2)  # ventana para abortar

    try:
        dog = Go2Controller(mode="real", network=NETWORK)
    except Exception as e:
        print(f"[fase4] FAIL: no se pudo conectar: {e}")
        sys.exit(1)
    print("[fase4] Conectado. Empezando en 2s...")
    time.sleep(2)

    try:
        step(">>> StandUp (las patas se enderezan)", 4)
        dog.stand_up()
        time.sleep(4)

        step(">>> Sit (se sienta)", 4)
        dog.sit()
        time.sleep(4)

        step(">>> StandUp de nuevo", 4)
        dog.stand_up()
        time.sleep(4)

        print("[fase4] Smoke test COMPLETADO OK")

    except KeyboardInterrupt:
        pass
    finally:
        print("[fase4] Parando (set_velocity 0,0,0).")
        dog.stop()


if __name__ == "__main__":
    main()
