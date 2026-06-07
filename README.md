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
uv run python main.py        # serves over stdio
```

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
