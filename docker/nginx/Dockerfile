# docker/nginx/Dockerfile
# Imagen del servidor Nginx para FitPro.
# Sirve los archivos estáticos del frontend y actúa como proxy inverso al backend.
#
# CONTEXTO DE BUILD: raíz del proyecto (.)
# Todas las rutas COPY son relativas a la raíz del proyecto.

# ─────────────────────────────────────────────────────────────────────────
# IMAGEN BASE — Nginx 1.25 Alpine
# Alpine: imagen mínima (~25 MB vs ~150 MB de la versión completa).
# ─────────────────────────────────────────────────────────────────────────
FROM nginx:1.25-alpine

# Eliminar la configuración por defecto de Nginx para evitar conflictos
# con nuestra configuración personalizada.
RUN rm /etc/nginx/conf.d/default.conf

# ─────────────────────────────────────────────────────────────────────────
# CORRECCIÓN CRÍTICA: ERR_INVALID_CHUNKED_ENCODING en Docker/WSL2
#
# El nginx.conf base de Alpine (en el bloque http{}) tiene:
#   sendfile on;
#
# Aunque nuestro fitpro.conf tenga "sendfile off" en el bloque server{},
# en algunas versiones de Alpine+nginx la directiva a nivel http puede
# no quedar correctamente anulada por el bloque server.
# Solución: parchar directamente el nginx.conf principal para que
# sendfile quede desactivado desde el nivel http, garantizando que
# ningún location ni server lo reactive accidentalmente.
# ─────────────────────────────────────────────────────────────────────────
RUN sed -i 's/sendfile\s*on;/sendfile off;/g' /etc/nginx/nginx.conf && \
    sed -i 's/tcp_nopush\s*on;/tcp_nopush off;/g' /etc/nginx/nginx.conf

# ─────────────────────────────────────────────────────────────────────────
# ARCHIVOS ESTÁTICOS DEL FRONTEND
# Copia todo el contenido de ./frontend/ al directorio web de Nginx.
# Estructura resultante en el contenedor:
#   /usr/share/nginx/html/index.html
#   /usr/share/nginx/html/css/main.css
#   /usr/share/nginx/html/js/api.js
#   ...etc
# ─────────────────────────────────────────────────────────────────────────
COPY frontend/ /usr/share/nginx/html/

# ─────────────────────────────────────────────────────────────────────────
# IMÁGENES DEL BACKEND
# Las imágenes se copian al servidor estático para que el navegador
# las obtenga vía http://localhost/img/... sin cruzar contenedores.
# ─────────────────────────────────────────────────────────────────────────
COPY backend/img/ /usr/share/nginx/html/img/

# ─────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE NGINX
# nginx.conf          → configuración del servidor virtual (locations, proxy,
#                       caché, enrutamiento SPA)
# security_headers.conf → cabeceras HTTP de seguridad incluidas en cada
#                         location (no se heredan automáticamente en nginx)
# ─────────────────────────────────────────────────────────────────────────
COPY docker/nginx/nginx.conf            /etc/nginx/conf.d/fitpro.conf
COPY docker/nginx/security_headers.conf /etc/nginx/conf.d/security_headers.conf

# Puerto HTTP estándar expuesto por el contenedor
EXPOSE 80

# Nginx en primer plano para que Docker gestione el ciclo de vida del proceso.
CMD ["nginx", "-g", "daemon off;"]