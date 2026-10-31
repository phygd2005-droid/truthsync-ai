#!/bin/bash
# One container, one public port ($PORT, 7860 on Hugging Face):
#   /api/*  -> device API (ESP32)      everything else -> web app
mkdir -p "$(dirname "${TRUTHSYNC_DB:-./data/truthsync.db}")"
python -m uvicorn api:app --host 127.0.0.1 --port 8000 &
python -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1 \
  --server.headless true --server.enableCORS false --server.enableXsrfProtection false \
  --browser.gatherUsageStats false &
caddy run --config ./Caddyfile --adapter caddyfile &
wait -n
exit 1
