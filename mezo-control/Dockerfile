FROM node:22-alpine AS frontend
WORKDIR /source
COPY package.json package-lock.json ./
COPY mezo-frontend/package.json ./mezo-frontend/package.json
COPY mezo-desktop/package.json ./mezo-desktop/package.json
RUN npm ci
COPY mezo-frontend ./mezo-frontend
RUN npm run build --workspace=mezo-frontend

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MEZO_BIND_HOST=::
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini valkey-server \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY mezo-control-plane/requirements.txt /tmp/control-requirements.txt
COPY mezo-router/requirements.txt /tmp/router-requirements.txt
COPY mezo-indexer/requirements.txt /tmp/indexer-requirements.txt
RUN pip install --no-cache-dir -r /tmp/control-requirements.txt -r /tmp/router-requirements.txt -r /tmp/indexer-requirements.txt
COPY mezo-control-plane/main.py /app/control/main.py
COPY mezo-control-plane/src /app/control/src
COPY mezo-router/main.py /app/router/main.py
COPY mezo-indexer/main.py /app/indexer/main.py
COPY --from=frontend /source/mezo-frontend/dist /app/control/frontend
COPY mezo-control/supervisor.py /app/supervisor.py
RUN mkdir -p /data/valkey
EXPOSE 8080 8081 8082 6379
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/app/supervisor.py"]
