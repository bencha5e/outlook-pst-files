"""
Shared body-text cleaning helpers used by both extraction paths
(parse_emails.py for a readpst .eml export, extract_from_outlook.py for
direct Outlook COM automation).
"""
import re

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


def strip_quotes_and_signature(body: str) -> str:
    lines = body.splitlines()
    cut = len(lines)
    for i, line in enumerate(lines):
        if QUOTE_MARKERS.match(line) or SIGNATURE_MARKER.match(line):
            cut = i
            break
    trimmed = "\n".join(lines[:cut]).strip()
    return trimmed if trimmed else body.strip()
