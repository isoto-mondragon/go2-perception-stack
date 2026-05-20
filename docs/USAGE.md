# Uso día a día

Cheat sheet de comandos. Asume que ya hiciste la instalación de
[INSTALL.md](INSTALL.md).

---

## Encendido del PC: cosas a hacer una vez

### Adjuntar la webcam (PowerShell admin)

```powershell
usbipd attach --wsl --busid <TU_BUSID>
```

Si automatizaste con Task Scheduler (ver INSTALL.md §6), ni siquiera esto.

### Verificar (en WSL)

```bash
ls /dev/video*    # debe estar /dev/video0
```

---

## Lanzar el simulador

```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
source ~/robotics/rl_workspace/.venv_rl/bin/activate

python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/mnt/c/Users/<usuario>/Downloads/model_4100.pt \
  --network=lo
```

Verás:

```
[Go2Simulator] Policy cargada desde ...
[Go2Simulator] Escuchando rt/wirelesscontroller en network=lo
[Go2Simulator] Command clamps: {...}
[Go2Simulator] Abriendo viewer ...
```

Y se abre la ventana de MuJoCo con el Go2 quieto de pie.

### Flags útiles

| Flag | Qué hace |
|---|---|
| `--checkpoint-file <path>` | Obligatorio: tu `.pt` |
| `--network lo` | `lo` para sim local, otra para bridge a robot real |
| `--no-terminations` | El perro NO se resetea al caer |
| `--no-debug-cmd` | No imprime el comando recibido |
| `--device cpu` / `--device cuda:0` | Fuerza un device de torch |

---

## Mover al perro: tres opciones

### A) Teclado (rápido para probar)

```bash
python tools/teleop_wireless.py --network=lo --max-lin 1.0 --max-ang 1.0
```

| Tecla | Acción |
|---|---|
| `w` / `s` | forward / backward (+0.3 m/s por pulsación) |
| `a` / `d` | strafe izquierda / derecha |
| `q` / `e` | giro yaw |
| `Shift+W` / `Shift+S` / `Shift+Q` / `Shift+E` | valor máximo de golpe |
| `ESPACIO` | parar todo |
| `Ctrl+C` | salir |

### B) Script Python con `Go2Controller`

```python
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="sim", network="lo")
dog.stand_up()                                # no-op en sim
time.sleep(1)

dog.set_velocity(vx=0.5, vy=0, wz=0); time.sleep(3)
dog.set_velocity(vx=0, vy=0, wz=1.0); time.sleep(2)
dog.set_velocity(vx=0.5, vy=0.3, wz=0); time.sleep(2)
dog.stop()
```

### C) Demos de percepción YOLO

Cada uno con un propósito distinto, ver tabla en [README](../README.md).

```bash
# Sigue a CUALQUIER persona
python examples/follow_yolo.py

# Sigue SOLO a alguien/algo definido por una foto
python examples/follow_reference.py \
  --reference /ruta/a/foto.jpg \
  --target person \
  --conf 0.30 --threshold 0.40

# Perro de vigilancia: patrulla y se gira hacia un intruso
python examples/patrol_and_alert.py

# Buscar y aproximarse a un objeto
python examples/fetch_object.py

# Centinela en sitio (solo rota)
python examples/guard_mode.py
```

---

## Clases encapsuladas (uso programático)

| Clase | Para qué | Cuándo usarla |
|---|---|---|
| `Go2Controller` | API alta nivel (sim/real) | **Siempre** en tu código de aplicación |
| `Go2Simulator` | Encapsula el simulador completo | Lanzar el sim desde un script en lugar de `play_dds.py` |
| `Go2Policy` | Introspeccionar el modelo entrenado | Debug avanzado, ver obs_dim, joint_names, etc. |
| `YoloCaptureThread` | Hilo robusto de webcam + YOLO | Para nuevos demos de percepción |

Ejemplo de cada uno en [README](../README.md) y en los scripts de `examples/`.

---

## Workflow típico de un día

```
1. Encender PC. Abrir WSL.
2. (Si no automatizaste) PowerShell admin → usbipd attach ...
3. cd ~/robotics/rl_workspace/unitree_rl_mjlab
4. source ~/robotics/rl_workspace/.venv_rl/bin/activate
5. Terminal A: python tools/play_dds.py Unitree-Go2-Flat --checkpoint-file=...
6. Terminal B: tu demo elegido (teleop, YOLO, etc.)
7. Trabajar.
8. Ctrl+C en cada terminal al acabar.
```

---

## Personalizar los demos

Cada script en `examples/` tiene sus constantes al principio. Las más útiles:

### `follow_yolo.py` y derivados

| Constante | Qué hace |
|---|---|
| `MODE` | `"sim"` o `"real"` |
| `NETWORK` | `"lo"` (sim) o `"enp5s0"` (real) |
| `TARGET_CLASS` | clase COCO a seguir (person, bottle, cup, cat, etc.) |
| `MAX_VX`, `MAX_WZ` | velocidades máximas |
| `TARGET_BBOX_H_PX` | altura "deseada" del bbox |
| `YOLO_IMGSZ` | resolución de inferencia (baja si va lento) |

### `fetch_object.py`

| Constante | Qué hace |
|---|---|
| `ARRIVED_BBOX_H_FRAC` | % del alto del frame para "ha llegado" |
| `SEARCH_WZ` | velocidad de rotación buscando |

### `follow_reference.py` (flags CLI)

| Flag | Qué hace |
|---|---|
| `--reference` | Path a foto de referencia |
| `--target` | Clase COCO |
| `--conf` | Confianza mínima YOLO |
| `--threshold` | Similitud HSV mínima para "match" |
| `--memory` | Segundos que mantenemos la última detección si YOLO la pierde |

---

## Resolución de problemas frecuentes

| Síntoma | Fix |
|---|---|
| Cámara se "congela" | El thread tiene auto-recovery. Si persiste, re-atacha con usbipd |
| YOLO va a 2 fps | Reduce `YOLO_IMGSZ` a 128 en el demo |
| El perro no responde al teleop | Revisar la terminal de `play_dds.py`: `[cmd] vx=...` debe cambiar |
| Perro gira solo / va hacia atrás | Comando residual: pulsa ESPACIO en el teleop |
| `Missing from play_dds.py` | Olvidaste el task. Comando completo en la sección "Lanzar el simulador" |

Más en [INSTALL.md](INSTALL.md#resolución-de-problemas).
