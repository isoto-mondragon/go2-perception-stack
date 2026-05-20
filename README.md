# Go2 Perception & Control Stack

> Pipeline para entrenar políticas RL para el **Unitree Go2** en
> [mjlab](https://github.com/mujocolab/mjlab), desplegarlas en simulador
> con control por DDS, y usar esa abstracción para construir aplicaciones
> de percepción (seguimiento, vigilancia, búsqueda) tanto en **simulación**
> como en el **robot físico**.

![arquitectura](docs/arch.png)

---

## 🧩 ¿Qué incluye este repo?

| Carpeta | Contenido |
|---|---|
| [notebooks/](notebooks/) | Notebook de Colab para entrenar una policy RL de velocity tracking del Go2 |
| [tools/](tools/) | Clases encapsuladas: `Go2Simulator`, `Go2Controller`, `Go2Policy`, `YoloCaptureThread`. Lanzadores `play_dds.py` y `teleop_wireless.py` |
| [examples/](examples/) | 6 demos de aplicación: seguimiento básico, follow con YOLO, follow con referencia, patrulla con alerta, search+approach, modo centinela |
| [docs/](docs/) | Guías detalladas de instalación, uso día a día, y transferencia sim→real |
| [models/](models/) | Donde colocar el `model_XXXX.pt` entrenado |

---

## 🎯 ¿Qué hace el sistema?

```
┌──────────────────────────────────────────────┐
│  TU CÓDIGO (perception + lógica)             │
│   - cámara → YOLO/MediaPipe → detección      │
│   - calcular (vx, vy, wz)                    │
│   - dog.set_velocity(vx, vy, wz)             │
└──────────────────┬───────────────────────────┘
                   │  MISMA API
        ┌──────────┴──────────┐
        ▼                     ▼
 ┌──────────────┐      ┌──────────────┐
 │  mode="sim"  │      │ mode="real"  │
 │              │      │              │
 │ play_dds.py  │      │ SportClient  │
 │ (mjlab + RL) │      │ (firmware    │
 │              │      │  on-board)   │
 └──────────────┘      └──────────────┘
```

La clase `Go2Controller` abstrae sim vs real: el código de aplicación es
**idéntico**, solo cambian dos parámetros (`mode` y `network`).

En **simulador** la locomoción la realiza una **policy RL** entrenada con
[unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab) sobre
[mjlab](https://github.com/mujocolab/mjlab) (`scripts/train.py`).

En **real** la locomoción la realiza el **Sport Mode** on-board del Go2,
expuesto vía la SDK oficial de Unitree.

---

## 🚀 Quick start

> Asume que ya tienes WSL2 Ubuntu 22.04 + el setup base de mjlab + un `.pt`
> entrenado. Si empiezas de cero, lee primero [docs/INSTALL.md](docs/INSTALL.md).

### 1. Clonar este repo dentro de `unitree_rl_mjlab`

```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
git clone https://github.com/isoto-mondragon/go2-perception-stack.git stack
# luego copia las carpetas tools/ y examples/ encima del repo de mjlab:
cp -r stack/tools/* tools/
cp -r stack/examples/* examples/
```

(También puedes hacer symlinks o un script de install que automatice esto;
ver [docs/INSTALL.md](docs/INSTALL.md).)

### 2. Activar venv y lanzar el simulador

```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/rl_workspace/unitree_rl_mjlab

python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/ruta/a/tu/model_XXXX.pt \
  --network=lo
```

### 3. Controlarlo (3 opciones, terminal aparte)

```bash
# A) Teclado (probar rápido)
python tools/teleop_wireless.py --network=lo --max-lin 1.0 --max-ang 1.0

# B) Sigue una persona con YOLO + webcam
python examples/follow_yolo.py

# C) Patrulla y se gira hacia ti si te detecta
python examples/patrol_and_alert.py
```

---

## 📚 Documentación detallada

| Doc | Para qué |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Instalación desde cero (WSL2 → CycloneDDS → SDK → mjlab → este repo). Solo la primera vez. |
| [docs/USAGE.md](docs/USAGE.md) | Comandos del día a día. Cómo lanzar simulador, teleop, demos, ajustar parámetros. |
| [docs/SIM_TO_REAL.md](docs/SIM_TO_REAL.md) | Cómo pasar de simulador al robot físico. Red, seguridad, test mínimo. |
| [notebooks/train_go2_velocity.ipynb](notebooks/train_go2_velocity.ipynb) | Entrenamiento de la policy en Colab (GPU T4). |

---

## 🧪 Demos disponibles

| Script | Concepto | Caso de uso |
|---|---|---|
| `examples/follow_demo.py` | Patrón fijo sin percepción | Validación de comandos |
| `examples/follow_yolo.py` | Sigue a CUALQUIER persona | Demo básico de seguimiento |
| `examples/follow_reference.py` | Sigue SOLO a una persona/objeto definidos por una foto | Reidentificación visual |
| `examples/patrol_and_alert.py` | Máquina de estados: patrulla + reacciona si detecta intruso | Robot de vigilancia |
| `examples/fetch_object.py` | Búsqueda + aproximación a un objeto | "Ve a por la botella" |
| `examples/guard_mode.py` | Centinela: solo rota la cabeza, no se mueve | Torreta de cámara |

---

## 🔄 Sim → Real

Cuando hayas validado tu aplicación en simulador, **el mismo código corre
en el robot físico**. Solo cambias dos parámetros:

```python
# Antes (sim):
dog = Go2Controller(mode="sim", network="lo")
# Ahora (real):
dog = Go2Controller(mode="real", network="enp5s0")
```

> ⚠️ **Importante** — En `mode="real"` la locomoción la realiza el firmware
> **Sport Mode** del Go2, NO tu `.pt` entrenado. Tu policy se usa en sim
> para iterar la lógica; en real, Sport Mode (rock-solid) ejecuta los
> comandos de velocidad. Esto es **lo deseable** para la mayoría de
> proyectos. Si quieres demostrar **sim2real puro** (tu `.pt` controlando
> los motores físicos directamente), ver el apéndice en
> [docs/SIM_TO_REAL.md](docs/SIM_TO_REAL.md#apéndice-añadir-un-backend-lowlevel-futuro).

Ver [docs/SIM_TO_REAL.md](docs/SIM_TO_REAL.md) para el procedimiento completo
(red, comprobaciones, test mínimo seguro).

---

## 🛠️ Stack técnico

- **mjlab** (MuJoCo Warp) — simulador físico y framework RL
- **rsl_rl** (PPO) — algoritmo de entrenamiento
- **unitree_rl_mjlab** — config del task `Unitree-Go2-Flat`
- **CycloneDDS** + **unitree_sdk2_python** — comunicación con el robot
- **YOLOv8** (ultralytics) — detección de objetos
- **OpenCV** — captura webcam + visualización

---

## 📜 Créditos

Este proyecto se apoya en y extiende:

- [unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab) (Apache-2.0)
- [mjlab](https://github.com/mujocolab/mjlab) (Apache-2.0)
- [Unitree SDK2](https://github.com/unitreerobotics/unitree_sdk2) (BSD-3-Clause)
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) (AGPL-3.0)
