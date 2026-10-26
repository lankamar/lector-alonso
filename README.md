# Lector Alonso

Extensión de Chrome + backend local de texto a voz para leer en español lo que tenés en pantalla: la selección, la página visible (OCR) o un documento entero (PDF, DOCX, TXT, MD).

Nació de una necesidad concreta: estudiar y corregir textos largos sin depender de servicios en la nube, con la voz latina neutra de **Alonso** y sin subir nada a un tercero.

---

## Qué hace

| Función | Cómo se usa |
|---|---|
| **Leer selección** | Seleccionás texto en cualquier página → *Leer selección* |
| **Leer documento** | Elegís un PDF, DOCX, TXT o MD en el panel y lo lee completo, por partes |
| **OCR de la página visible** | Captura la pestaña y extrae el texto de imágenes o PDFs escaneados |
| **Pegar y leer** | Toma el portapapeles y lo lee |
| **Menú contextual** | Clic derecho sobre texto seleccionado → *Read selection* |

Controles: pausa/reanudar, detener, velocidad de −30% a +80%, seis voces en español.

## Voces

| Voz | Variante |
|---|---|
| Alonso | Latino neutro (recomendada) |
| Tomás | Argentina |
| Elena | Argentina |
| Dalia | México |
| Jorge | México |
| Álvaro | España |

Las voces las sintetiza `edge-tts`. No hace falta clave de API.

## Arquitectura

```
extensión (Chrome, Manifest V3)
   ├── sidepanel.js      interfaz: texto, archivo, OCR, voz, velocidad
   ├── background.js     menú contextual y captura de selección
   └── offscreen.js      reproduce el audio que devuelve el backend
            │
            │ HTTP (127.0.0.1:8000 por defecto)
            ▼
backend FastAPI (app.py)
   ├── POST /extract     extrae texto de PDF, DOCX, TXT, MD o imagen
   ├── POST /split       parte el texto en fragmentos para sintetizar
   └── POST /tts         sintetiza un fragmento y devuelve el audio
```

El audio nunca sale de tu máquina: el backend corre local y la voz se genera ahí.

## Instalación

### 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

Opcional: protección con token.

```bash
cp .env.example .env
# editá APP_ACCESS_TOKEN con un valor largo y aleatorio
```

Si el token está definido, el panel de la extensión lo pide en *Token privado del servidor*.

### 2. Extensión

1. Abrí `chrome://extensions`
2. Activá **Modo de desarrollador**
3. **Cargar descomprimida** → seleccioná la carpeta `extension/`
4. Fijala en la barra y abrí el panel lateral

Si el backend corre en otro puerto, cambialo en *URL del backend TTS* y guardá.

### 3. Docker (opcional)

```bash
docker compose up -d
```

Incluye `Caddyfile` para servir el panel web en un dominio propio con HTTPS.

## Estructura del repositorio

```
app.py                 backend FastAPI (extract, split, tts)
requirements.txt       dependencias
extension/             extensión de Chrome (Manifest V3)
  manifest.json        permisos y configuración
  sidepanel.html/js    panel lateral
  background.js        menú contextual
  offscreen.js         reproducción de audio
Dockerfile             imagen del backend
docker-compose.yml     despliegue local
Caddyfile              proxy con HTTPS para el panel web
DEPLOY.md              notas de despliegue
```

## Permisos de la extensión

| Permiso | Para qué |
|---|---|
| `sidePanel` | el panel lateral |
| `scripting`, `activeTab` | leer la selección de la pestaña activa |
| `contextMenus` | la opción del clic derecho |
| `storage` | guardar voz, velocidad y URL del backend |
| `offscreen` | reproducir audio fuera del panel |
| `tabs` | capturar la pestaña para el OCR |

## Límites conocidos

- El OCR depende del motor del backend; en páginas con mucho diseño puede mezclar columnas.
- Los PDF escaneados sin capa de texto pasan por OCR y tardan más.
- La síntesis se hace por fragmentos: en documentos largos hay una pausa breve entre partes.
- La extensión está pensada para uso personal y autoinstalación; no está publicada en la Chrome Web Store.

## Estado

Versión **1.8.0**. Funciona en Chrome y en navegadores basados en Chromium con soporte de Manifest V3.

## Licencia

MIT — ver [LICENSE](LICENSE).
