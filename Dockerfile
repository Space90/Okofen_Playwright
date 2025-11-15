FROM python:3.12-slim

# Pour éviter les questions interactives et réduire le bruit
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Dépendances système de base
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libxkbcommon0 \
    libasound2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libglib2.0-0 \
    libdrm2 \
    libgbm1 \
    libxrandr2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Copie des requirements et install
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium

# Copie du code applicatif
COPY app.py Okofen_Playwright.py .env.example ./

# Variables par défaut (surchargées par .env ou compose)
ENV SCRIPT_PATH=/app/Okofen_Playwright.py \
    SCRIPT_TIMEOUT=25 \
    LOG_PATH=/app/okofen-web.log \
    LOG_LEVEL=INFO

EXPOSE 5000

# Commande de démarrage : Gunicorn + app factory Flask
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:create_app()"]
