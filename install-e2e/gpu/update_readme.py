#!/usr/bin/env python3
"""Render a benchmark results JSON into the README's benchmark section.

Keeps the model-benchmark table on the repo home page always-current: the GPU
CI lane runs the benchmark, then runs this to splice the freshly-rendered table
between two HTML-comment markers in README.md and commits the change (only when
it differs).

Add these two markers to README.md where the table should live:

    <!-- BENCHMARK:START -->
    <!-- BENCHMARK:END -->

Usage:
    python update_readme.py results/sweep-final.json --readme ../../README.md
    python update_readme.py results/sweep-final.json --check   # non-zero if it would change
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

START = "<!-- BENCHMARK:START -->"
END = "<!-- BENCHMARK:END -->"


def _fmt_pct(x: float) -> str:
    return f"{round(x * 100)}%"


def render(doc: dict) -> str:
    """Render the public-facing benchmark section (Markdown)."""
    models = sorted(
        doc.get("models", []),
        key=lambda m: (-m.get("exact_match", 0), (m.get("latency_ms") or {}).get("p50", 1e9)),
    )
    overhead_s = doc.get("voice_overhead_ms", 1600) / 1000

    lines = [
        START,
        "",
        "## 🎙️ Which local model routes voice best?",
        "",
        (
            f"How well each local model routes canned voice commands to the right built-in "
            f"tool — through command-center's real `/voice/command` path, "
            f"{doc.get('corpus_size', '?')} utterances across 7 tool categories + small-talk "
            f"negatives. Higher accuracy = fewer wrong/missed actions; lower latency = snappier."
        ),
        "",
        "| Model | Correct tool | Correct args | Never mis-fires | Routing (p50) | Est. spoken response |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for m in models:
        lat = m.get("latency_ms") or {}
        perceived = m.get("perceived_latency_ms")
        perceived_str = f"~{perceived / 1000:.1f}s" if perceived else "—"
        p50 = lat.get("p50")
        p50_str = f"{round(p50)}ms" if p50 is not None else "—"
        lines.append(
            f"| **{m['display']}** | {_fmt_pct(m['tool_accuracy'])} | "
            f"{_fmt_pct(m['arg_accuracy'])} | {_fmt_pct(m.get('negative_accuracy', 0))} | "
            f"{p50_str} | {perceived_str} |"
        )
    lines += [
        "",
        (
            f"<sub>GPU: **{doc.get('gpu', 'unknown')}** · "
            f"“Est. spoken response” = routing p50 + ~{overhead_s:.1f}s STT+TTS overhead · "
            f"generated {doc.get('generated_at', '')[:10]} · "
            f"[how this is measured](install-e2e/gpu/BENCHMARK.md)</sub>"
        ),
        "",
        END,
    ]
    return "\n".join(lines)


def splice(readme: str, section: str) -> str:
    if START not in readme or END not in readme:
        raise SystemExit(
            f"README is missing the {START} / {END} markers — add them where the "
            f"benchmark table should appear."
        )
    pre = readme[: readme.index(START)]
    post = readme[readme.index(END) + len(END) :]
    return pre + section + post


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", help="benchmark results JSON")
    ap.add_argument("--readme", default="README.md", help="target README path")
    ap.add_argument("--check", action="store_true", help="exit non-zero if the README would change (no write)")
    args = ap.parse_args()

    doc = json.loads(Path(args.results).read_text())
    if not doc.get("models"):
        raise SystemExit("results JSON has no models")
    section = render(doc)

    readme_path = Path(args.readme)
    original = readme_path.read_text()
    updated = splice(original, section)

    if args.check:
        if original != updated:
            print("README benchmark section is out of date")
            sys.exit(1)
        print("README benchmark section is current")
        return

    if original == updated:
        print("README benchmark section already current — no change")
        return
    readme_path.write_text(updated)
    print(f"updated {readme_path} benchmark section ({len(doc['models'])} models)")


if __name__ == "__main__":
    main()
