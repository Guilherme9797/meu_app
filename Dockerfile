# syntax=docker/dockerfile:1
#####################################
# Stage 1: builder (instala deps)
#####################################
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Pacotes necessários apenas para build (não vão para a imagem final)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia apenas requirements para aproveitar cache
COPY requirements.txt /app/requirements.txt

# Cria venv e instala dependências dentro dela
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install -r /app/requirements.txt

#####################################
# Stage 2: runtime (mínimo e seguro)
#####################################
FROM python:3.11-slim AS runtime

# Ajustes básicos de runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=America/Sao_Paulo \
    PORT=5000 \
    OPENAI_MODEL=gpt-4o-mini

# Bibliotecas de SO necessárias em runtime (PyMuPDF e afins)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libxext6 \
    libxrender1 \
    libsm6 \
    && rm -rf /var/lib/apt/lists/*

# Copia o ambiente virtual já pronto do builder
COPY --from=builder /opt/venv /opt/venv

# Copia o código
WORKDIR /app
COPY . /app

# Cria usuário não-root
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Healthcheck real batendo no /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5000/health | grep -q '"status":"' || exit 1

# Gunicorn (2 workers, 4 threads cada, timeout generoso)
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "--timeout", "120", "-b", "0.0.0.0:5000", "server:app"]
