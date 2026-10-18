# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

An MCP (Model Context Protocol) server that exposes the Central Statistics Office
(CSO) Ireland open data via the [PxStat Cube RESTful API](https://github.com/CSOIreland/PxStat/wiki/API-Cube-RESTful).
It lets an MCP client discover, inspect, and retrieve CSO statistical datasets
("cubes", ~12,600 of them). No API key or auth is required; data comes from the
live API at `https://ws.cso.ie/public/api.restful`.

## Commands

```sh
uv run python main.py        # run the MCP server (serves over stdio)
MCP_TRANSPORT=http MCP_PORT=8000 uv run python main.py   # serve over streamable HTTP (:8000/mcp)
docker compose up --build    # build + run the HTTP server in a container (:8000/mcp)
uv sync                      # install/sync dependencies from uv.lock
```

The transport defaults to stdio; set `MCP_TRANSPORT=http` for streamable HTTP.
The server uses mcp 2.x (`mcp.server.mcpserver.MCPServer`, the renamed
`FastMCP`), which takes the bind address in `run()`, so `MCP_HOST`/`MCP_PORT`
are read in `main()` and passed to `run(transport="streamable-http", ...)`
(defaults `127.0.0.1` / `8000`). The HTTP endpoint is `/mcp`.

The `Dockerfile` (uv base image, deps cached in their own layer) is HTTP-only by
design: it bakes in `MCP_TRANSPORT=http`, `MCP_HOST=0.0.0.0` (the code's
`127.0.0.1` default would make the container unreachable), and points
`CSO_LOG_FILE` at `/dev/stderr` so `docker logs` shows requests. The `HEALTHCHECK`
is a TCP connect to the port — a GET on `/mcp` returns 406 (it wants POST), so a
status-code check would mislead. `docker-compose.yml` wraps it for
`docker compose up --build`.

There is currently no test suite, linter config, or build step. Python >=3.12.

Per-request logging (every CSO HTTP request/response) is appended to `/tmp/cso.log`
(override with `CSO_LOG_FILE`) — tail it to debug API interactions, since stdio is
consumed by the MCP protocol.

## Architecture

Two files, a clean split between transport and data access:

- **`main.py`** — the MCP layer. Defines the `MCPServer("cso-ireland")` server and
  the four `@mcp.tool()` functions (`list_datasets`, `search_datasets`,
  `get_dataset_metadata`, `get_dataset`). Tools only shape arguments/results and
  delegate to a single module-level `CSOClient`. Tool docstrings are the user-facing
  contract (they become the tool descriptions the model sees) — keep them accurate.
- **`cso.py`** — the API client. `CSOClient` wraps the three PxStat endpoints
  (`ReadCollection`, `ReadMetadata`, `ReadDataset`) over a shared `httpx.AsyncClient`.
  `DatasetRecord` is the lightweight in-memory summary of one cube.

### Key behaviors to preserve

- **Collection caching.** `ReadCollection` returns a ~40 MB JSON-stat document
  describing every dataset. It is fetched once and cached in memory as a list of
  `DatasetRecord` (6-hour TTL, `_COLLECTION_TTL_SECONDS`). `list_datasets` and
  `search_datasets` are served entirely from this cache — only the first call after
  startup pays the download cost. Don't add per-call fetches of the full collection.
- **`ReadCollection` path args are positional.** Its optional `{datefrom}`/`{language}`
  segments are positional — passing language alone is misread as a date and 500s.
  It is intentionally called bare. See the comment in `get_collection`.
- **Search** is a simple AND-match: all space-separated terms (case-insensitive) must
  appear in the concatenated matrix code + label + dimension names (`DatasetRecord._haystack`).
- **Result capping** is deliberate to keep payloads small: list/search limits clamp to
  1–200; `get_dataset_metadata` caps category lists at 50 values (with a
  `categories_truncated` flag). Datasets can be huge — `get_dataset` defaults to the
  compact `csv` format.

### Typical client flow

`search_datasets("population county")` → pick a `matrix` code →
`get_dataset_metadata("B0101")` (gauge size: product of dimension sizes = cell count) →
`get_dataset("B0101")`.
