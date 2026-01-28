# Basis-Image mit Python
FROM python:3.12-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# System-Dependencies für PyMuPDF und yt-dlp (ffmpeg)
RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendungscode kopieren
COPY src/ ./src/
COPY app.py .

# Streamlit Konfiguration
RUN mkdir -p ~/.streamlit
RUN echo '\
[server]\n\
headless = true\n\
port = 8501\n\
address = "0.0.0.0"\n\
enableCORS = false\n\
enableXsrfProtection = false\n\
\n\
[browser]\n\
gatherUsageStats = false\n\
' > ~/.streamlit/config.toml

# Port freigeben
EXPOSE 8501

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Anwendung starten
ENTRYPOINT ["streamlit", "run", "app.py"]
