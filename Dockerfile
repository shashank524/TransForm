FROM python:3.11-slim

# Networking tools for tc netem shaping (client container)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    iputils-ping \
    ca-certificates \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
  && pip install --no-cache-dir matplotlib seaborn duckdb

# Copy repo (compose will also mount a volume for dev iteration)
COPY . /app

ENV PYTHONUNBUFFERED=1

