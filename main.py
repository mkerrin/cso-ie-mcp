"""MCP server exposing the CSO Ireland PxStat statistical datasets.

Wraps the PxStat Cube RESTful API so an assistant can discover (list/search),
inspect (metadata), and retrieve CSO statistical datasets ("cubes").

Docs: https://github.com/CSOIreland/PxStat/wiki/API-Cube-RESTful
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from cso import DEFAULT_LANGUAGE, CSOClient

# Host/port only matter under the HTTP transport, but FastMCP takes them at
# construction time, so configure them here from the environment.
mcp = FastMCP(
    "cso-ireland",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8000")),
)
client = CSOClient()


@mcp.tool()
async def list_datasets(limit: int = 50, offset: int = 0) -> dict:
    """List CSO Ireland statistical datasets.

    The full catalogue holds ~12,600 datasets, so results are paginated.

    Args:
        limit: Maximum number of datasets to return (1-200).
        offset: Number of datasets to skip, for paging through the catalogue.

    Returns:
        Total catalogue size, the page returned, and a list of dataset
        summaries (matrix code, label, last-updated date, dimensions).
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    records = await client.get_collection()
    page = records[offset : offset + limit]
    return {
        "total": len(records),
        "offset": offset,
        "count": len(page),
        "datasets": [r.as_dict() for r in page],
    }


@mcp.tool()
async def search_datasets(query: str, limit: int = 25) -> dict:
    """Search CSO Ireland datasets by keyword.

    Matches space-separated terms (case-insensitive, all must match) against
    each dataset's matrix code, label, and dimension names. For example
    "population census county" finds census population tables by county.

    Args:
        query: Space-separated search terms.
        limit: Maximum number of matches to return (1-200).

    Returns:
        The number of matches found and a list of dataset summaries. Use a
        returned `matrix` code with get_dataset_metadata or get_dataset.
    """
    limit = max(1, min(limit, 200))
    matches = await client.search(query, limit)
    return {
        "query": query,
        "count": len(matches),
        "datasets": [r.as_dict() for r in matches],
    }


@mcp.tool()
async def get_dataset_metadata(matrix: str, language: str = DEFAULT_LANGUAGE) -> dict:
    """Get the structure of a dataset: its dimensions and categories.

    Use this to understand a dataset before retrieving its data — it reveals
    the dimensions (e.g. Year, County, Statistic) and the category values
    available within each.

    Args:
        matrix: The dataset's matrix code (e.g. "B0101"), from list/search.
        language: Metadata language code (default "en").

    Returns:
        The dataset label, last-updated date, and a per-dimension breakdown
        of category counts and labels (category lists capped at 50 values).
    """
    meta = await client.get_metadata(matrix, language)
    dim_ids = meta.get("id", [])
    sizes = meta.get("size", [])
    dimension = meta.get("dimension", {}) or {}

    dimensions = []
    for idx, dim_id in enumerate(dim_ids):
        dim = dimension.get(dim_id, {}) or {}
        category = dim.get("category", {}) or {}
        labels = category.get("label", {}) or {}
        category_labels = list(labels.values())
        dimensions.append(
            {
                "id": dim_id,
                "label": dim.get("label", dim_id),
                "size": sizes[idx] if idx < len(sizes) else len(category_labels),
                "categories": category_labels[:50],
                "categories_truncated": len(category_labels) > 50,
            }
        )

    return {
        "matrix": matrix,
        "label": meta.get("label"),
        "updated": meta.get("updated"),
        "dimensions": dimensions,
    }


@mcp.tool()
async def get_dataset(
    matrix: str, format: str = "csv", language: str = DEFAULT_LANGUAGE
) -> str:
    """Retrieve the actual data for a dataset.

    Datasets can be large; "csv" is the most compact format and is the
    default. Inspect get_dataset_metadata first to gauge size (the product of
    the dimension sizes is the number of data cells).

    Args:
        matrix: The dataset's matrix code (e.g. "B0101"), from list/search.
        format: One of "csv" or "json-stat" (default "csv").
        language: Data language code (default "en").

    Returns:
        CSV text, or JSON-stat 2.0 text, for the dataset.
    """
    fmt = format.strip().lower()
    if fmt == "csv":
        resp = await client.get_dataset(
            matrix, fmt="CSV", version="1.0", language=language
        )
        return resp.text
    if fmt in ("json-stat", "jsonstat", "json"):
        resp = await client.get_dataset(
            matrix, fmt="JSON-stat", version="2.0", language=language
        )
        return resp.text
    raise ValueError(f"Unsupported format {format!r}; use 'csv' or 'json-stat'.")


def main() -> None:
    """Entry point. Defaults to stdio; set MCP_TRANSPORT=http for streamable HTTP.

    HTTP bind address is controlled by MCP_HOST / MCP_PORT (see FastMCP
    construction above).
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    try:
        if transport == "http":
            mcp.run(transport="streamable-http")
        else:
            mcp.run()
    finally:
        import anyio

        try:
            anyio.run(client.aclose)
        except Exception:
            pass


if __name__ == "__main__":
    main()
