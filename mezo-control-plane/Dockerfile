FROM node:22-alpine AS frontend

WORKDIR /source
COPY package.json package-lock.json ./
COPY mezo-frontend/package.json ./mezo-frontend/package.json
COPY mezo-desktop/package.json ./mezo-desktop/package.json
RUN npm ci
COPY mezo-frontend ./mezo-frontend
RUN npm run build --workspace=mezo-frontend

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY mezo-control-plane/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mezo-control-plane/main.py ./main.py
COPY mezo-control-plane/src ./src
COPY mezo-database ./database
COPY --from=frontend /source/mezo-frontend/dist ./frontend

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin mezo \
    && mkdir -p /data \
    && chown -R mezo:mezo /app /data

ENTRYPOINT ["/bin/sh", "-c", "chown mezo:mezo /data && exec gosu mezo \"$@\"", "--"]

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
