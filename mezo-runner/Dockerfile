FROM node:22-bookworm-slim

ARG KILO_VERSION=7.3.18
ARG SKILLS_CLI_VERSION=1.5.19
ARG GUARD_SKILLS_COMMIT=ffa26036b7b5e77b20b5d679304a703b6fd1a43d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates cmake curl docker.io gh git jq openssh-client python3 python3-pip shellcheck ripgrep tini \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global "@kilocode/cli@${KILO_VERSION}" "skills@${SKILLS_CLI_VERSION}" \
    && kilo --version \
    && skills --help >/dev/null

RUN git clone --filter=blob:none https://github.com/amElnagdy/guard-skills.git /tmp/guard-skills \
    && git -C /tmp/guard-skills checkout "${GUARD_SKILLS_COMMIT}" \
    && mkdir -p /opt/mezo/skills \
    && cp -R /tmp/guard-skills/skills/clean-code-guard /tmp/guard-skills/skills/test-guard /tmp/guard-skills/skills/docs-guard /opt/mezo/skills/ \
    && rm -rf /tmp/guard-skills

RUN useradd --no-create-home --user-group --uid 10002 --shell /usr/sbin/nologin mezo-task \
    && mkdir -p /app /data /workspaces \
    && chmod 0700 /data \
    && chmod 0755 /workspaces

WORKDIR /app
COPY mezo-runner/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY mezo-runner/runner ./runner

ENV PYTHONPATH=/app \
    WORKSPACE_ROOT=/workspaces \
    RUNNER_DATA_ROOT=/data \
    MEZO_SKILLS_ROOT=/opt/mezo/skills \
    MEZO_TASK_UID=10002 \
    MEZO_TASK_GID=10002

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "runner.main"]
