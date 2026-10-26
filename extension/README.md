# Lector Alonso para Chrome — v1.8.0

La extensión abre como panel lateral persistente: lee la selección, puede leer directamente
el portapapeles después de copiar una respuesta de un LLM, resalta el fragmento actual en
el texto del panel, aplica inmediatamente la voz y velocidad elegidas y permite editar/pegar texto,
limpiar el campo y cargar archivos PDF, TXT, MD, DOCX, DOC y fotos/capturas PNG, JPG,
WEBP, TIFF o BMP. También puede capturar la página visible del navegador, aplicar OCR y
leer el texto detectado (útil para páginas escaneadas de PDF). El texto extraído por OCR
queda editable. La extracción requiere las dependencias de `requirements.txt`,
Tesseract con los idiomas español e inglés y, para DOC antiguos, LibreOffice.
La PWA existente sigue siendo la opción para instalar en el celular; las extensiones
de Chrome de escritorio no se instalan en Chrome móvil.

## Instalar para probar

1. Instalá dependencias con `pip install -r requirements.txt` y ejecutá
   `uvicorn app:app --host 0.0.0.0 --port 8000`.
2. En Chrome de escritorio, abrí `chrome://extensions`.
3. Activá **Modo de desarrollador** y elegí **Cargar descomprimida**.
4. Seleccioná esta carpeta `extension/`.
5. Hacé clic en el ícono de Lector Alonso: se abre el panel lateral.
6. En **Conexión del servidor**, dejá `http://127.0.0.1:8000` y guardá.
7. Para una respuesta de un chat/LLM, usá su botón **Copiar** y luego tocá **Pegar y leer**.
   Para texto seleccionable, usá **Leer selección**. Para una página escaneada/PDF, dejá
   visible la página y tocá **OCR + leer página visible**. También podés subir un archivo.

Atajos iniciales: `Alt+Shift+R` leer selección, `Alt+Shift+P` pausar/reanudar,
`Alt+Shift+X` detener. Se pueden cambiar en `chrome://extensions/shortcuts`.

Si el backend está alojado en otro lugar, poné su URL HTTPS y el token privado
en **Conexión del servidor**, guardá los ajustes y aceptá el permiso de conexión
que solicita Chrome. El despliegue Docker para VPS está documentado en
`../DEPLOY.md`; el backend público debe configurarse siempre con un token.

El audio lo genera el backend y se reproduce en la extensión, no en la pestaña
original. Cerrar la pestaña origen detiene la lectura. La extensión requiere que
el backend esté encendido y accesible.

## Versiones

`VERSION` es la versión de la app web y el backend; se muestra en la PWA y en
`GET /version`. La versión instalada de Chrome se ve al pie del panel y se define
en `manifest.json`. Al publicar una actualización, mantener ambos números iguales,
actualizar este encabezado y recargar la extensión desde `chrome://extensions`.
Usamos SemVer: parche para correcciones, minor para funciones compatibles y major
para cambios incompatibles.
