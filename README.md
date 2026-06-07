# cso-mcp-py

An [MCP](https://modelcontextprotocol.io) server for the **Central Statistics
Office (CSO) Ireland** open data, served via the
[PxStat Cube RESTful API](https://github.com/CSOIreland/PxStat/wiki/API-Cube-RESTful).

It lets an MCP client (Claude Desktop, Claude Code, etc.) discover, inspect, and
retrieve CSO statistical datasets ("cubes") — around 12,600 of them.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_datasets(limit, offset)` | Page through the full catalogue. |
| `search_datasets(query, limit)` | Keyword search over matrix code, label, and dimension names (all space-separated terms must match). |
| `get_dataset_metadata(matrix, language)` | A dataset's dimensions and their categories — inspect this before fetching data. |
| `get_dataset(matrix, format, language)` | The dataset's data as `csv` (default) or `json-stat`. |

A typical flow: `search_datasets("population county")` → pick a `matrix` code →
`get_dataset_metadata("B0101")` → `get_dataset("B0101")`.

## Notes

- Data comes from the live API at `https://ws.cso.ie/public/api.restful`. No
  API key or authentication is required.
- The catalogue (`ReadCollection`) is a ~40 MB document, so it is fetched once
  and cached in memory (6-hour TTL) as lightweight records. List and search are
  served from that cache; the first call after startup is the slow one.
- Datasets can be large — check `get_dataset_metadata` (the product of the
  dimension sizes is the number of data cells) before calling `get_dataset`.

## Run

```sh
uv run python main.py        # serves over stdio (default)

# serve over streamable HTTP at http://127.0.0.1:8000/mcp
MCP_TRANSPORT=http MCP_PORT=8000 uv run python main.py
```

The transport is chosen by `MCP_TRANSPORT` (`stdio` by default, or `http`).
Under HTTP the bind address comes from `MCP_HOST` / `MCP_PORT` (defaults
`127.0.0.1` / `8000`) and the endpoint is `/mcp`.

### Docker (HTTP)

```sh
docker compose up --build    # builds the image, serves HTTP at :8001/mcp
```

Compose maps host port **8001** → container 8000 so this can run alongside the
`data-gov-ie` server (which uses 8000). The image is HTTP-only: it sets
`MCP_HOST=0.0.0.0` so the port is reachable from outside the container and sends
request logs to stderr (`CSO_LOG_FILE=/dev/stderr`) so `docker logs` shows them.

## Register with an MCP client

Claude Code:

```sh
claude mcp add cso-ireland -- uv --directory /home/michael/src/opendatamcp/cso-mcp-py run python main.py
```

Or in a `mcpServers` config block (e.g. Claude Desktop's
`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cso-ireland": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/michael/src/opendatamcp/cso-mcp-py",
        "run",
        "python",
        "main.py"
      ]
    }
  }
}
```
