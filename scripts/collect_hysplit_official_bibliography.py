#!/usr/bin/env python3
"""Export the two official NOAA HYSPLIT publication lists to CSV."""

from __future__ import annotations

import argparse
import csv
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


PAGES = {
    "noaa_model_publications": (
        "https://www.arl.noaa.gov/hysplit/"
        "hysplit-publications-meteorological-data-information/"
    ),
    "noaa_application_references": (
        "https://www.arl.noaa.gov/hysplit/hysplit-references/"
    ),
}


class MainListParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.main_depth = 0
        self.items: list[tuple[str, list[str]]] = []
        self.item_stack: list[dict[str, list[str]]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if not self.main_depth and attributes.get("id") == "main":
            self.main_depth = 1
            return
        if not self.main_depth:
            return
        self.main_depth += 1
        if tag == "li":
            self.item_stack.append({"text": [], "links": []})
        if tag == "a" and self.item_stack and attributes.get("href"):
            href = urllib.parse.urljoin(self.base_url, attributes["href"])
            self.item_stack[-1]["links"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if not self.main_depth:
            return
        if tag == "li" and self.item_stack:
            item = self.item_stack.pop()
            text = re.sub(r"\s+", " ", " ".join(item["text"])).strip()
            if text:
                self.items.append((text, item["links"]))
        self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.item_stack:
            self.item_stack[-1]["text"].append(data)


def fetch_html(url: str, attempts: int = 4) -> str:
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": "weatherapp-literature-index/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            socket.timeout,
            TimeoutError,
        ):
            if attempt == attempts - 1:
                raise
            time.sleep(min(2**attempt, 15))
    raise RuntimeError("unreachable")


def collect(page_name: str, url: str) -> list[dict[str, str | int]]:
    html = fetch_html(url)

    parser = MainListParser(url)
    parser.feed(html)
    rows = []
    for text, links in parser.items:
        if text == "About HYSPLIT":
            break
        if text == "Other Publications referencing HYSPLIT":
            break
        rows.append(
            {
                "official_order": len(rows) + 1,
                "list": page_name,
                "citation_as_published_by_noaa": text,
                "links": "; ".join(dict.fromkeys(links)),
                "source_page": url,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "docs/research/atmospheric-transport/"
            "hysplit_noaa_official_bibliography.csv"
        ),
    )
    args = parser.parse_args()

    rows = [
        row
        for page_name, url in PAGES.items()
        for row in collect(page_name, url)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "official_order",
                "list",
                "citation_as_published_by_noaa",
                "links",
                "source_page",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
