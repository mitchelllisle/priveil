"""Generate benchmarks/results.json and inject data into benchmarks/index.html.

Steps
-----
1. Strip per-round raw timing arrays (stats.data) — removes ~10 MB.
2. Load scenario metadata from benchmarks/data/*.json.
3. Call /detect for each scenario so the dashboard can show highlighted spans.
4. Write cleaned results.json (for git diff).
5. Inject the JSON into index.html so it works when opened via file://.

Usage
-----
    python benchmarks/generate_report.py benchmarks/results.json [API_URL]

API_URL defaults to the PRIVEIL_API_URL environment variable, then
http://localhost:8000. Detections are skipped with a warning if the API
is unreachable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BENCH_DIR = Path(__file__).parent
_DATA_DIR  = _BENCH_DIR / "data"
_HTML      = _BENCH_DIR / "index.html"

_TAG_OPEN  = '<script id="bench-data" type="application/json">'
_TAG_CLOSE = "</script>"


# ── scenario loader ────────────────────────────────────────────────────────────

def _load_scenarios() -> dict[str, dict]:
    scenarios: dict[str, dict] = {}
    for path in sorted(_DATA_DIR.glob("*.json")):
        meta = json.loads(path.read_text())
        scenarios[meta["name"]] = meta
    return scenarios


# ── detection fetching ─────────────────────────────────────────────────────────

def _fetch_detections(scenarios: dict[str, dict], api_url: str) -> None:
    """Call /detect for each scenario and store results in-place.

    Skips gracefully if the API is unreachable — the dashboard still renders
    timing stats; clicking a scenario shows 'no detection data available'.
    """
    try:
        import httpx
    except ImportError:
        print("  httpx not available — skipping detection fetch")
        return

    print(f"  Fetching detections from {api_url} ...")
    with httpx.Client(base_url=api_url, timeout=30.0) as client:
        for name, meta in scenarios.items():
            try:
                resp = client.post(
                    "/detect",
                    json={"text": meta["text"], "mode": meta.get("mode", "fast")},
                )
                resp.raise_for_status()
                meta["detections"] = resp.json()["data"]
                n = len(meta["detections"].get("entities", []))
                print(f"    {name}: {n} entities")
            except Exception as exc:
                print(f"    {name}: failed ({exc})")
                meta["detections"] = None


# ── HTML injection ─────────────────────────────────────────────────────────────

def _inject_html(data: dict) -> None:
    html  = _HTML.read_text(encoding="utf-8")
    start = html.index(_TAG_OPEN) + len(_TAG_OPEN)
    end   = html.index(_TAG_CLOSE, start)
    html  = html[:start] + json.dumps(data, separators=(",", ":")) + html[end:]
    _HTML.write_text(html, encoding="utf-8")


# ── main ───────────────────────────────────────────────────────────────────────

def generate(results_path: Path, api_url: str) -> None:
    data = json.loads(results_path.read_text())

    for bench in data.get("benchmarks", []):
        bench.get("stats", {}).pop("data", None)

    scenarios = _load_scenarios()
    _fetch_detections(scenarios, api_url)
    data["scenarios"] = scenarios

    results_path.write_text(json.dumps(data, indent=2) + "\n")
    _inject_html(data)

    size_kb = results_path.stat().st_size // 1024
    html_kb = _HTML.stat().st_size // 1024
    n_bench = len(data.get("benchmarks", []))
    n_sc    = len(scenarios)
    print(
        f"Wrote {results_path} ({size_kb} KB, {n_bench} benchmarks, {n_sc} scenarios)\n"
        f"Wrote {_HTML} ({html_kb} KB — open directly in browser)"
    )


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(f"Usage: {sys.argv[0]} <results.json> [api_url]")
    url = sys.argv[2] if len(sys.argv) == 3 else os.environ.get("PRIVEIL_API_URL", "http://localhost:8000")
    generate(Path(sys.argv[1]), url.rstrip("/"))
