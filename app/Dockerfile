FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh notify.py emby_favorites_sync.py runner.py /app/
RUN chmod +x /app/entrypoint.sh

#ENV CONFIG_PATH="/app/config/emby-sync.yml"

ENTRYPOINT ["/app/entrypoint.sh"]
