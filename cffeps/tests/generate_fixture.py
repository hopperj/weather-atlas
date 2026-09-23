#!/usr/bin/env python3
"""Generate the deterministic standard-atmosphere portable-driver fixture."""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixtures"


def main() -> None:
    lines: list[str] = []
    for hour in range(3):
        lines.append(f"2026 7 2 {hour} 0.0075 10.0 283.15")
        for level in range(40):
            height = level * 400.0
            pressure = 101325.0 * math.exp(-height / 8200.0)
            temperature = max(205.0, 291.15 - 0.0062 * height)
            lines.append(f"{pressure:.6f} {temperature:.6f} {height:.6f}")
    (ROOT / "minimal-profiles.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
