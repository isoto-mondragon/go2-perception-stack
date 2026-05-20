#!/usr/bin/env python3
"""Ejemplo de proyecto para alumnos: seguir un objetivo con control de velocidad.

Este script:
  1. Define una posicion objetivo en el plano (x, y) en frame del mundo.
  2. Cada tick lee donde estaria el perro (aqui simulamos con cinematica simple,
     pero en un proyecto real vendria de YOLO+camara o de odometria).
  3. Calcula el error y manda (vx, wz) al perro para acercarse.

Funciona EN SIM o EN ROBOT REAL sin cambiar una linea, solo el modo en Go2Controller.

Para probarlo en SIM:
  1. Arranca el simulador en una terminal:
       cd ~/robotics/rl_workspace/unitree_rl_mjlab
       source ~/robotics/rl_workspace/.venv_rl/bin/activate
       python tools/play_dds.py Unitree-Go2-Flat \
         --checkpoint-file=<ruta a tu model_XXXX.pt>
  2. En otra terminal:
       cd ~/robotics/rl_workspace/unitree_rl_mjlab
       source ~/robotics/rl_workspace/.venv_rl/bin/activate
       python examples/follow_demo.py

Para deployar en REAL:
  cambia mode="sim" -> mode="real" y network="lo" -> tu interfaz Ethernet.
"""

import math
import time
import sys
from pathlib import Path

# Hace importable tools/go2_controller.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.go2_controller import Go2Controller


def main():
    # Modo: "sim" en simulador, "real" en el perro fisico.
    dog = Go2Controller(mode="sim", network="lo")

    # En real conviene levantar primero. En sim el FSM ya lo hace.
    dog.stand_up()
    time.sleep(1.0)

    # En esta demo NO leemos camara; movemos al perro en un patron
    # forward -> giro -> forward -> giro... como prueba del controlador.
    # Cuando el alumno meta YOLO, sustituye este patron por la logica de
    # seguimiento: error horizontal -> wz, area del bbox -> vx.
    print("Ejecutando patron de prueba: avanza, gira, repite.")

    try:
        for cycle in range(5):
            print(f"[cycle {cycle}] avanza 3s a 0.3 m/s")
            dog.set_velocity(vx=0.3, vy=0.0, wz=0.0)
            time.sleep(3.0)

            print(f"[cycle {cycle}] gira 2s a 0.5 rad/s")
            dog.set_velocity(vx=0.0, vy=0.0, wz=0.5)
            time.sleep(2.0)

        print("Demo terminada. Parando.")
        dog.stop()

    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
    finally:
        dog.stop()


if __name__ == "__main__":
    main()
