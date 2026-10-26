import re
import asyncio
import subprocess
import tempfile
import hmac
import os
from zipfile import BadZipFile
from pathlib import Path
from io import BytesIO
import edge_tts
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

app = FastAPI(title="Lector Alonso PWA")
APP_VERSION = (Path(__file__).resolve().parent / "VERSION").read_text().strip()
APP_ACCESS_TOKEN = os.environ.get("APP_ACCESS_TOKEN", "")
@app.middleware("http")
async def protect_api(request, call_next):
    if (
        APP_ACCESS_TOKEN
        and request.method != "OPTIONS"
        and request.url.path in {"/split", "/extract", "/tts"}
    ):
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token, APP_ACCESS_TOKEN):
            return JSONResponse({"detail": "Se requiere un token de acceso válido."}, status_code=401)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://[a-p]{32}",
    allow_methods=["POST"],
    allow_headers=["*"],
)

VOICES = [
    ("es-US-AlonsoNeural", "Alonso (Latino Neutro - Recomendada)"),
    ("es-AR-TomasNeural", "Tomás (Argentina)"),
    ("es-AR-ElenaNeural", "Elena (Argentina)"),
    ("es-MX-DaliaNeural", "Dalia (México)"),
    ("es-MX-JorgeNeural", "Jorge (México)"),
    ("es-ES-AlvaroNeural", "Álvaro (España)")
]

