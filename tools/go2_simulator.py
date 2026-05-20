"""Encapsula el simulador completo del Go2 (mjlab env + DDS bridge + viewer).

Conecta tres piezas:
1. Un `Go2Policy` (la red neuronal entrenada).
2. Un suscriptor DDS al topic `rt/wirelesscontroller` (para recibir comandos
   del teleop o de tu codigo via `Go2Controller`).
3. Un viewer nativo de MuJoCo.

Cuando se llama a `.run()`, se abre la ventana del simulador y el perro
queda controlado por la policy, con el comando de velocidad llegando por
DDS. Bloquea hasta que se cierre la ventana.

Uso tipico desde Python:
    from tools.go2_simulator import Go2Simulator

    sim = Go2Simulator(checkpoint_file="model_4100.pt", network="lo")
    sim.run()   # bloquea hasta cerrar el viewer

Si solo quieres lanzar el sim desde linea de comandos, usa
`tools/play_dds.py` que es un wrapper de esto.
"""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Lock
from typing import Any

import torch

# DDS path setup
_SDK2_PYTHON = Path("~/robotics/unitree_sdk2_python").expanduser()
if _SDK2_PYTHON.exists() and str(_SDK2_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SDK2_PYTHON))


class _WirelessCommandBuffer:
    """Buffer thread-safe para el ultimo comando recibido por DDS."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.lx = 0.0
        self.ly = 0.0
        self.rx = 0.0
        self.ry = 0.0

    def update(self, msg) -> None:
        with self._lock:
            self.lx = float(msg.lx)
            self.ly = float(msg.ly)
            self.rx = float(msg.rx)
            self.ry = float(msg.ry)

    def get_vxvywz(self) -> tuple[float, float, float]:
        """Devuelve (vx, vy, wz) en convencion teleop:
        ly -> vx, lx -> vy, rx -> wz."""
        with self._lock:
            return self.ly, self.lx, self.rx


class Go2Simulator:
    """Simulador completo (mjlab + DDS + viewer)."""

    def __init__(
        self,
        checkpoint_file: str | Path,
        task: str = "Unitree-Go2-Flat",
        network: str = "lo",
        domain_id: int = 0,
        device: str | None = None,
        no_terminations: bool = False,
        debug_cmd: bool = True,
    ) -> None:
        """
        Args:
            checkpoint_file: ruta al `.pt` entrenado.
            task: nombre del task mjlab.
            network: interfaz DDS, "lo" para sim local.
            domain_id: DDS domain id.
            device: torch device (None -> auto).
            no_terminations: si True, deshabilita el reset al caerse.
            debug_cmd: si True, imprime cada ~0.5s el comando recibido.
        """
        # Imports diferidos
        import mjlab.tasks  # noqa: F401
        import src.tasks  # noqa: F401
        from mjlab.envs import ManagerBasedRlEnv
        from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
        from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
        from mjlab.utils.torch import configure_torch_backends
        from mjlab.viewer import NativeMujocoViewer

        from unitree_sdk2py.core.channel import (
            ChannelFactoryInitialize,
            ChannelSubscriber,
        )
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import WirelessController_

        configure_torch_backends()
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.checkpoint_file = str(Path(checkpoint_file).expanduser().resolve())
        self.task = task
        self.network = network
        self.domain_id = domain_id
        self._debug_cmd = debug_cmd
        self._NativeMujocoViewer = NativeMujocoViewer

        # ------------------------------------------------------------
        # Env config: lo modificamos para que respeta el comando del teleop
        # ------------------------------------------------------------
        env_cfg = load_env_cfg(task, play=True)
        agent_cfg = load_rl_cfg(task)
        env_cfg.scene.num_envs = 1

        if "twist" in env_cfg.commands:
            # No queremos que el env re-samplee comandos: nosotros los
            # escribimos en vel_command_b cada step desde DDS.
            env_cfg.commands["twist"].resampling_time_range = (1e9, 1e9)
            env_cfg.commands["twist"].rel_standing_envs = 0.0
            # Deshabilitar heading_command para que wz no sea sobrescrito
            # por el controlador interno de heading.
            env_cfg.commands["twist"].heading_command = False
            env_cfg.commands["twist"].ranges.heading = None

        if no_terminations:
            env_cfg.terminations = {}
            print("[Go2Simulator] Terminations disabled (dog will not reset on fall)")

        # ------------------------------------------------------------
        # Construir env + policy
        # ------------------------------------------------------------
        self._env = ManagerBasedRlEnv(cfg=env_cfg, device=self.device, render_mode=None)
        self._env_wrapped = RslRlVecEnvWrapper(self._env, clip_actions=agent_cfg.clip_actions)

        runner_cls = load_runner_cls(task) or MjlabOnPolicyRunner
        self._runner = runner_cls(self._env_wrapped, dict(_asdict(agent_cfg)), device=self.device)
        self._runner.load(
            self.checkpoint_file,
            load_cfg={"actor": True},
            strict=True,
            map_location=self.device,
        )
        self._policy = self._runner.get_inference_policy(device=self.device)
        print(f"[Go2Simulator] Policy cargada desde {self.checkpoint_file}")

        # ------------------------------------------------------------
        # DDS subscriber para WirelessController
        # ------------------------------------------------------------
        ChannelFactoryInitialize(self.domain_id, self.network)
        self._cmd_buffer = _WirelessCommandBuffer()
        self._wc_sub = ChannelSubscriber("rt/wirelesscontroller", WirelessController_)
        self._wc_sub.Init(lambda msg: self._cmd_buffer.update(msg), 10)
        print(f"[Go2Simulator] Escuchando rt/wirelesscontroller en network={self.network}")

        # Rangos del comando (despues de play=True override)
        twist_cfg = env_cfg.commands["twist"]
        self._ranges = {
            "lin_vel_x": tuple(twist_cfg.ranges.lin_vel_x),
            "lin_vel_y": tuple(twist_cfg.ranges.lin_vel_y),
            "ang_vel_z": tuple(twist_cfg.ranges.ang_vel_z),
        }
        print(f"[Go2Simulator] Command clamps: {self._ranges}")

        # Hook que envuelve el policy
        self._hooked_policy = self._make_hook()

    # ----------------------------------------------------------------
    # Hook que inyecta el comando DDS antes de cada llamada al policy
    # ----------------------------------------------------------------
    def _make_hook(self):
        twist = self._env.command_manager.get_term("twist")
        device = self.device
        ranges = self._ranges
        cmd_buffer = self._cmd_buffer
        policy = self._policy

        lin_x_lo, lin_x_hi = ranges["lin_vel_x"]
        lin_y_lo, lin_y_hi = ranges["lin_vel_y"]
        ang_z_lo, ang_z_hi = ranges["ang_vel_z"]

        last_print = [0]
        step_count = [0]
        debug = self._debug_cmd

        def hook(obs):
            vx, vy, wz = cmd_buffer.get_vxvywz()
            vx = max(lin_x_lo, min(lin_x_hi, vx))
            vy = max(lin_y_lo, min(lin_y_hi, vy))
            wz = max(ang_z_lo, min(ang_z_hi, wz))
            cmd = torch.tensor([[vx, vy, wz]], device=device, dtype=twist.vel_command_b.dtype)
            twist.vel_command_b[:] = cmd

            step_count[0] += 1
            if debug and step_count[0] - last_print[0] >= 25:
                print(f"\r[cmd] vx={vx:+.2f}  vy={vy:+.2f}  wz={wz:+.2f}   ",
                      end="", flush=True)
                last_print[0] = step_count[0]

            return policy(obs)

        return hook

    # ----------------------------------------------------------------
    # API publica
    # ----------------------------------------------------------------
    def run(self) -> None:
        """Lanza el viewer y bloquea hasta que se cierre la ventana."""
        print("[Go2Simulator] Abriendo viewer (cierra la ventana o Ctrl+C para salir)")
        viewer = self._NativeMujocoViewer(self._env_wrapped, self._hooked_policy)
        try:
            viewer.run()
        finally:
            self.close()

    def close(self) -> None:
        """Cierra el env limpiamente."""
        try:
            self._env_wrapped.close()
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Acceso para usuarios avanzados
    # ----------------------------------------------------------------
    @property
    def env(self) -> Any:
        return self._env

    @property
    def policy(self) -> Any:
        return self._policy


def _asdict(obj):
    """Helper: dataclasses.asdict alternativo si no es dataclass."""
    from dataclasses import asdict, is_dataclass
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj.__dict__) if hasattr(obj, "__dict__") else dict(obj)
