"""Go2Controller: una API alto nivel que sirve tanto para sim como real.

Los alumnos solo necesitan esto. Internamente:
- mode="sim": publica WirelessController_ por DDS al simulador (play_dds.py).
- mode="real": llama a SportClient del SDK alto nivel del Go2 fisico.

En ambos casos la API es identica: set_velocity, stop, stand_up, etc.

Ejemplo basico:
    from tools.go2_controller import Go2Controller

    dog = Go2Controller(mode="sim", network="lo")
    dog.stand_up()       # en sim ya esta de pie; en real, levanta
    dog.set_velocity(vx=0.3, vy=0.0, wz=0.0)   # avanza
    time.sleep(2.0)
    dog.set_velocity(0, 0, 0.5)                 # gira
    time.sleep(2.0)
    dog.stop()
    dog.sit()            # solo real

El alumno NUNCA toca RL, ni motors, ni DDS bajo nivel, ni Sport Mode.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

# Asegura que unitree_sdk2py esta en el path
_SDK2_PYTHON = Path("~/robotics/unitree_sdk2_python").expanduser()
if _SDK2_PYTHON.exists() and str(_SDK2_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SDK2_PYTHON))


class _SimBackend:
    """Backend para simulador: publica WirelessController por DDS."""

    def __init__(self, network: str = "lo", domain_id: int = 0) -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_

        ChannelFactoryInitialize(domain_id, network)
        self._pub = ChannelPublisher("rt/wirelesscontroller", WirelessController_)
        self._pub.Init()
        self._msg_cls = WirelessController_
        self._msg = WirelessController_(lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0)
        # Publica una vez para "darse de alta"
        self._pub.Write(self._msg)

    def set_velocity(self, vx: float, vy: float, wz: float) -> None:
        # Mapping: ly = vx, lx = vy, rx = wz (matching teleop_wireless.py)
        self._msg.ly = float(vx)
        self._msg.lx = float(vy)
        self._msg.rx = float(wz)
        self._pub.Write(self._msg)

    def stand_up(self) -> None:
        # En sim, el FSM nativo de play_dds.py ya pone al perro de pie y
        # ejecuta la policy directamente. No-op aqui.
        pass

    def sit(self) -> None:
        # No emulado en sim. Lo dejamos como stop().
        self.set_velocity(0, 0, 0)

    def stop(self) -> None:
        self.set_velocity(0, 0, 0)


class _RealBackend:
    """Backend para el robot fisico: SportClient."""

    def __init__(self, network: str, domain_id: int = 0) -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.sport.sport_client import SportClient

        ChannelFactoryInitialize(domain_id, network)
        self._sport = SportClient()
        self._sport.SetTimeout(5.0)
        self._sport.Init()

    def set_velocity(self, vx: float, vy: float, wz: float) -> None:
        # Sport Mode acepta directamente (vx, vy, wz)
        self._sport.Move(vx, vy, wz)

    def stand_up(self) -> None:
        self._sport.StandUp()

    def sit(self) -> None:
        self._sport.Sit()

    def stop(self) -> None:
        self._sport.StopMove()


class Go2Controller:
    """API alto nivel del Go2 (sim o real)."""

    def __init__(
        self,
        mode: Literal["sim", "real"] = "sim",
        network: str = "lo",
        domain_id: int = 0,
    ) -> None:
        """
        Args:
            mode: "sim" para usar play_dds.py como simulador.
                  "real" para hablar con el Go2 fisico via Sport Mode.
            network: interfaz DDS. "lo" para sim, ej. "enp5s0" para real.
            domain_id: dominio DDS (0 por defecto, igual que el sim).
        """
        if mode == "sim":
            self._backend = _SimBackend(network=network, domain_id=domain_id)
        elif mode == "real":
            self._backend = _RealBackend(network=network, domain_id=domain_id)
        else:
            raise ValueError(f"mode debe ser 'sim' o 'real', no {mode!r}")
        self.mode = mode

    def set_velocity(self, vx: float = 0.0, vy: float = 0.0, wz: float = 0.0) -> None:
        """Manda comando de velocidad al perro.

        Args:
            vx: velocidad lineal forward/backward (m/s). + = adelante.
            vy: velocidad lineal lateral (m/s). + = izquierda.
            wz: velocidad angular yaw (rad/s). + = giro a la izquierda.
        """
        self._backend.set_velocity(vx, vy, wz)

    def stand_up(self) -> None:
        """Levanta el perro a postura de pie. En sim ya esta de pie; no-op."""
        self._backend.stand_up()

    def sit(self) -> None:
        """Sienta el perro (solo robot real; en sim equivale a stop)."""
        self._backend.sit()

    def stop(self) -> None:
        """Para el perro: vx=vy=wz=0."""
        self._backend.stop()
