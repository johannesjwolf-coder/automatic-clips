FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core tini \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements*.txt backend/
RUN pip install --no-cache-dir -r backend/requirements-lock.txt
COPY backend/ backend/
COPY scripts/ scripts/
COPY --from=frontend /src/frontend/out frontend/out
RUN useradd -m -u 10001 clipcontrol && mkdir -p /app/data && chown -R clipcontrol:clipcontrol /app
USER clipcontrol
ENV CLIPCONTROL_DATA=/app/data CLIPCONTROL_STATIC=/app/frontend/out PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python","scripts/serve.py"]
