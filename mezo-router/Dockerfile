FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY mezo-router/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY mezo-router/main.py ./
COPY mezo-router/start.py ./
RUN useradd --no-create-home --uid 10003 --shell /usr/sbin/nologin mezo-router \
    && chown -R mezo-router:mezo-router /app
USER mezo-router
EXPOSE 8080
CMD ["python", "start.py"]
