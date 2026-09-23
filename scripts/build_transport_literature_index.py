#!/usr/bin/env python3
"""Build reproducible FLEXPART and HYSPLIT literature indexes from OpenAlex."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any


API_URL = "https://api.openalex.org/works"
SELECT_FIELDS = ",".join(
    (
        "id",
        "doi",
        "display_name",
        "publication_year",
        "authorships",
        "primary_location",
        "type",
        "cited_by_count",
        "open_access",
    )
)
SEARCHES = {
    "FLEXPART": "FLEXPART",
    "HYSPLIT": "HYSPLIT",
}
CSV_FIELDS = (
    "model",
    "relevance_tier",
    "year",
    "title",
    "authors",
    "source",
    "work_type",
    "doi",
    "landing_page",
    "open_access_status",
    "is_oa",
    "cited_by_count",
    "openalex_id",
)


def request_json(params: dict[str, str | int], attempts: int = 8) -> dict[str, Any]:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "weatherapp-literature-index/1.0"}
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=60
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if attempt == attempts - 1:
                raise
            retry_after = error.headers.get("Retry-After")
            if error.code == 429 and retry_after and retry_after.isdigit():
                delay = min(max(int(retry_after), 1), 120)
            elif error.code == 429:
                delay = min(5 * 2**attempt, 120)
            else:
                delay = min(2**attempt, 30)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(min(2**attempt, 30))
    raise RuntimeError("unreachable")


def iter_works(search: str) -> Iterable[dict[str, Any]]:
    cursor = "*"
    while cursor:
        payload = request_json(
            {
                "search": search,
                "per-page": 200,
                "cursor": cursor,
                "select": SELECT_FIELDS,
            }
        )
        yield from payload["results"]
        cursor = payload["meta"].get("next_cursor")
        if not payload["results"]:
            break


def authors_for(work: dict[str, Any]) -> str:
    names = []
    for authorship in work.get("authorships") or []:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            names.append(name)
    return "; ".join(names)


def relevance_tier(model: str, title: str) -> str:
    normalized = title.casefold()
    model_tokens = {
        "FLEXPART": ("flexpart", "flexible particle dispersion"),
        "HYSPLIT": (
            "hysplit",
            "hy-split",
            "hybrid single-particle lagrangian integrated",
        ),
    }
    if any(token in normalized for token in model_tokens[model]):
        return "core_or_named_application"
    return "fulltext_mention"


def normalize_work(model: str, work: dict[str, Any]) -> dict[str, Any]:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    oa = work.get("open_access") or {}
    title = work.get("display_name") or ""
    return {
        "model": model,
        "relevance_tier": relevance_tier(model, title),
        "year": work.get("publication_year") or "",
        "title": title,
        "authors": authors_for(work),
        "source": source.get("display_name") or "",
        "work_type": work.get("type") or "",
        "doi": work.get("doi") or "",
        "landing_page": location.get("landing_page_url") or "",
        "open_access_status": oa.get("oa_status") or "",
        "is_oa": oa.get("is_oa", ""),
        "cited_by_count": work.get("cited_by_count") or 0,
        "openalex_id": work.get("id") or "",
    }


def dedupe_key(row: dict[str, Any]) -> str:
    if row["doi"]:
        return str(row["doi"]).casefold()
    title = re.sub(r"\W+", "", str(row["title"]).casefold())
    return f"{title}:{row['year']}"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    tier = 0 if row["relevance_tier"] == "core_or_named_application" else 1
    year = int(row["year"]) if row["year"] else 0
    citations = int(row["cited_by_count"])
    return (tier, -year, -citations, str(row["title"]).casefold())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/research/atmospheric-transport"),
    )
    parser.add_argument(
        "--from-existing",
        action="store_true",
        help=(
            "Rebuild filtered and deduplicated files from existing "
            "*_openalex.csv exports without calling OpenAlex"
        ),
    )
    args = parser.parse_args()

    all_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "source": "OpenAlex",
        "api": API_URL,
        "retrieved_on": date.today().isoformat(),
        "query_semantics": "OpenAlex search (full-text search at retrieval time)",
        "searches": {},
    }

    for model, search in SEARCHES.items():
        broad_export = args.output_dir / f"{model.casefold()}_openalex.csv"
        if args.from_existing:
            rows = read_csv(broad_export)
        else:
            rows = [normalize_work(model, work) for work in iter_works(search)]
        rows.sort(key=sort_key)
        write_csv(broad_export, rows)
        title_matches = [
            row
            for row in rows
            if row["relevance_tier"] == "core_or_named_application"
        ]
        write_csv(
            args.output_dir / f"{model.casefold()}_title_matches.csv",
            title_matches,
        )
        all_rows.extend(rows)
        summary["searches"][model] = {
            "query": search,
            "retrieved_rows": len(rows),
            "core_or_named_application": len(title_matches),
            "fulltext_mention": sum(
                row["relevance_tier"] == "fulltext_mention" for row in rows
            ),
        }

    deduped: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        key = dedupe_key(row)
        if key in deduped:
            models = set(str(deduped[key]["model"]).split(";"))
            models.add(str(row["model"]))
            deduped[key]["model"] = ";".join(sorted(models))
            if row["relevance_tier"] == "core_or_named_application":
                deduped[key]["relevance_tier"] = row["relevance_tier"]
        else:
            deduped[key] = row.copy()

    combined = sorted(deduped.values(), key=sort_key)
    write_csv(args.output_dir / "combined_openalex_deduplicated.csv", combined)
    summary["combined_deduplicated_rows"] = len(combined)
    with (args.output_dir / "openalex_search_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
