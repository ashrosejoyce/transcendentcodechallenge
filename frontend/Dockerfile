# Build context is ./frontend (see docker-compose.yml). Vanilla HTML/CSS/JS,
# no build step - just served directly by nginx.
FROM nginx:1.27-alpine

COPY index.html style.css app.js /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not localhost: Alpine's BusyBox wget resolves "localhost" to
# ::1 first with no IPv4 fallback (unlike curl), and nginx here only
# listens on IPv4 - "localhost" makes every check fail with "connection
# refused" even though the server is up and reachable on 8080 from outside.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
