FROM python:3.12-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bubblewrap build-essential ca-certificates cmake git jq make nodejs npm ripgrep shellcheck tini \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --no-create-home --user-group --uid 10002 --shell /usr/sbin/nologin mezo-task \
    && mkdir -p /app /workspaces \
    && chown mezo-task:mezo-task /workspaces

WORKDIR /app
COPY mezo-runner/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY mezo-runner/runner ./runner

ENV PYTHONPATH=/app \
    WORKSPACE_ROOT=/workspaces \
    MEZO_TASK_UID=10002 \
    MEZO_TASK_GID=10002

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "runner.open_source_main"]
