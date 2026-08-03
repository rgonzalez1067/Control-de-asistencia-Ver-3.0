# =====================================================================
# MegaSoft Asistencia — Frontend (React CRA + Nginx)
# =====================================================================
# Etapa 1: build
FROM node:20-alpine AS builder

WORKDIR /app

# REACT_APP_BACKEND_URL debe pasarse como build-arg porque CRA
# solo lee variables en tiempo de compilación.
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}

# Instala dependencias primero
# `yarn.lock*` con wildcard: no falla si el archivo no existe en el repo
COPY package.json yarn.lock* ./
RUN if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile ; \
    else \
      echo "⚠️ yarn.lock ausente — build no reproducible" && yarn install ; \
    fi

# Copia código y compila
COPY . .
RUN yarn build

# =====================================================================
# Etapa 2: nginx sirve build estático + proxy a /api
# =====================================================================
FROM nginx:1.27-alpine

# Limpia default
RUN rm /etc/nginx/conf.d/default.conf

# Config: SPA fallback + proxy backend
RUN printf '%s\n' \
  'server {' \
  '    listen 80;' \
  '    server_name _;' \
  '    root /usr/share/nginx/html;' \
  '    index index.html;' \
  '    client_max_body_size 25M;' \
  '    gzip on;' \
  '    gzip_types text/plain text/css application/json application/javascript image/svg+xml;' \
  '    location /api/ {' \
  '        proxy_pass http://backend:8001;' \
  '        proxy_set_header Host $host;' \
  '        proxy_set_header X-Real-IP $remote_addr;' \
  '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' \
  '        proxy_set_header X-Forwarded-Proto $scheme;' \
  '        proxy_read_timeout 90s;' \
  '    }' \
  '    location / {' \
  '        try_files $uri /index.html;' \
  '    }' \
  '}' > /etc/nginx/conf.d/megasoft.conf

COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --spider -q http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
