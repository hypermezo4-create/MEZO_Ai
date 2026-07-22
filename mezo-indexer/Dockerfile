FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY mezo-indexer/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY mezo-indexer/main.py ./
RUN useradd --no-create-home --uid 10004 --shell /usr/sbin/nologin mezo-indexer \
    && mkdir -p /index \
    && chown -R mezo-indexer:mezo-indexer /app /index
USER mezo-indexer
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
