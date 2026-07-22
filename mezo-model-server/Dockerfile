FROM python:3.12-slim

ARG LLAMA_RELEASE=b10079
ARG LLAMA_ARCHIVE_SHA256=296236a4fd056b46d5bac953ddc95147b8f8de20ecf49becd90c4de5ab2bfe40

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 tini \
    && curl --fail --location --retry 5 \
       "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_RELEASE}/llama-${LLAMA_RELEASE}-bin-ubuntu-x64.tar.gz" \
       --output /tmp/llama.tar.gz \
    && echo "${LLAMA_ARCHIVE_SHA256}  /tmp/llama.tar.gz" | sha256sum --check --strict \
    && mkdir -p /opt/llama \
    && tar -xzf /tmp/llama.tar.gz -C /opt/llama --strip-components=1 \
    && rm -f /tmp/llama.tar.gz \
    && mkdir -p /models \
    && rm -rf /var/lib/apt/lists/*

COPY mezo-model-server/bootstrap.py /opt/mezo/bootstrap.py
COPY mezo-model-server/manifests /opt/mezo/manifests

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/opt/mezo/bootstrap.py"]
