FROM caddy:2 AS caddy
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/home/user \
    XDG_DATA_HOME=/tmp/xdg-data XDG_CONFIG_HOME=/tmp/xdg-config
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=user . .
COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
RUN chmod +x start.sh
USER user
ENV TRUTHSYNC_DB=/home/user/app/data/truthsync.db
CMD ["bash", "start.sh"]
