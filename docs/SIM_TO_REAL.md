# De simulador a robot real

Cómo desplegar tu aplicación (la que probaste en simulador) en el Go2 físico.

---

## Lectura previa OBLIGATORIA: dos enfoques de "real"

Hay **dos formas distintas** de hacer que el Go2 físico ejecute tu app, y
es importante entender la diferencia antes de seguir.

### Enfoque A — Sport Mode (el que implementa este repo)

`Go2Controller(mode="real")` llama por DDS al servicio **Sport Mode**
on-board del Go2. Sport Mode es el firmware oficial que viene de fábrica:
es el mismo código que mueve al perro cuando lo controlas con la app
móvil de Unitree o con el mando RC.

```
TU SCRIPT  →  SportClient.Move(vx, vy, wz)  →  firmware Sport Mode
              ↓ por Ethernet                    (cerrado, on-board)
                                                ↓
                                                MOTORES
```

**Importante**: en este enfoque tu **`.pt` entrenado NO se usa**. El
perro se mueve con el código de Unitree. Tu policy RL del simulador
sirve para iterar la **lógica de aplicación** (percepción, planificación,
decisión), pero la **locomoción** la hace el firmware.

| Ventajas | Limitaciones |
|---|---|
| **Rock-solid**: el perro no se cae bajo comandos razonables | No es "sim2real" estricto: el `.pt` no llega al hardware |
| Setup mínimo: cable Ethernet y enchufar el perro | Limitado a lo que Sport Mode expone (vx, vy, wz, StandUp, Sit, gestos predefinidos) |
| Seguro para clase / demos públicas | No permite gait/comportamientos custom |
| Sport Mode tiene años de tuning | |

**Es lo que usa este repo por defecto.** Para la mayoría de proyectos
(seguimiento YOLO, navegación, patrulla, etc.) es la opción correcta.

### Enfoque B — Deploy de tu `.pt` en hardware (sim2real puro)

El Go2 también admite **control de bajo nivel**: tú publicas torques /
posiciones a cada uno de los 12 motores directamente, saltándote Sport
Mode. Aquí **sí se usa tu `.pt`** como en simulador: la red infiere
acciones de joint y un controlador C++ las publica.

```
TU SCRIPT  →  set_velocity(vx, vy, wz)         (igual que sim)
              ↓
              go2_ctrl (C++ binario)
              ↓ carga tu policy.onnx
              ↓ infiere 12 acciones de joint
              ↓ publica rt/lowcmd (PD + target_q)
              ↓ por Ethernet
                                                ↓
                                                MOTORES (sin Sport Mode)
```

| Ventajas | Limitaciones |
|---|---|
| **Sim2real real**: tu RL training se valida en hardware | **Frágil**: tu policy puede caer en real igual que en sim si no aguanta el sim2real gap |
| Permite gait/movimientos custom (parkour, marcha lateral rápida, etc.) | Requiere poner el Go2 en `debug mode` (`L2+R2`) — Sport Mode se apaga |
| Es lo que hace la investigación seria de locomoción | Más pasos manuales, más riesgo si algo va mal |
|  | Sin dominio randomization fuerte en training → el perro se cae |
|  | Hay que compilar `go2_ctrl` (más complejidad) |

