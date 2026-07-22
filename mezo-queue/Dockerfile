FROM valkey/valkey:8.1.3-alpine
COPY mezo-queue/start.sh /usr/local/bin/mezo-valkey-start
RUN chmod 0755 /usr/local/bin/mezo-valkey-start \
    && mkdir -p /data \
    && chown -R valkey:valkey /data
USER valkey
ENTRYPOINT ["/usr/local/bin/mezo-valkey-start"]
