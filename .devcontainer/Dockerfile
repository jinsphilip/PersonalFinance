# FinTracker dev image. Dependencies are installed at build time so Daytona
# prebuilds (and Codespaces prebuilds) cache them — new environments start fast.
FROM mcr.microsoft.com/devcontainers/python:3.11

# Copy only requirements first for better layer caching.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt
