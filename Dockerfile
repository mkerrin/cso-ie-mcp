# Build and run the cso-ireland MCP server over streamable HTTP.
#
# Uses the official uv image so the build matches local `uv sync` exactly.
# Dependencies are installed in their own layer (keyed on pyproject.toml +
# uv.lock) so they are only re-resolved when those files change, not on every
# source edit.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# UV_COMPILE_BYTECODE: precompile .pyc at install time for faster cold starts.
# UV_LINK_MODE=copy: avoid hardlink warnings when the cache and venv differ FS.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1) Resolve and install just the dependencies (no project code yet) so this
#    layer is cached across source-only changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# 2) Add the project source and sync once more against the lockfile.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Put the project venv first on PATH so `python` resolves to the venv.
ENV PATH="/app/.venv/bin:$PATH"

# HTTP transport defaults for the container. MCP_HOST must be 0.0.0.0 (not the
# code's 127.0.0.1 default) or the port is unreachable from outside the
# container. Logs go to a file by default; redirect to stderr for `docker logs`.
ENV MCP_TRANSPORT=http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    CSO_LOG_FILE=/dev/stderr

EXPOSE 8000

# Liveness = the HTTP port accepts a TCP connection. (A GET on /mcp returns 406
# since the endpoint wants POST, so a plain connect check is cleaner than
# interpreting status codes.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_PORT','8000'))), timeout=4).close()"]

CMD ["python", "main.py"]
