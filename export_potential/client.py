"""Read the same anonymous chart endpoints used by ITC's public EPM page.

This is an unofficial integration, not ITC's licensed/premium API. Values are
never estimated. Public page transport and field mappings were inspected on
2026-09-12 (main-YFOHUXRT, chunk-J4C7MEAK, chunk-PDDQILWR).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ORIGIN = "https://exportpotential.intracen.org"
REFERENCES = {"countries", "sub-regions", "regions", "products", "sub-sectors", "sectors"}
# Public browser transport constant; no account credentials or premium API key.
_PAGE_KEY = bytes(ord(c) + 9 for c in "<,+-:/;=)./:;,0*('-/9,))<-0,;+=)")
_CACHE: OrderedDict[str, tuple[float, Any, dict]] = OrderedDict()
_LOCK = threading.Lock()
TTL = 900
_PERIOD_CACHE = None


class SourceError(Exception):
    pass


def period_info() -> dict:
    global _PERIOD_CACHE
    if _PERIOD_CACHE and time.monotonic() - _PERIOD_CACHE[0] < TTL:
        return _PERIOD_CACHE[1]
    url = 'https://umbraco.exportpotential.intracen.org/api/epm2/en/umbraco-data/dictionary/'
    try:
        response = requests.get(url,timeout=(8,15),allow_redirects=False)
        response.raise_for_status()
        year = int(response.json()['EpYear'])
        if not 2020 <= year <= 2100:
            raise ValueError('Unexpected projection year')
    except (requests.RequestException,ValueError,KeyError,TypeError):
        year = None
    result = {'target_year':year,'trade_years':'2020–2024' if year==2030 else None,
              'verified_on':'2026-09-12','source_url':ORIGIN+'/en/resources/data-sources'}
    if year is not None:
        _PERIOD_CACHE = (time.monotonic(),result)
    return result


def decode_public_response(text: str) -> Any:
    """The published site's AES transport wrapper, then ordinary JSON parsing."""
    try:
        raw = base64.b64decode(text, validate=True)
        decryptor = Cipher(algorithms.AES(_PAGE_KEY), modes.CBC(bytes(16))).decryptor()
        clear = decryptor.update(raw) + decryptor.finalize()
        padding = clear[-1]
        if not 1 <= padding <= 16 or clear[-padding:] != bytes([padding]) * padding:
            raise ValueError("Unexpected transport padding")
        return json.loads(clear[:-padding])
    except (ValueError, IndexError, UnicodeError) as exc:
        raise SourceError("ITC response format changed; no replacement values were generated") from exc


def read(path: str) -> tuple[Any, dict]:
    if not path.startswith("/api/en/") or ".." in path or "?" in path:
        raise ValueError("Invalid ITC path")
    with _LOCK:
        cached = _CACHE.get(path)
        if cached and time.monotonic() - cached[0] < TTL:
            _CACHE.move_to_end(path)
            return copy.deepcopy(cached[1]), {**cached[2], "cached": True}
    url = ORIGIN + path
    try:
        response = requests.get(url, headers={"X-Context": "epm2", "X-Format": "camel"},
                                timeout=(8, 35), allow_redirects=False)
        if response.status_code != 200:
            raise SourceError(f"ITC returned HTTP {response.status_code}")
        if len(response.content) > 24_000_000:
            raise SourceError("ITC response exceeded the chart size limit")
        data = decode_public_response(response.text.strip())
    except requests.RequestException as exc:
        raise SourceError("Unable to reach ITC chart data") from exc
    provenance = {"source": "ITC Export Potential Map", "source_url": url,
                  "retrieved_at": datetime.now(timezone.utc).isoformat(),
                  "response_sha256": hashlib.sha256(response.content).hexdigest(),
                  "cached": False, "method": "public_chart_response", "currency": "USD"}
    with _LOCK:
        _CACHE[path] = (time.monotonic(), data, provenance)
        while len(_CACHE) > 40:
            _CACHE.popitem(last=False)
    return copy.deepcopy(data), dict(provenance)


def number(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SourceError(f"Unexpected numeric field: {key}")
    return value


def normalize(row: dict) -> dict:
    if not isinstance(row, dict):
        raise SourceError("ITC chart row schema changed")
    item = row.get("item")
    if not isinstance(item, dict) or "code" not in item or "name" not in item:
        raise SourceError("ITC chart item schema changed")
    if not isinstance(item["name"], str) or not isinstance(item["code"], (str, int)) or isinstance(item["code"], bool):
        raise SourceError("ITC chart identifier schema changed")
    value = number(row, "value")
    gap = number(row, "gap")
    # Same multiplication as the original public chart (gl in PDDQILWR).
    realized = number(row, "realizedPotential")
    untapped = value * (1 - realized) if value is not None and realized is not None else None
    if untapped is not None and not math.isfinite(untapped):
        raise SourceError("ITC chart value exceeds numeric range")
    return {"id": str(item["code"]), "item": item,
            "potential": value, "baseline": number(row, "exportValue"),
            "unrealized": untapped, "gap_ratio": gap,
            "realized_ratio": realized,
            "demand": number(row, "bubbleSize"),
            "ease": number(row, "lineWidth"), "supply": number(row, "lineLength"),
            "tariff": number(row, "tariff"), "raw": row}


def chart_path(axis: str, exporter: str, market: str, product: str,
               from_marker: str, to_marker: str, what_marker: str) -> str:
    for code in (exporter, market, product):
        if not code or len(code) > 24 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in code):
            raise ValueError("Invalid selection code")
    if axis not in {"markets", "products", "exporters"}:
        raise ValueError("Invalid axis")
    if from_marker not in {"i", "w", "r", "re"} or to_marker not in {"j", "w", "r", "re"}:
        raise ValueError("Invalid economy marker")
    if what_marker not in {"k", "a", "s", "ls"}:
        raise ValueError("Invalid product marker")
    e = "all" if exporter == "w" or axis == "exporters" else exporter
    m = "all" if market == "w" or axis == "markets" else market
    p = "all" if product == "a" or axis == "products" else product
    return f"/api/en/epis/{axis}/from/{from_marker}/{e}/to/{to_marker}/{m}/what/{what_marker}/{p}"


def chart(**selection) -> dict:
    path = chart_path(**selection)
    data, provenance = read(path)
    if not isinstance(data, list):
        raise SourceError("ITC did not return a chart dataset")
    rows = [normalize(row) for row in data]
    if len({r["id"] for r in rows}) != len(rows):
        raise SourceError("ITC returned duplicate chart identifiers")
    return {"rows": rows, "count": len(rows), "selection": selection,
            "available": bool(rows), "provenance": provenance}
