#!/usr/bin/env python3
"""Fase 3 — Comprobar que DDS habla con el Go2 real.

Solo LEE de rt/lowstate. No manda ningún comando. 100% seguro.

Uso:
  1. Ajusta NETWORK abajo con tu interfaz real (eth0, enp0s5, ...).
  2. python3 examples/real_robot/01_dds_check.py

Salida esperada:
  Recibidos ~1500 mensajes en 3s   -> OK
  Recibidos 0 mensajes              -> red mal configurada
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ============================================================
# CONFIG: ajusta esto a tu instalacion
# ============================================================
NETWORK = "eth0"   # nombre de tu interfaz Ethernet en WSL (ver `ip addr`)
DURATION_S = 3.0
DOMAIN_ID = 0

# ============================================================
# Setup paths
# ============================================================
SDK2_PYTHON = Path("~/robotics/unitree_sdk2_python").expanduser()
if SDK2_PYTHON.exists() and str(SDK2_PYTHON) not in sys.path:
    sys.path.insert(0, str(SDK2_PYTHON))

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_


def main():
    print(f"[fase3] Inicializando DDS sobre interfaz '{NETWORK}', domain={DOMAIN_ID}")
    try:
        ChannelFactoryInitialize(DOMAIN_ID, NETWORK)
    except Exception as e:
        print(f"[fase3] FAIL: no se pudo inicializar DDS: {e}")
        print("       Comprueba que NETWORK es correcto (ver `ip addr` en WSL).")
        sys.exit(1)

    received = {"count": 0, "last_tick": None}

    def on_msg(msg):
        received["count"] += 1
        received["last_tick"] = getattr(msg, "tick", None)

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_msg, 10)

    print(f"[fase3] Escuchando rt/lowstate durante {DURATION_S}s...")
    time.sleep(DURATION_S)

    count = received["count"]
    rate = count / DURATION_S
    print(f"[fase3] Recibidos {count} mensajes en {DURATION_S}s ({rate:.1f} Hz)")

    if count == 0:
        print("[fase3] FAIL: no llegan mensajes.")
        print("       Revisa:")
        print("        - El Go2 esta encendido y en la misma subred.")
        print("        - `ping 192.168.123.161` responde desde WSL.")
        print("        - .wslconfig tiene networkingMode=mirrored y wsl --shutdown.")
        print(f"        - NETWORK='{NETWORK}' es el nombre real de tu interfaz.")
        sys.exit(2)

    if count < 100:
        print("[fase3] WARN: muy pocos mensajes. La conexion existe pero es")
        print("       muy intermitente. Mira cable / interferencias.")
    else:
        print("[fase3] OK - DDS funcionando, el perro publica lowstate.")


if __name__ == "__main__":
    main()
