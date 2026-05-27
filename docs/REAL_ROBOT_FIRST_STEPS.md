---
title: "Primeros pasos con el Go2 físico"
subtitle: "Guía progresiva: desde el ping hasta los primeros movimientos"
author: "go2-perception-stack"
date: \today
geometry: margin=2.5cm
fontsize: 11pt
toc: true
toc-depth: 2
colorlinks: true
linkcolor: blue
urlcolor: blue
---

# Primeros pasos con el Go2 físico

Esta guía lleva paso a paso desde la primera vez que conectas el perro
hasta el primer movimiento real. Cada fase se valida antes de pasar a la
siguiente. **Si algo falla, NO avances; revisa la fase actual antes de
seguir.**

\newpage

# Antes de TODO: seguridad

- **El perro suspendido**: en una mesa, banco o con arnés. Las primeras
  pruebas **NUNCA** en el suelo. Aunque uses Sport Mode (que es robusto),
  si por error mandas un comando agresivo o sueltas el cable, mejor que
  sus patas pateen aire que tu mesa.
- **Zona despejada** de 1.5 m alrededor.
- **Una mano cerca del switch físico** del Go2 para apagarlo si pasa
  algo raro.

---

# Fase 0 — Material y posición física

1. **Carga el Go2** al menos al 50% (mejor 100%). Mira el LED.
2. **Cable Ethernet** entre tu portátil y el puerto Ethernet del Go2
   (suele estar en la parte trasera del cuerpo del perro, bajo una tapa
   de goma).
3. **Suspende el perro** en una mesa para que las patas cuelguen y no
   toquen el suelo. Asegúrate de que el cable Ethernet no se enrolla en
   una pata cuando se mueva.
4. **Enciende el Go2**: pulsa el botón de encendido. Tarda ~30 segundos
   en arrancar (oirás el ventilador y verás LEDs cambiar).
5. **Espera** a que el perro se ponga de pie automáticamente (Sport Mode
   arranca solo). Si está en mesa, las patas se quedarán colgando en
   posición "de pie".

> **Stop si no se enciende o pita raro** → mira el manual del Go2 o
> vuelve al cargador.

---

# Fase 1 — Configurar la red en Windows

El Go2 usa la subred `192.168.123.0/24` por defecto. Su IP es
`192.168.123.161` (estándar Unitree). Tú tienes que ponerte en la misma
subred con una IP distinta — la convención es `192.168.123.222`.

## En Windows 11

