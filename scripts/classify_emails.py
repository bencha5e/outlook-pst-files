#!/usr/bin/env python3
"""
Classify each message in data/messages.jsonl against the taxonomy in
scripts/taxonomy.md, using the Claude API.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/classify_emails.py [--in data/messages.jsonl] [--out data/classified.jsonl]
                                       [--model claude-haiku-4-5-20251001] [--limit N]

Requires: pip install anthropic

Cheap pre-filter: messages whose subject looks like a calendar invite,
auto-reply, or out-of-office notice are tagged "none" without an API call.
Resumable: message_ids already present in --out are skipped on re-run, so a
killed run can just be restarted with the same command.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("error: pip install anthropic")

NOISE_SUBJECT_RE = re.compile(
    r"^(accepted:|declined:|tentative:|canceled:|cancelled:|invitation:|"
    r"updated invitation:|automatic reply:|auto[- ]?reply:|out of office)",
    re.IGNORECASE,
)

CATEGORIES = [
    "borrower_decline",
    "borrower_approval",
    "ire_recommendation",
    "ire_news_positive",
    "ire_news_negative",
    "covenant_dy_issue",
    "modification_waiver",
    "none",
]

CLASSIFY_TOOL = {
    "name": "classify_email",
    "description": "Record the classification of a single email against the fixed taxonomy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Confidence in this category assignment.",
            },
            "rationale": {
                "type": "string",
                "description": "One sentence explaining why this category was chosen.",
            },
            "key_excerpt": {
                "type": "string",
                "description": "The sentence or short passage from the email body that most "
                "supports the classification. Empty string if category is 'none'.",
            },
        },
        "required": ["category", "confidence", "rationale", "key_excerpt"],
    },
}


def load_taxonomy() -> str:
    taxonomy_path = Path(__file__).parent / "taxonomy.md"
    return taxonomy_path.read_text(encoding="utf-8")


def build_system_prompt(taxonomy: str) -> list:
    return [
        {
            "type": "text",
            "text": (
                "You are classifying emails from a commercial real estate asset manager's "
                "Outlook mailbox for a training-data curation project. For each email, call "
                "the classify_email tool exactly once with the best-fitting category.\n\n"
                + taxonomy
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def is_noise(record: dict) -> bool:
    return bool(NOISE_SUBJECT_RE.match(record.get("subject", "")))


def load_done_ids(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    done = set()
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["message_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def classify_one(client, model: str, system_prompt: list, record: dict, max_retries: int = 4) -> dict:
    user_content = (
        f"Folder: {record['folder']}\n"
        f"Date: {record.get('date')}\n"
        f"From: {record.get('from')}\n"
        f"To: {', '.join(record.get('to') or [])}\n"
        f"Subject: {record.get('subject')}\n\n"
        f"Body:\n{(record.get('body_text') or '')[:6000]}"
    )

    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=400,
                system=system_prompt,
                tools=[CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "classify_email"},
                messages=[{"role": "user", "content": user_content}],
            )
            for block in resp.content:
                if block.type == "tool_use" and block.name == "classify_email":
                    return block.input
            raise RuntimeError("no tool_use block in response")
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 529) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("classification failed after retries")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_path", type=Path, default=Path("data/messages.jsonl"))
    ap.add_argument("--out", dest="out_path", type=Path, default=Path("data/classified.jsonl"))
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--limit", type=int, default=None, help="max messages to classify this run")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("error: set ANTHROPIC_API_KEY")

    client = anthropic.Anthropic()
    taxonomy = load_taxonomy()
    system_prompt = build_system_prompt(taxonomy)

    done_ids = load_done_ids(args.out_path)
    args.out_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    with open(args.in_path, encoding="utf-8") as in_f, open(args.out_path, "a", encoding="utf-8") as out_f:
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record["message_id"] in done_ids:
                continue
            if args.limit is not None and processed >= args.limit:
                break

            if is_noise(record):
                classification = {
                    "category": "none",
                    "confidence": "high",
                    "rationale": "Calendar/auto-reply/out-of-office subject pattern.",
                    "key_excerpt": "",
                }
                method = "regex"
            else:
                try:
                    classification = classify_one(client, args.model, system_prompt, record)
                    method = "llm"
                except Exception as exc:
                    print(f"warn: classify failed for {record['message_id']}: {exc}", file=sys.stderr)
                    processed += 1
                    continue

            out_record = {**record, **classification, "classification_method": method}
            out_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
            out_f.flush()
            processed += 1

            if processed % 25 == 0:
                print(f"...{processed} classified this run", file=sys.stderr)

    print(f"done: {processed} messages classified this run, output in {args.out_path}")


if __name__ == "__main__":
    main()
