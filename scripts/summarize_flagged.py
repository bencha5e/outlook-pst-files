#!/usr/bin/env python3
"""
Turn data/classified.jsonl into a reviewable Markdown report of flagged
("meaningful context") emails, grouped by category and sorted by date, so
you can scan and hand-pick the strongest examples for skill training.

Usage:
    python scripts/summarize_flagged.py [--in data/classified.jsonl] [--out data/flagged_report.md]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

CATEGORY_ORDER = [
    "ire_news_negative",
    "ire_news_positive",
    "ire_recommendation",
    "borrower_decline",
    "covenant_dy_issue",
    "modification_waiver",
    "borrower_approval",
]

CATEGORY_LABELS = {
    "ire_news_negative": "Significant News to IRE - Negative",
    "ire_news_positive": "Significant News to IRE - Positive",
    "ire_recommendation": "Recommendations to IRE",
    "borrower_decline": "Borrower Declines / Pushback",
    "covenant_dy_issue": "Debt Yield / Covenant Issues",
    "modification_waiver": "Modification / Waiver Decisions",
    "borrower_approval": "Borrower Approvals",
}


def load_records(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_path", type=Path, default=Path("data/classified.jsonl"))
    ap.add_argument("--out", dest="out_path", type=Path, default=Path("data/flagged_report.md"))
    args = ap.parse_args()

    by_category = defaultdict(list)
    total = 0
    for record in load_records(args.in_path):
        total += 1
        category = record.get("category", "none")
        if category == "none":
            continue
        by_category[category].append(record)

    flagged_total = sum(len(v) for v in by_category.values())

    lines = [
        "# Flagged Email Report",
        "",
        f"{flagged_total} of {total} parsed messages flagged as carrying meaningful context.",
        "",
        "Review each entry, then hand-pick the strongest ~15-30 examples (spread across "
        "categories) to feed into building the writing-style skill.",
        "",
    ]

    categories_present = CATEGORY_ORDER + [
        c for c in by_category if c not in CATEGORY_ORDER
    ]

    for category in categories_present:
        records = by_category.get(category)
        if not records:
            continue
        records.sort(key=lambda r: r.get("date") or "")
        label = CATEGORY_LABELS.get(category, category)
        lines.append(f"## {label} ({len(records)})")
        lines.append("")
        for r in records:
            lines.append(f"### {r.get('date', 'unknown date')} - {r.get('subject', '(no subject)')}")
            lines.append(f"- **Folder:** {r.get('folder')}  ")
            lines.append(f"- **From:** {r.get('from')}  **To:** {', '.join(r.get('to') or [])}  ")
            lines.append(f"- **Confidence:** {r.get('confidence')}  ")
            lines.append(f"- **Rationale:** {r.get('rationale')}  ")
            if r.get("key_excerpt"):
                lines.append(f"- **Key excerpt:** \"{r['key_excerpt']}\"  ")
            lines.append(f"- **Source:** `{r.get('source_path')}`")
            lines.append("")

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    args.out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote report for {flagged_total} flagged messages to {args.out_path}")


if __name__ == "__main__":
    main()
