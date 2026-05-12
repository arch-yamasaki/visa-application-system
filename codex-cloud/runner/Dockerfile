FROM node:22-bookworm

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl jq tar zstd \
  && rm -rf /var/lib/apt/lists/*

# Install codex CLI globally
RUN npm install -g @openai/codex

# Python deps (install into system with break-system-packages since this is a container)
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

WORKDIR /app

COPY update_status.py gcs_helper.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
