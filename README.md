# Bitácora de Fuerza

App simple para registrar pesos y series de la rutina, con guardado real en
base de datos (no depende de Claude ni del navegador local — accesible desde
cualquier dispositivo).

## Estructura
- `main.py` — backend FastAPI con una API de guardado tipo clave-valor
- `static/index.html` — la app (diseño, rutina, lógica de la interfaz)
- `requirements.txt` — dependencias de Python
- `Procfile` — comando de arranque para Railway

## 1. Subir a GitHub

```bash
cd bitacora-fuerza
git init
git add .
git commit -m "Bitácora de fuerza"
gh repo create bitacora-fuerza --private --source=. --push
```

(O si preferís sin `gh`: creá el repo vacío en github.com, y hacé
`git remote add origin <url>` + `git push -u origin main`.)

## 2. Desplegar en Railway

1. Entrá a railway.app → **New Project** → **Deploy from GitHub repo** →
   elegí `bitacora-fuerza`.
2. Railway detecta automáticamente que es Python (por `requirements.txt` y
   `Procfile`) e instala todo solo.
3. Agregá una base de datos: botón **+ New** → **Database** → **PostgreSQL**.
   Railway conecta sola la variable `DATABASE_URL` al servicio — no hay que
   tocar nada en el código.
4. Andá a la pestaña **Settings** del servicio web → **Networking** →
   **Generate Domain**. Ahí te da una URL pública tipo
   `https://bitacora-fuerza-production.up.railway.app`.

## 3. Usar desde el celular

Abrí esa URL desde Chrome o Safari en tu teléfono. Para que se sienta como
una app:
- **Android (Chrome):** menú ⋮ → "Agregar a pantalla de inicio"
- **iPhone (Safari):** botón compartir → "Agregar a pantalla de inicio"

Así te queda un ícono como cualquier otra app, y cada vez que la abrís pega
contra la base de datos real en Railway — el progreso es el mismo se entre
desde el teléfono o desde la compu.

## Notas
- Si en algún momento agregás más semanas de rutina, solo hay que editar el
  array `ROUTINE` dentro de `static/index.html` — no hace falta tocar el
  backend.
- Sin uso, el plan gratuito de Railway alcanza de sobra para esto (es una
  app personal con tráfico mínimo).
