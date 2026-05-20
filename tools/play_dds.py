#!/usr/bin/env python3
"""Wrapper CLI fino sobre Go2Simulator.

Lanza el simulador mjlab + DDS bridge. La logica esta en go2_simulator.py;
este script solo parsea args y llama a Go2Simulator(...).run().

Uso:
    python tools/play_dds.py Unitree-Go2-Flat \
      --checkpoint-file=/path/to/model.pt \
      --network=lo
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import tyro

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.go2_simulator import Go2Simulator


@dataclass(frozen=True)
class PlayDdsConfig:
    """Config del simulador DDS."""

    checkpoint_file: str
    """Ruta al checkpoint .pt entrenado."""
    network: str = "lo"
    """Interfaz DDS. 'lo' para sim, otra para bridge a robot real."""
    device: str | None = None
    """torch device (None -> auto)."""
    no_terminations: bool = False
    """Si True, deshabilita el reset al caerse el perro."""
    no_debug_cmd: bool = False
    """Si True, NO imprime el comando recibido por DDS."""


def main():
    # Importa mjlab.tasks y src.tasks para popular el registry
    import mjlab.tasks  # noqa: F401
    import src.tasks  # noqa: F401
    from mjlab.tasks.registry import list_tasks

    all_tasks = list_tasks()
    chosen_task, remaining_args = tyro.cli(
        tyro.extras.literal_type_from_choices(all_tasks),
        add_help=False,
        return_unknown_args=True,
    )

    args = tyro.cli(
        PlayDdsConfig,
        args=remaining_args,
        prog=f"{sys.argv[0]} {chosen_task}",
    )

    sim = Go2Simulator(
        checkpoint_file=args.checkpoint_file,
        task=chosen_task,
        network=args.network,
        device=args.device,
        no_terminations=args.no_terminations,
        debug_cmd=not args.no_debug_cmd,
    )
    sim.run()


if __name__ == "__main__":
    main()
