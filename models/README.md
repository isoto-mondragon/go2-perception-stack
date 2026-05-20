# models/

Pon aquí los checkpoints `.pt` entrenados.

## Cómo obtener un `.pt`

Dos formas:

### A) Entrenando tú mismo

Abre `notebooks/train_go2_velocity.ipynb` en Google Colab con runtime
T4 GPU. Ejecuta de arriba a abajo. Para cuando `Train/mean_reward > 55`. Descarga el último `model_XXXX.pt`
desde `Drive/MyDrive/go2_rl/exports/...` y guárdalo aquí.

### B) Pre-entrenado

Si tu instructor te ha facilitado un `.pt`, ponlo aquí.

## Estructura recomendada

```
models/
├── README.md              (este archivo)
├── go2_velocity_v1.pt     (tu primer entrenamiento)
├── go2_velocity_v2.pt     (un segundo entrenamiento, mejor)
└── ...
```

Apunta a uno de ellos al lanzar:

```bash
python tools/play_dds.py Unitree-Go2-Flat \
  --checkpoint-file=models/go2_velocity_v1.pt \
  --network=lo
```

## Por qué este archivo no se sube a git

El `.gitignore` excluye `*.pt` y `*.onnx` porque pueden pesar varios MB y
no tiene mucho sentido versionarlos. Si quieres compartir tu modelo,
súbelo a:

- HuggingFace Hub
- Google Drive (con un link en el README)
- Releases de GitHub (sin contar contra el límite del repo)
