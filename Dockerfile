FROM python:3.12-slim-bookworm

# Tesseract + language packs live only in the image (not required on the host).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --list-langs | grep -E '^(eng|rus)$'

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV NOTES_MCP_DATA_DIR=/app/data \
    NOTES_MCP_HOST=0.0.0.0 \
    NOTES_MCP_PORT=8080 \
    NOTES_MCP_PUBLIC_URL=http://localhost:8080

EXPOSE 8080

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

CMD ["notes-web"]
