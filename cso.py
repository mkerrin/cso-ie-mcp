"""Client for the CSO Ireland PxStat Cube RESTful API.

Docs: https://github.com/CSOIreland/PxStat/wiki/API-Cube-RESTful

The collection endpoint returns a ~40MB JSON-stat document describing all
~12,600 datasets, so it is fetched once and cached as a list of lightweight
records. Everything else (metadata, data) is fetched on demand per matrix.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

BASE_URL = "https://ws.cso.ie/public/api.restful"
DEFAULT_LANGUAGE = "en"

# The full collection rarely changes within a session; cache it for a while.
_COLLECTION_TTL_SECONDS = 6 * 60 * 60

LOG_FILE = "/tmp/cso.log"


def _build_logger() -> logging.Logger:
    """A logger that appends every CSO request/response to LOG_FILE."""
    logger = logging.getLogger("cso")
    logger.setLevel(logging.INFO)
    # Avoid stacking duplicate handlers if the module is imported more than once.
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == LOG_FILE
        for h in logger.handlers
    ):
        handler = logging.FileHandler(LOG_FILE)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
        logger.propagate = False
    return logger


log = _build_logger()


async def _log_request(request: httpx.Request) -> None:
    log.info("--> %s %s", request.method, request.url)


async def _log_response(response: httpx.Response) -> None:
    request = response.request
    log.info("<-- %s %s %s", response.status_code, request.method, request.url)


@dataclass(frozen=True)
class DatasetRecord:
    """A lightweight summary of one dataset (cube) from the collection."""

    matrix: str
    label: str
    updated: str | None
    dimensions: tuple[str, ...]
    href: str | None

    @property
    def _haystack(self) -> str:
        return " ".join(
            [self.matrix, self.label, *self.dimensions]
        ).casefold()

    def matches(self, terms: list[str]) -> bool:
        """True when every search term appears in matrix/label/dimensions."""
        hay = self._haystack
        return all(term in hay for term in terms)

    def as_dict(self) -> dict:
        return {
            "matrix": self.matrix,
            "label": self.label,
            "updated": self.updated,
            "dimensions": list(self.dimensions),
            "href": self.href,
        }


class CSOClient:
    """Thin wrapper around the PxStat Cube RESTful endpoints."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
            event_hooks={"request": [_log_request], "response": [_log_response]},
        )
        self._collection: list[DatasetRecord] | None = None
        self._collection_fetched_at: float = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- collection -------------------------------------------------------

    async def get_collection(self, force_refresh: bool = False) -> list[DatasetRecord]:
        """Return all dataset summaries, fetching and caching as needed."""
        fresh = (
            self._collection is not None
            and (time.monotonic() - self._collection_fetched_at) < _COLLECTION_TTL_SECONDS
        )
        if fresh and not force_refresh:
            return self._collection  # type: ignore[return-value]

        # ReadCollection takes optional {datefrom}/{language} path segments,
        # but they are positional: passing the language alone is misread as a
        # date and 500s. Call it bare to get the full live collection.
        resp = await self._client.get("/PxStat.Data.Cube_API.ReadCollection")
        resp.raise_for_status()
        payload = resp.json()

        records: list[DatasetRecord] = []
        for item in payload.get("link", {}).get("item", []):
            extension = item.get("extension", {}) or {}
            matrix = extension.get("matrix")
            if not matrix:
                continue
            dimensions = tuple(
                dim.get("label", "")
                for dim in (item.get("dimension", {}) or {}).values()
            )
            records.append(
                DatasetRecord(
                    matrix=matrix,
                    label=item.get("label", ""),
                    updated=item.get("updated"),
                    dimensions=dimensions,
                    href=item.get("href"),
                )
            )

        self._collection = records
        self._collection_fetched_at = time.monotonic()
        return records

    async def search(self, query: str, limit: int) -> list[DatasetRecord]:
        records = await self.get_collection()
        terms = [t for t in query.casefold().split() if t]
        if not terms:
            return records[:limit]
        return [r for r in records if r.matches(terms)][:limit]

    # -- single dataset ---------------------------------------------------

    async def get_metadata(
        self, matrix: str, language: str = DEFAULT_LANGUAGE
    ) -> dict:
        resp = await self._client.get(
            f"/PxStat.Data.Cube_API.ReadMetadata/{matrix}/{language}"
        )
        resp.raise_for_status()
        return resp.json()

    async def get_dataset(
        self,
        matrix: str,
        fmt: str = "JSON-stat",
        version: str = "2.0",
        language: str = DEFAULT_LANGUAGE,
    ) -> httpx.Response:
        resp = await self._client.get(
            f"/PxStat.Data.Cube_API.ReadDataset/{matrix}/{fmt}/{version}/{language}"
        )
        resp.raise_for_status()
        return resp
