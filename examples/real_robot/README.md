# examples/real_robot/

Scripts progresivos para validar el funcionamiento del Go2 físico paso
a paso. **Lánzalos en orden numérico.** No pases al siguiente si el
anterior no terminó OK.

Cada script tiene una constante `NETWORK = "eth0"` cerca del inicio que
debes ajustar al nombre de tu interfaz Ethernet de WSL (mira con
`ip addr`).

| Script | Fase | Qué hace | Riesgo | Perro |
|--------|------|----------|--------|-------|
| `01_dds_check.py` | 3 | Solo LEE `rt/lowstate` 3 s para validar DDS | Cero | Suspendido |
| `02_smoke_test.py` | 4 | StandUp / Sit / StandUp | Bajo | Suspendido |
| `03_velocity_suspended.py` | 5 | Velocidad muy baja (0.1 m/s, 0.3 rad/s) | Bajo | Suspendido |
| `04_velocity_floor.py` | 6 | Velocidad pequeña → media (0.2 → 0.5 m/s) | Medio | En el suelo |

Para el contexto completo y las precauciones, ver
[`docs/REAL_ROBOT_FIRST_STEPS.md`](../../docs/REAL_ROBOT_FIRST_STEPS.md).

## Cómo lanzarlos

```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab    # o donde tengas los tools/
source ~/robotics/rl_workspace/.venv_rl/bin/activate

# Fase 3
python3 examples/real_robot/01_dds_check.py

# Fase 4 (perro suspendido)
python3 examples/real_robot/02_smoke_test.py

# Fase 5 (perro suspendido)
python3 examples/real_robot/03_velocity_suspended.py

# Fase 6 (suelo despejado)
python3 examples/real_robot/04_velocity_floor.py
```

## Para parar el perro YA

1. **Ctrl+C** en la terminal del script. Cada script llama a
   `dog.stop()` en su bloque `finally`.
2. Si no responde, **botón físico** del Go2.
