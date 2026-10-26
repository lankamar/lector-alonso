# Despliegue del backend en un VPS

Este paquete requiere un VPS con Docker y Docker Compose. No se despliega en
`public_html` ni en un hosting compartido que solo permita FTP/PHP. Caddy publica
la aplicación por HTTPS y obtiene/renueva el certificado automáticamente.

## Requisitos

- VPS con Docker Engine y el plugin Docker Compose instalados.
- Un dominio o subdominio cuyo registro DNS `A` apunte a la IP pública del VPS.
- Puertos TCP 80 y 443 abiertos en el firewall del VPS y del proveedor.

## Configuración

1. Copiá los archivos del proyecto al VPS.
2. En la carpeta del proyecto, creá `.env` a partir del ejemplo:

   ```sh
   cp .env.example .env
   ```

3. Editá `.env`: poné el dominio real en `APP_DOMAIN` y generá un token privado
   con `openssl rand -hex 32` para `APP_ACCESS_TOKEN`. No compartas ni publiques
   ese valor; `.env` está excluido de Git y de la imagen Docker.
4. Iniciá los servicios:

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

   La aplicación queda detrás de Caddy; el puerto 8000 no se expone directamente.
   Comprobá `https://TU-DOMINIO/version`.

## Clientes

- **PWA:** abrí `https://TU-DOMINIO`, desplegá “Acceso al servidor”, ingresá el
  mismo token y guardalo en ese navegador.
- **Extensión:** instalá la carpeta `extension/`, abrí “Conexión del servidor”,
  configurá `https://TU-DOMINIO` y el token, y guardá. Chrome pedirá permiso de
  conexión.

El token se guarda localmente en cada navegador/instalación. Al cambiarlo en el
VPS, actualizá también los clientes. Para actualizar la app: `docker compose up
-d --build`.

## Límites importantes

`edge-tts` sintetiza mediante el servicio en línea de Microsoft; por eso el VPS
necesita salida a Internet y el servicio puede cambiar sus condiciones o limitar
el acceso. OCR usa Tesseract instalado dentro de la imagen; la conversión de `.doc`
requiere LibreOffice. El endpoint `/version` es público para diagnóstico, mientras
que las operaciones de síntesis, extracción y división de texto requieren token.
