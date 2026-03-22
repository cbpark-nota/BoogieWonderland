FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Make claude available system-wide
ENV PATH="/root/.local/bin:/root/.claude/bin:${PATH}"

# Working directory (will be overridden by mount)
WORKDIR /workspace

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Keep container running
CMD ["tail", "-f", "/dev/null"]
