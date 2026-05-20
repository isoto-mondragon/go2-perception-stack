#!/usr/bin/env python3
"""Teleop por teclado publicando WirelessController_ por DDS.

El controlador C++ (go2_ctrl) lee el joystick desde lowstate (que mapea
internamente el topic rt/wirelesscontroller). Publicando aqui simulamos
un mando para alimentar `velocity_commands` a la policy RL.

Mapeo:
  ly = vx  (forward/backward) <- W / S
  lx = vy  (strafe izq/der)   <- A / D
  rx = wz  (yaw)              <- Q / E
  espacio = parada total (todos los ejes a 0)

Uso (en una tercera terminal, con sim+go2_ctrl corriendo):
  python3 tools/teleop_wireless.py --network lo
"""

from __future__ import annotations

import argparse
import sys
import termios
import time
import tty
from pathlib import Path

# Anadimos el unitree_sdk2_python local al PYTHONPATH si esta ahi
ROBOTICS_ROOT = Path("~/robotics").expanduser()
SDK2_PY = ROBOTICS_ROOT / "unitree_sdk2_python"
if SDK2_PY.exists():
    sys.path.insert(0, str(SDK2_PY))

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_


class KbReader:
    """Lector de teclado no bloqueante (raw mode)."""

    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *_):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def poll(self) -> str | None:
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="lo", help="Interfaz DDS (lo para sim, ethX para robot)")
    ap.add_argument("--step", type=float, default=0.3, help="Incremento por pulsacion")
    ap.add_argument("--max-lin", type=float, default=1.0, help="Maxima vel lineal (m/s)")
    ap.add_argument("--max-ang", type=float, default=1.0, help="Maxima vel angular (rad/s)")
    ap.add_argument("--rate", type=float, default=50.0, help="Hz de publicacion")
    args = ap.parse_args()

    ChannelFactoryInitialize(0, args.network)
    pub = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
    pub.Init()

    # El IDL de unitree_sdk2py no aplica defaults: hay que pasar los 5 campos.
    msg = WirelessController_(lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0)

    period = 1.0 / args.rate
    print("Teleop WirelessController. Controles:")
    print("  W/S = forward/backward   |   A/D = strafe   |   Q/E = yaw")
    print("  Shift+W/S = MAX forward/backward (vx=+/-max)")
    print("  ESPACIO = stop           |   Ctrl+C = salir")
    print(f"network={args.network}  step={args.step}  max_lin={args.max_lin}  max_ang={args.max_ang}\n")

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    last_print = 0.0
    with KbReader() as kb:
        try:
            while True:
                k = kb.poll()
                if k:
                    if k == "w":
                        msg.ly = clamp(msg.ly + args.step, -args.max_lin, args.max_lin)
                    elif k == "s":
                        msg.ly = clamp(msg.ly - args.step, -args.max_lin, args.max_lin)
                    elif k == "a":
                        msg.lx = clamp(msg.lx + args.step, -args.max_lin, args.max_lin)
                    elif k == "d":
                        msg.lx = clamp(msg.lx - args.step, -args.max_lin, args.max_lin)
                    elif k == "q":
                        msg.rx = clamp(msg.rx + args.step, -args.max_ang, args.max_ang)
                    elif k == "e":
                        msg.rx = clamp(msg.rx - args.step, -args.max_ang, args.max_ang)
                    elif k == "W":   # Shift+W -> max forward
                        msg.ly = args.max_lin
                    elif k == "S":   # Shift+S -> max backward
                        msg.ly = -args.max_lin
                    elif k == "A":
                        msg.lx = args.max_lin
                    elif k == "D":
                        msg.lx = -args.max_lin
                    elif k == "Q":
                        msg.rx = args.max_ang
                    elif k == "E":
                        msg.rx = -args.max_ang
                    elif k == " ":
                        msg.lx = msg.ly = msg.rx = msg.ry = 0.0
                    elif k == "\x03":  # Ctrl+C raw
                        break

                pub.Write(msg)

                now = time.time()
                if now - last_print > 0.2:
                    print(f"\rvx={msg.ly:+.2f}  vy={msg.lx:+.2f}  wz={msg.rx:+.2f}   ",
                          end="", flush=True)
                    last_print = now

                time.sleep(period)
        except KeyboardInterrupt:
            pass
        finally:
            # Mandar comando de parada al salir
            msg.lx = msg.ly = msg.rx = msg.ry = 0.0
            for _ in range(10):
                pub.Write(msg)
                time.sleep(period)
            print("\nStop publicado.")


if __name__ == "__main__":
    main()
