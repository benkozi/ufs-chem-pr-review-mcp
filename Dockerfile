# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

# Install git and ca-certificates for repository cloning
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG REPO_URL="https://github.com/benkozi/ufs-chem-pr-review-mcp.git"
ARG REPO_REF="feature/initial-impl"

# Clone repository directly inside container
RUN git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" /app

# Enable bytecode compilation and copy mode
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

# Install production dependencies
RUN uv sync --frozen --no-dev

# Put virtual environment on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Run MCP server by default over STDIO
ENTRYPOINT ["ufs-chem-pr-review-mcp"]
