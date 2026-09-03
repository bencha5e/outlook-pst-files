#!/usr/bin/env python3
"""
Walk a readpst .eml export tree and emit one JSON record per message to
data/messages.jsonl.

Usage:
    python scripts/parse_emails.py <readpst_output_dir> [--out data/messages.jsonl]

Expects the directory layout readpst produces, e.g.:
    <readpst_output_dir>/Inbox/1.eml, 2.eml, ...
    <readpst_output_dir>/Sent Items/1.eml, 2.eml, ...

Only folders whose path contains "Inbox" or "Sent" are processed; everything
else (Calendar, Contacts, Deleted Items, etc.) is skipped.
"""
import argparse
import email
import email.message
import json
import re
import sys
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

RELEVANT_FOLDER_RE = re.compile(r"inbox|sent", re.IGNORECASE)

# Lines that mark the start of a quoted reply chain in plain-text bodies.
QUOTE_MARKERS = re.compile(
    r"^\s*(-{2,}\s*Original Message\s*-{2,}|"
    r"From:\s.+|"
    r"On .+ wrote:|"
    r"_{5,})\s*$",
    re.IGNORECASE,
)

# Common signature block delimiter.
SIGNATURE_MARKER = re.compile(r"^\s*--\s*$|^\s*Sent from my ")


def strip_html(html_body: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_body)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def get_body_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, TypeError):
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
        if plain is not None:
            return plain
        if html is not None:
            return strip_html(html)
        return ""
    else:
        try:
            payload = msg.get_payload(decode=True)
        except Exception:
            payload = None
        if payload is None:
            return msg.get_payload() or ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, TypeError):
            text = payload.decode("utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            return strip_html(text)
        return text


def strip_quotes_and_signature(body: str) -> str:
    lines = body.splitlines()
    cut = len(lines)
    for i, line in enumerate(lines):
        if QUOTE_MARKERS.match(line) or SIGNATURE_MARKER.match(line):
            cut = i
            break
    trimmed = "\n".join(lines[:cut]).strip()
    return trimmed if trimmed else body.strip()


def parse_date(msg: email.message.Message):
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        return raw


def addr_list(msg: email.message.Message, header: str):
    raw = msg.get(header, "")
    if not raw:
        return []
    return [parseaddr(a)[1] or parseaddr(a)[0] for a in raw.split(",") if a.strip()]


def classify_folder(path: Path) -> str:
    parts_lower = " ".join(p.lower() for p in path.parts)
    if "sent" in parts_lower:
        return "Sent"
    if "inbox" in parts_lower:
        return "Inbox"
    return "Other"


def build_thread_id(msg: email.message.Message) -> str:
    refs = msg.get("References", "")
    if refs.strip():
        return refs.split()[0].strip("<>")
    in_reply_to = msg.get("In-Reply-To", "")
    if in_reply_to.strip():
        return in_reply_to.strip().strip("<>")
    return (msg.get("Message-ID") or "").strip().strip("<>")


def parse_file(path: Path):
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f)

    folder = classify_folder(path)
    if folder == "Other":
        return None

    raw_body = get_body_text(msg)
    body_text = strip_quotes_and_signature(raw_body)

    return {
        "message_id": (msg.get("Message-ID") or "").strip().strip("<>") or str(path),
        "thread_id": build_thread_id(msg),
        "folder": folder,
        "date": parse_date(msg),
        "from": parseaddr(msg.get("From", ""))[1] or msg.get("From", ""),
        "to": addr_list(msg, "To"),
        "cc": addr_list(msg, "Cc"),
        "subject": msg.get("Subject", "").strip(),
        "body_text": body_text,
        "source_path": str(path),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dir", type=Path, help="readpst .eml export directory")
    ap.add_argument("--out", type=Path, default=Path("data/messages.jsonl"))
    args = ap.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"error: {args.input_dir} is not a directory")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    eml_files = [
        p
        for p in args.input_dir.rglob("*.eml")
        if RELEVANT_FOLDER_RE.search(str(p.relative_to(args.input_dir)))
    ]

    written, skipped = 0, 0
    with open(args.out, "w", encoding="utf-8") as out_f:
        for path in sorted(eml_files):
            try:
                record = parse_file(path)
            except Exception as exc:
                print(f"warn: failed to parse {path}: {exc}", file=sys.stderr)
                skipped += 1
                continue
            if record is None:
                skipped += 1
                continue
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    print(f"wrote {written} messages to {args.out} ({skipped} skipped)")


if __name__ == "__main__":
    main()