**Este enfoque NO está cableado en `Go2Controller`.** Lo dejamos como
extensión futura cuando se quiera demostrar sim2real puro o entrenar
comportamientos no expuestos por Sport Mode. Ver
[Apéndice: añadir un backend lowlevel](#apéndice-añadir-un-backend-lowlevel-futuro).

### ¿Cuál uso?

| Tu caso | Enfoque recomendado |
|---|---|
| Proyecto de clase: alumnos hacen YOLO + control alto nivel | **A — Sport Mode** |
| Demo "el perro me sigue" / "el perro patrulla" / "ve a por el objeto" | **A — Sport Mode** |
| Quieres validar que la policy entrenada **realmente anda en el robot** | **B — `.pt` en hardware** |
| Investigación de locomoción / gait custom | **B — `.pt` en hardware** |
| Primera vez que tocas el robot | **A** (siempre, hasta familiarizarte) |

A partir de aquí, el resto del documento describe el **enfoque A** (lo
que ya tienes implementado). Para el enfoque B, ver el apéndice al
final.

---

## Idea clave (enfoque A)

`Go2Controller` está diseñado para que el **mismo código** funcione en
ambos contextos. Lo único que cambian son dos parámetros:

```python
# Antes (sim):
dog = Go2Controller(mode="sim", network="lo")
# Ahora (real):
dog = Go2Controller(mode="real", network="enp5s0")
```

**Lo que ocurre por debajo en cada caso**:

| | Modo sim | Modo real (enfoque A) |
|---|---|---|
| Backend | Publica `WirelessController_` por DDS al simulador | Llama a `SportClient.Move(vx, vy, wz)` |
| Locomoción | Tu `.pt` entrenado en mjlab | **Sport Mode** (firmware on-board del Go2) |
| `.pt` se usa | Sí | No |
| Red | `lo` (loopback en WSL) | Ethernet directo al perro |

---

## Procedimiento paso a paso

### 1. Preparar el Go2 físico

1. **Cargar la batería** completamente.
2. **Posicionar el robot suspendido** (mesa, arnés, trípode). NUNCA hacer
   las primeras pruebas con el robot en el suelo.
3. **Encender el Go2**. Esperar ~30 s a que termine el arranque.
4. El Go2 está en **Sport Mode** por defecto al arrancar (se pone de pie
   solo tras unos segundos).

### 2. Conectar el PC al robot

#### Por Ethernet directo

Conecta un cable Ethernet entre tu PC y el puerto del Go2. Configura tu
interfaz en Windows o WSL con IP estática:

- **IP**: `192.168.123.222`
- **Máscara**: `255.255.255.0`
- **Gateway**: (vacío)

Verifica conectividad:

```bash
ping 192.168.123.161
# Debes ver respuesta
```

#### Identificar el nombre de la interfaz Ethernet en WSL

```bash
ip addr
# Busca algo tipo enp5s0, eno1, eth0...
```

Apunta ese nombre — lo pasarás como `network=`.

### 3. Adaptar tu código de aplicación

En tu script (sea `follow_yolo.py`, `patrol_and_alert.py`, o el tuyo
propio), cambia las dos constantes:

```python
MODE = "real"
NETWORK = "enp5s0"   # tu interfaz Ethernet
```

Si el script usa `argparse`, pasa por CLI:

```bash
python examples/follow_reference.py \
  --reference foto.jpg --target person \
  --mode real --network enp5s0
```

### 4. Smoke test antes de cualquier cosa

Con el perro **suspendido**, ejecuta esto antes de la app de verdad:

```python
# real_smoke_test.py
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path("~/robotics/rl_workspace/unitree_rl_mjlab").expanduser()))
from tools.go2_controller import Go2Controller

dog = Go2Controller(mode="real", network="enp5s0")

# Test 1: levantarse / sentarse (sin desplazamiento)
print("Test 1: stand_up")
dog.stand_up()
time.sleep(3)

print("Test 1: sit")
dog.sit()
time.sleep(3)

# Test 2: velocidad mínima
print("Test 2: stand_up y avanzar 0.1 m/s")
dog.stand_up()
time.sleep(2)
dog.set_velocity(vx=0.1, vy=0, wz=0)
time.sleep(2)
dog.stop()

print("Smoke test OK")
```

Ejecuta:

```bash
python real_smoke_test.py
```

Si los 3 pasos van bien, **ahora sí** puedes bajarlo al suelo.

### 5. Lanzar tu aplicación

```bash
# Ejemplo: follow_reference con cámara del laptop
python examples/follow_reference.py \
  --reference /mnt/c/.../foto.jpg \
  --mode real --network enp5s0 \
  --conf 0.30 --threshold 0.40
```

---

## Diferencias entre sim y real (importantes)

### Lo que es IGUAL

La API (`set_velocity`, `stop`, `stand_up`, `sit`).
El código de tu aplicación (perception + lógica).
Las constantes (vx_max, deadzone, kp, etc.) suelen funcionar parecido.

### Lo que CAMBIA

**Sport Mode es mucho más robusto** que la policy RL del sim. En real
el perro NO se cae aunque le des comandos raros — el firmware compensa.

**Cámara**: en real lo natural es usar la **cámara on-board del Go2**
(no la webcam del laptop). Esto requiere suscribirse al stream de video
por DDS. Ver "Cámara on-board" abajo.

**Latencia**: real puede tener más jitter (Ethernet vs loopback). Si
ves comportamiento oscilante, baja las ganancias (`KP_YAW`, `KP_FORWARD`).

**Seguridad**: el perro pesa ~15 kg. Asume que cualquier comando
puede salir mal. Mantén una zona despejada y un botón de emergencia
físico a mano.

---

## Cámara on-board del Go2 (para deploy real)

Para usar la cámara del propio Go2 en lugar de la webcam:

1. En tu código, en vez de `cv2.VideoCapture(0)`, usa el cliente de
   video de la SDK Unitree.
2. La SDK expone `VideoClient` (ver
   [unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python)
   → ejemplos de video).

Esto es un ejercicio adicional — no lo cubrimos aquí pero los demos
están preparados para que sea un cambio de UNAS POCAS LÍNEAS (sustituir
el lector de frames).

---

## Tabla de seguridad

| Situación | Qué hacer |
|---|---|
| El perro hace algo inesperado | `Ctrl+C` en la terminal. El controller publica `set_velocity(0,0,0)` antes de cerrar. |
| Vas a hacer un cambio de código grande | Suspende el perro o ponlo en `Damp` antes de relanzar |
| El perro no responde a comandos | Revisa que `ping 192.168.123.161` funciona. Si no, problema de red |
| Quieres parar el perro INMEDIATAMENTE | Botón físico del Go2, O sentarlo: `dog.sit()` |

---

## Checklist antes del primer despliegue (enfoque A)

- [ ] PC en `192.168.123.222`, ping a `192.168.123.161` funciona
- [ ] Go2 cargado, en Sport Mode, suspendido en mesa/arnés
- [ ] Zona despejada de obstáculos
- [ ] `real_smoke_test.py` pasa todos los pasos
- [ ] Sabes cómo parar el perro (Ctrl+C, sit, botón físico)
- [ ] Si usas cámara: webcam o stream on-board funcionando

Si los 6 puntos son ✓, adelante con tu app.

---

## Apéndice: añadir un backend `lowlevel` (futuro)

Si en algún momento quieres ejecutar **tu `.pt` directamente en el robot
físico** (enfoque B descrito al inicio de este documento), estos son los
pasos a alto nivel. **No están implementados** en este repo todavía,
pero el camino está claro:

### 1. Compilar `go2_ctrl`

`unitree_rl_mjlab` trae un controlador C++ en
`deploy/robots/go2/` que:
- Subscribe a `rt/lowstate` y `rt/wirelesscontroller`.
- Carga `policy.onnx`.
- Cada 20ms infiere acciones y publica `rt/lowcmd` con PD + target_q.

Hay que **compilarlo** con varios fixes (RPATH para que las dependencias
de DDS y ONNX se resuelvan bien). En el árbol de `unitree_rl_mjlab` ya
está el código C++ + CMakeLists. La compilación está documentada
en el README de `unitree_rl_mjlab` (sección 4 — Deployment).

Resumen de pasos:
```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab/deploy/robots/go2
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
# Resultado: build/go2_ctrl
```

### 2. Poner el Go2 en modo `debug` (low-level)

1. Suspender el perro en mesa o arnés.
2. Encender el Go2. Esperar a que entre en estado de pie.
3. **Pulsar `L2 + B` en el mando RC** → el robot se sienta.
4. **Pulsar `L2 + A`** → entra en `damping` (motores flojos).
5. **Pulsar `L2 + R2`** (la combinación exacta puede variar según versión de firmware) → entra en `debug mode`. Sport Mode queda suspendido. Ahora `rt/lowcmd` está activo y los motores aceptan tus comandos.

> Una vez en debug mode, **cualquier comando torque/posición** que publiques a `rt/lowcmd` va directo a los motores. Asegurate de tener `go2_ctrl` ya configurado para publicar valores sensatos antes de entrar a este modo.

### 3. Lanzar `go2_ctrl`

```bash
cd ~/robotics/rl_workspace/unitree_rl_mjlab/deploy/robots/go2
./build/go2_ctrl --network=enp5s0   # tu interfaz Ethernet real
```

El binario carga `policy.onnx` desde
`config/policy/velocity/v0/exported/`, conecta a `rt/lowstate`, y
comienza a publicar comandos.

### 4. Añadir el modo a `Go2Controller` (cuando quieras hacerlo)

`tools/go2_controller.py` se extendería con un tercer backend que
publique a `rt/wirelesscontroller` (igual que en sim, pero apuntando a la
interfaz real). Algo así:

```python
elif mode == "real_lowlevel":
    # Asume que go2_ctrl ya está corriendo en otra terminal,
    # subscribiendo a rt/wirelesscontroller para recibir comandos.
    self._backend = _SimBackend(network=network, domain_id=domain_id)
    # (mismo backend que sim porque la API DDS es la misma!)
```

Es decir: **tu código de aplicación no cambia nada**. Solo cambias
`mode="real"` por `mode="real_lowlevel"` y, en otra terminal, lanzas
`go2_ctrl` en lugar de Sport Mode.

### 5. Riesgos a tener en cuenta

- En `debug mode` el firmware de seguridad de Sport Mode NO actúa. Si tu
  policy se vuelve loca, el perro se cae. Mucho.
- El sim2real gap es real: aunque tu policy fuera perfecta en simulador,
  pequeñas diferencias en fricciones, latencia y calibración de motores
  pueden desestabilizar.
- **Domain randomization fuerte** durante entrenamiento es crítico para
  que el `.pt` sobreviva el paso a real.

### 6. ¿Cuándo merece la pena?

- Cuando hayas entrenado una policy con **DR amplia** y validado que es
  robusta en simulador.
- Cuando necesites un gait que Sport Mode no ofrece.
- Cuando estés haciendo investigación de locomoción / sim2real.

Para todo lo demás → **enfoque A (Sport Mode)** es la opción correcta.