1. Abre **"Configuración" → "Red e Internet" → "Ethernet"** (o haz clic
   derecho en el icono de red de la barra de tareas → "Configuración de
   red e Internet").
2. Pincha en el adaptador Ethernet (donde está conectado el cable al
   Go2). Debería decir "Sin Internet" — es normal.
3. Busca **"Configuración IP"** → "Editar".
4. Cambia de **"Automático (DHCP)"** a **"Manual"**.
5. Activa **IPv4**:
   - **Dirección IP**: `192.168.123.222`
   - **Máscara de subred** (Longitud de prefijo de subred): `24`
     (o `255.255.255.0` si pide formato así)
   - **Puerta de enlace**: déjalo vacío.
   - **DNS**: déjalo vacío.
6. Guardar.

## Verifica en Windows (PowerShell)

```powershell
ipconfig
```

Busca tu adaptador Ethernet en la salida. Debes ver:

```
Dirección IPv4. . . . . . . . . . : 192.168.123.222
Máscara de subred . . . . . . . . : 255.255.255.0
```

Y ahora prueba ping al perro:

```powershell
ping 192.168.123.161
```

Deberías ver:

```
Respuesta desde 192.168.123.161: bytes=32 tiempo=2ms TTL=64
Respuesta desde 192.168.123.161: bytes=32 tiempo=1ms TTL=64
...
```

**Si NO responde**: el perro no está enchufado/encendido, o el cable
está mal, o tu adaptador está mal configurado. Vuelve al paso 1.

\newpage

# Fase 2 — Configurar WSL2 para ver al perro

Esto es importante: **WSL2 por defecto NO ve la red de Windows
directamente**, usa una NAT propia. Tienes que activar **modo
"mirrored"** para que WSL vea el mismo adaptador Ethernet y pueda hablar
con el perro.

## Editar `.wslconfig`

En Windows, abre el explorador y ve a `C:\Users\isoto\` (tu carpeta de
usuario). Si no existe el archivo `.wslconfig`, créalo. Si existe,
añade/asegura que tiene esto:

```ini
[wsl2]
networkingMode=mirrored
```

Guarda.

## Reiniciar WSL

En PowerShell:

```powershell
wsl --shutdown
```

Espera 10 segundos y abre Ubuntu de nuevo.

## Verifica en WSL

```bash
ip addr
```

Ahora debes ver el adaptador Ethernet de Windows reflejado dentro de
WSL, con la IP `192.168.123.222`. Algo así:

```
3: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
    inet 192.168.123.222/24 scope global eth0
       valid_lft forever preferred_lft forever
```

**Apunta el nombre del adaptador** (`eth0`, `enp0s5`, `wifi0`...
depende del PC). Lo necesitarás como `--network` en los scripts.

Ahora prueba ping desde WSL:

```bash
ping 192.168.123.161
```

Debe responder. **Si no responde** pero desde Windows sí: el modo
mirrored no se activó. Comprueba `.wslconfig` y reinicia otra vez.

\newpage

# Fase 3 — Comprobar que DDS funciona

El ping te dice que la red baja funciona. Ahora hay que verificar que
DDS habla con el perro.

## Aviso importante sobre `CYCLONEDDS_URI`

Si tienes ROS2 instalado, tu `.bashrc` probablemente exporta
automáticamente `CYCLONEDDS_URI=file:///.../cyclonedds_local.xml`
configurado para `lo` (loopback / simulador). **Eso bloquea el DDS al
robot real**, que va por `eth0` con multicast.

Antes de cualquier test con el robot real, asegúrate de **sobreescribir
explícitamente la variable**:

```bash
export CYCLONEDDS_URI=file:///home/isoto/cyclonedds_go2.xml
echo "$CYCLONEDDS_URI"   # debe imprimir el path correcto
```

Donde `cyclonedds_go2.xml` tiene esta config (interfaz `eth0`, multicast
habilitado, peer al Go2):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain Id="any">
    <General>
      <Interfaces><NetworkInterface name="eth0"/></Interfaces>
      <AllowMulticast>true</AllowMulticast>
    </General>
    <Discovery>
      <Peers><Peer Address="192.168.123.161"/></Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

Para no tener que exportar a mano cada vez, añade al final de tu
`.bashrc`:

```bash
alias dds-sim='export CYCLONEDDS_URI=file://$HOME/robotics/dds_config/cyclonedds_local.xml; echo "DDS SIM (lo)"'
alias dds-real='export CYCLONEDDS_URI=file://$HOME/cyclonedds_go2.xml; echo "DDS REAL (eth0)"'
```

A partir de ahí, en cualquier terminal nueva: `dds-real` cambia al perro
físico, `dds-sim` vuelve al simulador.

## Test de Python (unitree_sdk2py)

Activa el venv y prueba listar topics:

```bash
source ~/robotics/rl_workspace/.venv_rl/bin/activate

# Sustituye eth0 por tu interfaz real de la Fase 2
export CYCLONEDDS_URI='<CycloneDDS><Domain Id="any"><General><Interfaces><NetworkInterface name="eth0"/></Interfaces></General></Domain></CycloneDDS>'

python3 << 'EOF'
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/unitree_sdk2_python").expanduser()))

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

ChannelFactoryInitialize(0, "eth0")  # cambia eth0 por tu interfaz
print("DDS inicializado.")

received = {"count": 0}
def on_msg(msg):
    received["count"] += 1

sub = ChannelSubscriber("rt/lowstate", LowState_)
sub.Init(on_msg, 10)

print("Esperando mensajes de rt/lowstate durante 3s...")
time.sleep(3.0)
print(f"Recibidos {received['count']} mensajes en 3s")
if received["count"] > 0:
    print("OK - el perro publica lowstate y WSL lo recibe.")
else:
    print("FAIL - no llegan mensajes. Revisa red/interfaz/.wslconfig")
EOF
```

**Esperado**: `Recibidos ~1500 mensajes en 3s` (el Go2 publica a ~500 Hz).

Si recibes 0 mensajes, **no pases de aquí** — algo de red está mal.

\newpage

# Fase 4 — Smoke test sin mover el perro

Solo levantarse / sentarse. Movimientos predecibles, sin desplazamiento.

Crea `~/test_real_smoke.py`:

```python
"""Smoke test del Go2 real. Levanta y sienta, NADA MAS."""
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

# Cambia "eth0" por tu interfaz real
NETWORK = "eth0"

print(f"Conectando al Go2 real via {NETWORK}...")
dog = Go2Controller(mode="real", network=NETWORK)
print("Conectado. Esperando 2s antes del primer comando...")
time.sleep(2)

print(">>> StandUp (debe levantar las patas si esta sentado)")
dog.stand_up()
time.sleep(4)

print(">>> Sit (debe sentarse)")
dog.sit()
time.sleep(4)

print(">>> StandUp de nuevo")
dog.stand_up()
time.sleep(4)

print("Smoke test OK")
```

Lánzalo:

```bash
python3 ~/test_real_smoke.py
```

**Esperado** con el perro suspendido:

- StandUp → las patas se enderezan (intentan ponerse de pie pero no
  pisan nada porque está en el aire).
- Sit → las patas se recogen.
- StandUp otra vez → vuelve a enderezar.

> Si el perro hace cualquier cosa rara (twitches violentos, pita):
> apaga con el botón físico.

\newpage

# Fase 5 — Velocidad mínima (perro suspendido)

Solo si la Fase 4 fue perfecta. **El perro sigue suspendido.**

```python
"""Test de velocidad MUY BAJA, perro suspendido."""
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

NETWORK = "eth0"
dog = Go2Controller(mode="real", network=NETWORK)
time.sleep(1)

print(">>> StandUp")
dog.stand_up()
time.sleep(4)

print(">>> Forward 0.1 m/s durante 2 segundos")
dog.set_velocity(vx=0.1, vy=0, wz=0)
time.sleep(2)
dog.stop()
time.sleep(2)

print(">>> Backward 0.1 m/s durante 2 segundos")
dog.set_velocity(vx=-0.1, vy=0, wz=0)
time.sleep(2)
dog.stop()
time.sleep(2)

print(">>> Yaw 0.3 rad/s durante 2 segundos")
dog.set_velocity(vx=0, vy=0, wz=0.3)
time.sleep(2)
dog.stop()

print("Test velocidades OK")
```

**Esperado** suspendido: las patas hacen el movimiento de marcha en el
aire (forward, backward, giro). El cuerpo apenas se mueve porque no hay
tracción.

\newpage

# Fase 6 — Suelo, velocidades pequeñas

**Solo cuando 4 y 5 han ido perfectas.** Bajas el perro al suelo en una
zona despejada de al menos 3 × 3 m.

Mismo script de Fase 5 pero con `vx = 0.2` (en lugar de 0.1) y tiempos
de 3 s. El perro debería avanzar/retroceder/girar suavemente. Si todo
bien, sube progresivamente:

- `0.2 → 0.3 → 0.5` m/s
- Yaw `0.3 → 0.6 → 1.0` rad/s

# Fase 7 — Aplicaciones (YOLO, etc.)

Cuando llegas aquí, ya puedes lanzar tus demos cambiando los dos
parámetros:

```bash
python examples/follow_yolo.py
# Pero edita el script y cambia:
#   MODE = "real"
#   NETWORK = "eth0"   (o tu interfaz)
```

\newpage

# Resumen de fases

| Fase | Lo que validas | Riesgo |
|------|----------------|--------|
| 0 | Físico: carga, posición, encendido | Cero |
| 1 | Red Windows | Cero |
| 2 | Red WSL (mirrored) | Cero |
| 3 | DDS habla con el perro | Cero (solo lee) |
| 4 | StandUp / Sit | Bajo (suspendido) |
| 5 | Velocidad mínima suspendido | Bajo |
| 6 | Velocidad pequeña en suelo | Medio |
| 7 | Aplicaciones reales | Medio-alto |

# Si algo falla — checklist rápido

| Síntoma | Causa probable | Fix |
|---------|----------------|-----|
| Ping a `192.168.123.161` falla en Windows | Adaptador mal configurado o cable | Volver a Fase 1, comprobar `ipconfig` |
| Ping OK en Windows pero falla en WSL | `.wslconfig` no tiene `networkingMode=mirrored` | Editar y `wsl --shutdown` |
| DDS recibe 0 mensajes | `ChannelFactoryInitialize` con interfaz incorrecta | Ajustar a tu nombre real (`eth0`, `enp0s5`...) |
| `StandUp` no hace nada | Perro en modo bloqueado (low-level) o batería baja | Comprobar LEDs, recargar |
| Twitches violentos | El perro recibió un comando con NaN o malformado | Apagar inmediatamente con el botón físico |

# Para parar el perro YA en cualquier momento

1. **Ctrl+C** en la terminal de Python. `Go2Controller` envía `stop()` antes de cerrar.
2. **`dog.sit()`** en una terminal interactiva si la primera no responde.
3. **Botón físico** del Go2 si nada de lo anterior funciona.
