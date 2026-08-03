# =====================================================================
# MegaSoft Asistencia — Backend (FastAPI + MongoDB)
# =====================================================================
FROM python:3.11-slim AS runtime

# Zona horaria y dependencias del sistema
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Caracas

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata build-essential libjpeg-dev zlib1g-dev curl \
    && ln -fs /usr/share/zoneinfo/America/Caracas /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PATH explícito por si acaso (asegura que /usr/local/bin esté al frente)
ENV PATH="/usr/local/bin:${PATH}"

# Instala dependencias primero para cacheo eficiente
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir \
         --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
         -r requirements.txt \
    && python -c "import uvicorn, fastapi; print('deps OK', uvicorn.__version__)"

# Copia el código y assets (manual, tests, etc.)
COPY . .

# Ejecutar como usuario no-root
RUN useradd -m -u 1000 megasoft && chown -R megasoft:megasoft /app
USER megasoft

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/api/settings || exit 1

# Producción: 2 workers uvicorn. Ajusta --workers según núcleos.
# `python -m uvicorn` evita problemas de PATH cuando el binario está
# instalado en un directorio no incluido en $PATH del usuario no-root.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2", "--proxy-headers"]