def split_text_smart(text: str, max_chars: int = 400):
    text = re.sub(r"```[\s\S]*?```", " [bloque de código omitido] ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"[#*_~>]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    
    sentences = re.split(r'(?<=[.!?;\n])\s+', text)
    chunks = []
    curr = ""
    for s in sentences:
        if not s.strip():
            continue
        if len(curr) + len(s) < max_chars:
            curr = f"{curr} {s}".strip()
        else:
            if curr:
                chunks.append(curr)
            curr = s
    if curr:
        chunks.append(curr)
    return chunks

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Lector Alonso - Audio Reader</title>
    <meta name="theme-color" content="#0f172a">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="/manifest.json">
    <style>
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #090d16;
            color: #f1f5f9;
            margin: 0;
            padding: 16px;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        .container {
            max-width: 680px;
            width: 100%;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            flex: 1;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 8px;
            border-bottom: 1px solid #1e293b;
        }
        h1 {
            margin: 0;
            font-size: 1.25rem;
            color: #38bdf8;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .badge {
            background: #0284c7;
            font-size: 0.7rem;
            padding: 2px 6px;
            border-radius: 99px;
            color: #fff;
        }
        textarea {
            width: 100%;
            height: 220px;
            background: #111827;
            border: 1px solid #374151;
            border-radius: 12px;
            color: #f9fafb;
            padding: 12px;
            font-size: 1rem;
            line-height: 1.5;
            resize: vertical;
            outline: none;
        }
        textarea:focus { border-color: #38bdf8; }
        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            background: #131c2e;
            padding: 12px;
            border-radius: 12px;
            border: 1px solid #1e293b;
        }
        label { font-size: 0.8rem; color: #94a3b8; font-weight: 600; display: block; margin-bottom: 4px; }
        select, input[type="range"] {
            width: 100%;
            background: #1f293d;
            border: 1px solid #334155;
            color: #fff;
            padding: 8px;
            border-radius: 8px;
            font-size: 0.9rem;
            outline: none;
        }
        .btn-group {
            display: flex;
            gap: 10px;
            margin-top: 4px;
        }
        button {
            flex: 1;
            padding: 14px;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 1rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.2s;
        }
        .btn-play { background: #0284c7; color: #fff; }
        .btn-play:active { background: #0369a1; transform: scale(0.98); }
        .btn-stop { background: #ef4444; color: #fff; flex: 0.5; }
        .btn-stop:active { background: #dc2626; transform: scale(0.98); }
        .btn-file {
            background: #1e293b;
            color: #94a3b8;
            font-size: 0.85rem;
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            text-align: center;
            border: 1px dashed #475569;
        }
        #status {
            font-size: 0.85rem;
            color: #38bdf8;
            text-align: center;
            min-height: 20px;
        }
        .rate-box {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .rate-val { font-size: 0.9rem; color: #38bdf8; font-weight: bold; min-width: 40px; }
        #app-version { color: #64748b; text-align: center; font-size: 0.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎙️ Lector Alonso <span class="badge">Voz Principal</span></h1>
            <span id="queue-status" style="font-size: 0.75rem; color: #64748b;">Listo</span>
        </header>

        <label class="btn-file">
            📁 Cargar documento o foto (PDF, texto, Word, PNG/JPG)
            <input type="file" id="file-input" accept=".txt,.md,.pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" style="display:none;" onchange="loadFile(this)">
        </label>

        <textarea id="text" placeholder="Pega aquí el texto, libro o capítulo que quieras que lea..."></textarea>

        <button type="button" class="btn-file" onclick="pasteAndRead()">📋 Pegar desde el portapapeles y leer</button>
        <div class="controls">
            <div>
                <label>Voz:</label>
                <select id="voice">
                    {voice_options}
                </select>
            </div>
            <div>
                <label>Velocidad:</label>
                <div class="rate-box">
                    <input type="range" id="rate" min="-30" max="80" value="20" step="5" oninput="updateRate(this.value)">
                    <span id="rate-val" class="rate-val">+20%</span>
                </div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn-play" id="btn-play" onclick="startPlayback()">▶ Reproducir</button>
            <button class="btn-stop" id="btn-stop" onclick="stopPlayback()">⏹ Detener</button>
        </div>

        <details>
            <summary style="margin-top:14px;cursor:pointer;color:#cbd5e1">Acceso al servidor</summary>
            <label for="access-token">Token privado del servidor</label>
            <input id="access-token" type="password" autocomplete="off" placeholder="Token entregado por quien administra el servidor">
            <button type="button" class="btn-file" onclick="saveAccessToken()">Guardar token</button>
        </details>
        <div id="status"></div>
        <div id="app-version">Lector Alonso v{app_version}</div>
    </div>

    <script>
        let isPlaying = false;
        let chunks = [];
        let currentIndex = 0;
        let audioPlayer = new Audio();
        let audioUrl = null;
        let activeRequest = null;
        let accessToken = localStorage.getItem('lectorAccessToken') || '';
        document.getElementById('access-token').value = accessToken;

        function authHeaders() {
            return accessToken ? {Authorization: 'Bearer ' + accessToken} : {};
        }

        function saveAccessToken() {
            accessToken = document.getElementById('access-token').value.trim();
            localStorage.setItem('lectorAccessToken', accessToken);
            document.getElementById('status').innerText = 'Token guardado en este navegador.';
        }

        function updateRate(val) {
            document.getElementById('rate-val').innerText = (val >= 0 ? '+' : '') + val + '%';
        }

        async function pasteAndRead() {
            try {
                const text = await navigator.clipboard.readText();
                if (!text.trim()) {
                    document.getElementById('status').innerText = 'El portapapeles está vacío.';
                    return;
                }
                document.getElementById('text').value = text;
                await startPlayback();
            } catch (error) {
                document.getElementById('status').innerText =
                    'No se pudo acceder al portapapeles. Pegá con Ctrl+V en el campo y tocá Reproducir.';
            }
        }

        function loadFile(input) {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            document.getElementById('status').innerText = `Extrayendo texto de ${file.name}...`;
            fetch('/extract', { method: 'POST', body: formData, headers: authHeaders() })
                .then(async response => {
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || 'No se pudo extraer el texto.');
                    document.getElementById('text').value = result.text;
                    document.getElementById('status').innerText = `Texto extraído de ${file.name}. Podés editarlo.`;
                })
                .catch(error => {
                    document.getElementById('status').innerText = `Error: ${error.message}`;
                })
                .finally(() => { input.value = ''; });
        }

        async function startPlayback() {
            const text = document.getElementById('text').value.trim();
            if (!text) {
                alert('Pega algún texto primero');
                return;
            }

            stopPlayback();
            activeRequest = new AbortController();
            isPlaying = true;
            document.getElementById('status').innerText = 'Analizando texto...';
            document.getElementById('btn-play').innerText = '⏳ Cargando...';

            try {
                const res = await fetch('/split', {
                    method: 'POST',
                    body: new URLSearchParams({text: text}),
                    signal: activeRequest.signal,
                    headers: {'Content-Type': 'application/x-www-form-urlencoded', ...authHeaders()}
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Error al preparar el texto.');
                chunks = data.chunks;
                currentIndex = 0;

                if (chunks.length === 0) {
                    stopPlayback();
                    return;
                }

                document.getElementById('btn-play').innerText = '⏸ Pausar';
                playNextChunk();
            } catch (err) {
                if (err.name !== 'AbortError') {
                    document.getElementById('status').innerText = 'Error al preparar el texto.';
                    stopPlayback();
                }
            }
        }

        async function playNextChunk() {
            if (!isPlaying || currentIndex >= chunks.length) {
                stopPlayback();
                document.getElementById('status').innerText = 'Lectura completada.';
                return;
            }

            const voice = document.getElementById('voice').value;
            const rateVal = document.getElementById('rate').value;
            const rate = (rateVal >= 0 ? '+' : '') + rateVal + '%';
            const chunkText = chunks[currentIndex];

            document.getElementById('status').innerText = `Leyendo párrafo ${currentIndex + 1} de ${chunks.length}...`;

            try {
                const formData = new FormData();
                formData.append('text', chunkText);
                formData.append('voice', voice);
                formData.append('rate', rate);

                const res = await fetch('/tts', {
                    method: 'POST',
                    body: formData,
                    signal: activeRequest.signal,
                    headers: authHeaders()
                });
                if (!res.ok) {
                    const errorBody = await res.json();
                    throw new Error(errorBody.detail || 'Error sintetizando.');
                }

                const blob = await res.blob();
                audioUrl = URL.createObjectURL(blob);
                audioPlayer.src = audioUrl;
                
                audioPlayer.onended = () => {
                    currentIndex++;
                    playNextChunk();
                };

                await audioPlayer.play();
            } catch (err) {
                if (err.name === 'AbortError') return;
                console.error(err);
                document.getElementById('status').innerText = 'Error en reproducción: ' + err.message;
                stopPlayback();
            }
        }

        function stopPlayback() {
            isPlaying = false;
            if (activeRequest) {
                activeRequest.abort();
                activeRequest = null;
            }
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
            audioPlayer.removeAttribute('src');
            audioPlayer.load();
            if (audioUrl) {
                URL.revokeObjectURL(audioUrl);
                audioUrl = null;
            }
            document.getElementById('btn-play').innerText = '▶ Reproducir';
            document.getElementById('status').innerText = '';
        }

        window.addEventListener('pagehide', stopPlayback);

        // Compartir directamente desde el móvil (Web Share Target / Intent)
        window.addEventListener('DOMContentLoaded', () => {
            const parsedUrl = new URL(window.location);
            const sharedText = parsedUrl.searchParams.get('text') || parsedUrl.searchParams.get('title');
            if (sharedText) {
                document.getElementById('text').value = sharedText;
            }
        });
    </script>
</body>
</html>
"""

MANIFEST = {
    "name": "Lector Alonso",
    "short_name": "Lector Alonso",
    "description": "Lector de libros y mensajes en voz alta con Alonso",
    "version": APP_VERSION,
    "version_name": APP_VERSION,
    "start_url": "/",
    "display": "standalone",
    "background_color": "#090d16",
    "theme_color": "#0f172a",
    "icons": [
        {
            "src": "https://cdn-icons-png.flaticon.com/512/3039/3039386.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
}

@app.get("/manifest.json")
async def get_manifest():
    return JSONResponse(content=MANIFEST)

@app.get("/version")
async def get_version():
    return JSONResponse({"app": "Lector Alonso", "version": APP_VERSION})

@app.get("/", response_class=HTMLResponse)
async def index():
    opts = "".join([f'<option value="{v[0]}" {"selected" if v[0] == "es-US-AlonsoNeural" else ""}>{v[1]}</option>' for v in VOICES])
    return HTML_CONTENT.replace("{voice_options}", opts).replace("{app_version}", APP_VERSION)

@app.post("/split")
async def split_endpoint(text: str = Form(...)):
    chunks = split_text_smart(text)
    return JSONResponse({"chunks": chunks})

@app.post("/extract")
async def extract_document(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    if suffix not in {".pdf", ".txt", ".md", ".docx", ".doc", *image_suffixes}:
        raise HTTPException(
            status_code=415,
            detail="Formato no compatible. Usá PDF, TXT, MD, DOCX, DOC o una imagen PNG/JPG/WEBP/TIFF/BMP."
        )

    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 20 MB.")
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    try:
        if suffix in image_suffixes:
            try:
                with Image.open(BytesIO(content)) as image:
                    image.verify()
                with Image.open(BytesIO(content)) as image:
                    if image.width * image.height > 40_000_000:
                        raise HTTPException(status_code=413, detail="La imagen supera el límite de 40 megapíxeles.")
                    image.load()
                    with tempfile.TemporaryDirectory(prefix="lector-alonso-ocr-") as temp_dir:
                        image_path = Path(temp_dir) / f"image{suffix}"
                        image.save(image_path)
                        result = subprocess.run(
                            ["tesseract", str(image_path), "stdout", "-l", "spa+eng", "--psm", "3"],
                            capture_output=True,
                            text=True,
                            timeout=60,
                            check=False,
                        )
                        if result.returncode != 0:
                            raise HTTPException(
                                status_code=503,
                                detail="OCR no disponible. Instalá Tesseract con los idiomas español e inglés."
                            )
                        text = result.stdout
            except UnidentifiedImageError as error:
                raise HTTPException(status_code=422, detail="El archivo no es una imagen válida.") from error
        elif suffix in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise HTTPException(status_code=422, detail="El PDF está protegido con contraseña.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            document = Document(BytesIO(content))
            paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
            for table in document.tables:
                paragraphs.extend(
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in table.rows
                )
            text = "\n".join(paragraphs)
        else:
            with tempfile.TemporaryDirectory(prefix="lector-alonso-") as temp_dir:
                source = Path(temp_dir) / Path(file.filename or "document.doc").name
                source.write_bytes(content)
                result = subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "txt:Text",
                        "--outdir",
                        temp_dir,
                        str(source),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                converted = source.with_suffix(".txt")
                if result.returncode != 0 or not converted.exists():
                    raise HTTPException(status_code=422, detail="No se pudo extraer el texto del archivo DOC.")
                text = converted.read_text(encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=422, detail="El procesamiento del archivo superó el tiempo permitido.") from error
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Falta una herramienta del servidor para procesar este archivo (Tesseract OCR o LibreOffice)."
        ) from error
    except (UnicodeDecodeError, PdfReadError, BadZipFile, PackageNotFoundError, ValueError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el documento: {error}") from error

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No se encontró texto extraíble. Si es un PDF escaneado, requiere OCR.")
    return JSONResponse({"filename": file.filename, "text": text})

@app.post("/tts")
async def tts_endpoint(
    text: str = Form(...),
    voice: str = Form("es-US-AlonsoNeural"),
    rate: str = Form("+20%")
):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
    return Response(content=bytes(audio_data), media_type="audio/mpeg")
