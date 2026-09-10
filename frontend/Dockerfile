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

# Previene que advertencias de ESLint cancelen el build en CI
ENV CI=false \
    DISABLE_ESLINT_PLUGIN=true \
    NODE_OPTIONS="--max-old-space-size=4096"

# Instala dependencias con fallback seguro
COPY package.json yarn.lock* package-lock.json* ./

RUN npm config set registry https://registry.npmjs.org/ && \
    if [ -f package-lock.json ]; then \
      npm ci ; \
    elif [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile || npm install --legacy-peer-deps ; \
    else \
      npm install --legacy-peer-deps ; \
    fi

# Copia código y compila
COPY . .
RUN npm run build || yarn build

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

RUN chmod -R 755 /usr/share/nginx/html && chown -R nginx:nginx /usr/share/nginx/html

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --spider -q --no-check-certificate https://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
