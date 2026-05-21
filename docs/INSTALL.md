# Instalación desde cero

Esta guía lleva desde un PC con Windows recién instalado hasta tener
todo funcionando.

> Si solo quieres saber cómo lanzar los scripts día a día, mira
> [USAGE.md](USAGE.md).

---

## 1. WSL2 + Ubuntu 22.04

En PowerShell **como administrador**:

```powershell
wsl --install -d Ubuntu-22.04
```

Reinicia. Al volver, abre Ubuntu y crea usuario+contraseña.

## 2. Paquetes del sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake git pkg-config \
  libyaml-cpp-dev libboost-all-dev libeigen3-dev \
  libspdlog-dev libfmt-dev libglfw3-dev \
  python3-pip python3-venv v4l-utils
```

## 3. CycloneDDS + Unitree SDK2

CycloneDDS:

```bash
mkdir -p ~/robotics && cd ~/robotics
git clone https://github.com/eclipse-cyclonedds/cyclonedds.git
cd cyclonedds
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=../install -DBUILD_DDSPERF=ON
cmake --build . --target install -- -j$(nproc)
```

Unitree SDK2 (C++):

```bash
cd ~/robotics
git clone https://github.com/unitreerobotics/unitree_sdk2.git
cd unitree_sdk2 && mkdir build && cd build
sudo cmake .. -DCMAKE_INSTALL_PREFIX=/opt/unitree_robotics
sudo make install
```

Unitree SDK2 Python:

```bash
cd ~/robotics
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
```

## 4. Clonar mjlab y este repo

```bash
cd ~/robotics
mkdir -p rl_workspace && cd rl_workspace
git clone https://github.com/unitreerobotics/unitree_rl_mjlab.git
cd unitree_rl_mjlab

# Crear venv
python3 -m venv ~/robotics/rl_workspace/.venv_rl
source ~/robotics/rl_workspace/.venv_rl/bin/activate
pip install -U pip

# Instalar mjlab con fixes obligatorios de versiones
pip install -e .
pip install --force-reinstall \
  "mujoco-warp @ git+https://github.com/google-deepmind/mujoco_warp@40ef9d6acf2584e89cac615fcbf0cb18e05b2c97"
pip install --force-reinstall "warp-lang==1.12.1"

# SDK python en el venv
cd ~/robotics/unitree_sdk2_python
pip install -e .

# Webcam + YOLO
pip install ultralytics opencv-python

# Volver al directorio del repo mjlab
cd ~/robotics/rl_workspace/unitree_rl_mjlab
```

### Clonar este repo (los `tools/` y `examples/` de aplicación)

```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab
git clone https://github.com/isoto-mondragon/go2-perception-stack.git stack

# unitree_rl_mjlab NO trae carpetas tools/ ni examples/ por defecto,
# las creamos antes de copiar:
mkdir -p tools examples

# Copiar nuestros tools/examples al repo de mjlab
cp -r stack/tools/*    tools/
cp -r stack/examples/* examples/
```

> Si prefieres mantener la separación, puedes usar symlinks en lugar de cp.
> Pero copiar es más simple y suficiente para empezar.

## 5. Verificar instalación

```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
python -c "import torch, mujoco, mjlab, ultralytics, cv2; \
           import unitree_sdk2py; print('OK')"
```

Debe imprimir `OK`. Si algún `import` falla, vuelve al paso correspondiente.

## 6. Webcam en WSL2 (opcional, para demos con cámara)

WSL2 no ve la webcam de Windows por defecto. Necesitas **usbipd-win**.

En Windows, descarga el `.msi` desde
<https://github.com/dorssel/usbipd-win/releases/latest>, instala, **reinicia**.

Luego en PowerShell admin:

```powershell
usbipd list                          # busca tu webcam, apunta BUSID (p.ej. 1-1)
usbipd bind --busid 1-1              # solo una vez por dispositivo
usbipd attach --wsl --busid 1-1      # cada vez que reinicies Windows
```

En WSL:

```bash
sudo usermod -a -G video $USER       # solo una vez
# Cierra y vuelve a abrir Ubuntu para que aplique
```

Comprueba que ves la cámara:

```bash
ls /dev/video*
python3 -c "import cv2; c=cv2.VideoCapture(0, cv2.CAP_V4L2); \
  c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')); \
  ok,f=c.read(); print('OK' if ok else 'FAIL', f.shape if ok else '')"
```

Debe imprimir `OK (480, 640, 3)`.

> **Tip**: para evitar tener que hacer `attach` cada vez, configura
> Task Scheduler de Windows con la acción
> `"C:\Program Files\usbipd-win\usbipd.exe" attach --wsl --busid 1-1`
> al iniciar sesión.

## 7. Obtener una policy entrenada (.pt)

Tienes dos opciones:

### Opción A — Entrenar tu propia policy

Abre [`notebooks/train_go2_velocity.ipynb`](../notebooks/train_go2_velocity.ipynb)
en Google Colab con runtime T4. Ejecuta de arriba abajo (instala deps,
arranca TensorBoard, lanza training). Para cuando `Train/mean_reward > 65`
(~3000–5000 iteraciones, 1.5–2h). Descarga el `model_XXXX.pt` resultante.

### Opción B — Usar una pre-entrenada

Si tu instructor te facilita un `.pt`, ponlo en `models/` o donde te
indique.

Copia el `.pt` a una ruta accesible desde WSL, por ejemplo
`/mnt/c/Users/<tu_usuario>/Downloads/model_4100.pt`.

## 8. Primer test end-to-end

Lanza el simulador en una terminal:

```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/rl_workspace/unitree_rl_mjlab
python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=/mnt/c/Users/<usuario>/Downloads/model_4100.pt \
  --network=lo
```

Debe abrirse una ventana de MuJoCo con el Go2 quieto de pie.

Lanza el teleop en otra terminal:

```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate
cd ~/robotics/rl_workspace/unitree_rl_mjlab
python tools/teleop_wireless.py --network=lo --max-lin 1.0 --max-ang 1.0
```

Pulsa `Shift+W` → el perro debe avanzar. `Q`/`E` → girar. `ESPACIO` → parar.

✅ Si llegas hasta aquí, la instalación está completa.

---

## Resolución de problemas

| Síntoma | Causa | Fix |
|---|---|---|
| `free(): invalid pointer` | Mismatch versiones CycloneDDS C/C++ | Asegurar que la SDK Unitree (`/opt/unitree_robotics`) esté instalada antes de compilar el resto |
| `ModuleNotFoundError: torch` | Venv distinto activado | `source ~/robotics/rl_workspace/.venv_rl/bin/activate` |
| `No module named src.tasks` | No estás en el directorio del repo mjlab | `cd ~/robotics/rl_workspace/unitree_rl_mjlab` |
| `tile_cholesky / fill_mode` | Versión de mujoco-warp incorrecta | Reinstala con el commit pinned (paso 4) |
| `Permission denied /dev/video0` | Falta grupo video | `sudo usermod -a -G video $USER` + reabrir terminal |
| Cámara no aparece (`/dev/video0` no existe) | usbipd no adjuntada | Repite `usbipd attach --wsl --busid <id>` en PowerShell admin |
