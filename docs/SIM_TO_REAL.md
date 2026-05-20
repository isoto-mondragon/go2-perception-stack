# De simulador a robot real

Cómo desplegar tu aplicación (la que probaste en simulador) en el Go2 físico.

---

## Idea clave

`Go2Controller` está diseñado para que el **mismo código** funcione en
ambos contextos. Lo único que cambian son dos parámetros:

```python
# Antes (sim):
dog = Go2Controller(mode="sim", network="lo")
# Ahora (real):
dog = Go2Controller(mode="real", network="enp5s0")
```

**Lo que ocurre por debajo en cada caso**:

| | Modo sim | Modo real |
|---|---|---|
| Backend | Publica `WirelessController_` por DDS al simulador | Llama a `SportClient.Move(vx, vy, wz)` |
| Locomoción | Policy RL entrenada en mjlab | Sport Mode (firmware on-board del Go2) |
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

✅ La API (`set_velocity`, `stop`, `stand_up`, `sit`).
✅ El código de tu aplicación (perception + lógica).
✅ Las constantes (vx_max, deadzone, kp, etc.) suelen funcionar parecido.

### Lo que CAMBIA

⚠️ **Sport Mode es mucho más robusto** que la policy RL del sim. En real
el perro NO se cae aunque le des comandos raros — el firmware compensa.

⚠️ **Cámara**: en real lo natural es usar la **cámara on-board del Go2**
(no la webcam del laptop). Esto requiere suscribirse al stream de video
por DDS. Ver "Cámara on-board" abajo.

⚠️ **Latencia**: real puede tener más jitter (Ethernet vs loopback). Si
ves comportamiento oscilante, baja las ganancias (`KP_YAW`, `KP_FORWARD`).

⚠️ **Seguridad**: el perro pesa ~15 kg. Asume que cualquier comando
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

## Checklist antes del primer despliegue

- [ ] PC en `192.168.123.222`, ping a `192.168.123.161` funciona
- [ ] Go2 cargado, en Sport Mode, suspendido en mesa/arnés
- [ ] Zona despejada de obstáculos
- [ ] `real_smoke_test.py` pasa todos los pasos
- [ ] Sabes cómo parar el perro (Ctrl+C, sit, botón físico)
- [ ] Si usas cámara: webcam o stream on-board funcionando

Si los 6 puntos son ✓, adelante con tu app.
