"""Encapsula el modelo RL entrenado del Go2.

Esta clase carga un checkpoint `.pt` de mjlab+rsl_rl y expone:
- Metadata (joint names, action scale, observation dims, etc.)
- Una funcion `predict(obs)` para inferencia.
- Acceso al modulo torch subyacente para usuarios avanzados.

Uso tipico:
    from tools.go2_policy import Go2Policy

    policy = Go2Policy(
        checkpoint_file="model_4100.pt",
        task="Unitree-Go2-Flat",
    )
    print(policy.summary())

    # Inferencia desde codigo (avanzado)
    obs = torch.zeros((1, policy.obs_dim))
    action = policy.predict(obs)

Para los alumnos no es necesario tocar esta clase: `Go2Simulator` la usa
internamente. Esta aqui por si alguien quiere experimentar con el modelo
directamente.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch


class Go2Policy:
    """Wrapper alrededor de un checkpoint .pt entrenado con mjlab+rsl_rl."""

    def __init__(
        self,
        checkpoint_file: str | Path,
        task: str = "Unitree-Go2-Flat",
        device: str | None = None,
    ) -> None:
        """Carga el modelo desde el checkpoint.

        Args:
            checkpoint_file: ruta absoluta o relativa al `.pt`.
            task: nombre del task de mjlab (define la estructura del env y la red).
            device: torch device. None -> auto (cuda si hay, else cpu).
        """
        # Imports diferidos para no penalizar al cargar el modulo
        import mjlab.tasks  # noqa: F401
        import src.tasks  # noqa: F401
        from mjlab.envs import ManagerBasedRlEnv
        from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
        from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
        from mjlab.utils.torch import configure_torch_backends

        configure_torch_backends()
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.task = task
        self.checkpoint_file = str(Path(checkpoint_file).expanduser().resolve())

        # Cargar configs
        env_cfg = load_env_cfg(task, play=True)
        agent_cfg = load_rl_cfg(task)
        env_cfg.scene.num_envs = 1

        # Crear env minimal solo para tener obs/action shapes
        self._env = ManagerBasedRlEnv(cfg=env_cfg, device=self.device, render_mode=None)
        self._env_wrapped = RslRlVecEnvWrapper(self._env, clip_actions=agent_cfg.clip_actions)

        # Cargar runner + policy
        runner_cls = load_runner_cls(task) or MjlabOnPolicyRunner
        self._runner = runner_cls(self._env_wrapped, asdict(agent_cfg), device=self.device)
        self._runner.load(
            self.checkpoint_file,
            load_cfg={"actor": True},
            strict=True,
            map_location=self.device,
        )
        self._policy = self._runner.get_inference_policy(device=self.device)

        # Guardar refs a env_cfg y agent_cfg para introspeccion
        self._env_cfg = env_cfg
        self._agent_cfg = agent_cfg

    # ------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------
    @property
    def obs_dim(self) -> int:
        """Dimension del vector de observacion que espera la red."""
        obs_space = self._env_wrapped.observation_space
        return int(obs_space.shape[-1])

    @property
    def action_dim(self) -> int:
        """Dimension del vector de accion que produce la red."""
        return int(self._env_wrapped.action_space.shape[-1])

    @property
    def observation_terms(self) -> list[str]:
        """Lista de nombres de los terms que componen la observacion del actor."""
        return list(self._env.observation_manager.active_terms.get("actor", []))

    @property
    def joint_names(self) -> list[str]:
        """Nombres de los joints en el orden que el policy espera."""
        robot = self._env.scene["robot"]
        return list(robot.joint_names)

    @property
    def action_scale(self) -> float:
        """Factor de escala que se multiplica a la salida cruda del policy."""
        ja = self._env.action_manager.get_term("joint_pos")
        scale = ja._scale
        if isinstance(scale, torch.Tensor):
            return float(scale.flatten()[0].item())
        return float(scale)

    # ------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------
    def predict(self, obs: torch.Tensor) -> torch.Tensor:
        """Run policy(obs) -> action. Espera tensor [B, obs_dim] en self.device."""
        with torch.no_grad():
            return self._policy(obs)

    # ------------------------------------------------------------
    # Acceso para usuarios avanzados
    # ------------------------------------------------------------
    @property
    def env(self) -> Any:
        """El env de mjlab subyacente (avanzado)."""
        return self._env

    @property
    def env_wrapped(self) -> Any:
        """El env envuelto con RslRlVecEnvWrapper (avanzado)."""
        return self._env_wrapped

    @property
    def runner(self) -> Any:
        """El runner de rsl_rl que carga la policy (avanzado)."""
        return self._runner

    @property
    def torch_module(self) -> torch.nn.Module:
        """El callable de inferencia (incluye normalizer y MLP)."""
        return self._policy

    # ------------------------------------------------------------
    # Display
    # ------------------------------------------------------------
    def summary(self) -> str:
        """String con un resumen legible del modelo."""
        lines = [
            f"Go2Policy",
            f"  checkpoint:  {self.checkpoint_file}",
            f"  task:        {self.task}",
            f"  device:      {self.device}",
            f"  obs_dim:     {self.obs_dim}",
            f"  action_dim:  {self.action_dim}",
            f"  action_scale: {self.action_scale}",
            f"  joints:      {self.joint_names}",
            f"  obs terms:   {self.observation_terms}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"Go2Policy(task={self.task!r}, obs_dim={self.obs_dim}, action_dim={self.action_dim})"

    # ------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------
    def close(self) -> None:
        """Libera el env. Llamar al terminar si quieres ser limpio."""
        try:
            self._env_wrapped.close()
        except Exception:
            pass
