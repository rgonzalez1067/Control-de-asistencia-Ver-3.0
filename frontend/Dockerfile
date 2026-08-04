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

# Copia la configuración SSL desde el repo. Los certificados se montan
# como volumen /etc/nginx/ssl desde el host en el docker-compose.
COPY nginx-ssl.conf /etc/nginx/conf.d/megasoft.conf

COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --spider -q --no-check-certificate https://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
