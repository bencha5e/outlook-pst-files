#!/usr/bin/env python3
"""
Extract Inbox/Sent Items messages directly from a PST via Outlook's COM
interface (Windows only) and write them to data/messages.jsonl in the same
schema parse_emails.py produces. This is the Windows-without-admin-rights
alternative to readpst: it uses Outlook, which is already installed, instead
of a separate extraction tool.

Prerequisites:
    1. In Outlook: File > Open & Export > Open Outlook Data File, and pick
       your .pst file. It will appear as a top-level entry in the Outlook
       folder pane - note its exact display name (usually the file name
       without ".pst", or a mailbox name if the PST was originally an
       archived mailbox).
    2. pip install --user pywin32
    3. Outlook must be running (or this script will launch it).

Usage:
    python scripts/extract_from_outlook.py "<PST display name in Outlook>" [--out data/messages.jsonl]

Run with --list-stores first if you're not sure of the exact display name:
    python scripts/extract_from_outlook.py --list-stores
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from email_cleaning import strip_html, strip_quotes_and_signature  # noqa: E402

try:
    import win32com.client
except ImportError:
    sys.exit("error: pip install --user pywin32")

# olMailItem = 43 (only care about actual mail, not meeting requests etc.
# that live in Inbox/Sent Items too).
OL_MAIL_ITEM = 43

TARGET_FOLDER_NAMES = {"inbox", "sent items"}


def get_outlook_namespace():
    outlook = win32com.client.Dispatch("Outlook.Application")
    return outlook.GetNamespace("MAPI")


def list_stores(namespace):
    for folder in namespace.Folders:
        print(folder.Name)


def find_store_root(namespace, store_name: str):
    for folder in namespace.Folders:
        if folder.Name.strip().lower() == store_name.strip().lower():
            return folder
    available = ", ".join(f.Name for f in namespace.Folders)
    sys.exit(
        f"error: no store named {store_name!r} found in Outlook.\n"
        f"Available: {available}\n"
        f"Make sure the PST is opened via File > Open & Export > Open Outlook Data File."
    )


def find_target_folders(store_root):
    """Depth-first search for folders named Inbox / Sent Items anywhere under
    the store root, since PSTs opened as data files sometimes nest them."""
    found = []
    stack = [store_root]
    while stack:
        folder = stack.pop()
        if folder.Name.strip().lower() in TARGET_FOLDER_NAMES:
            found.append(folder)
        for sub in folder.Folders:
            stack.append(sub)
    return found


def folder_label(name: str) -> str:
    return "Sent" if name.strip().lower() == "sent items" else "Inbox"


def smtp_address(mail_item, prop_name: str) -> str:
    """Best-effort resolution of an SMTP address; Exchange items often expose
    only a legacyExchangeDN via *_EmailAddress properties."""
    try:
        addr = getattr(mail_item, prop_name, "") or ""
    except Exception:
        addr = ""
    if addr and "@" in addr:
        return addr
    try:
        sender = mail_item.Sender
        if sender is not None:
            exch_user = sender.GetExchangeUser()
            if exch_user is not None and exch_user.PrimarySmtpAddress:
                return exch_user.PrimarySmtpAddress
    except Exception:
        pass
    return addr


def recipients_by_type(mail_item, type_value: int):
    addrs = []
    try:
        for r in mail_item.Recipients:
            if r.Type == type_value:
                try:
                    exch_user = r.AddressEntry.GetExchangeUser()
                    addr = exch_user.PrimarySmtpAddress if exch_user else r.Address
                except Exception:
                    addr = r.Address
                addrs.append(addr or r.Name)
    except Exception:
        pass
    return addrs


def extract_item(mail_item, folder_label_str: str, source_label: str):
    try:
        if mail_item.Class != 43:  # olMail
            return None
    except Exception:
        pass

    date = mail_item.SentOn if folder_label_str == "Sent" else mail_item.ReceivedTime
    date_str = date.isoformat() if date else None

    raw_body = mail_item.Body or ""
    body_text = strip_quotes_and_signature(raw_body)

    entry_id = mail_item.EntryID
    conversation_id = mail_item.ConversationID or entry_id

    return {
        "message_id": entry_id,
        "thread_id": conversation_id,
        "folder": folder_label_str,
        "date": date_str,
        "from": smtp_address(mail_item, "SenderEmailAddress"),
        "to": recipients_by_type(mail_item, 1),  # olTo
        "cc": recipients_by_type(mail_item, 2),  # olCC
        "subject": (mail_item.Subject or "").strip(),
        "body_text": body_text,
        "source_path": f"outlook:{source_label}/{entry_id}",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("store_name", nargs="?", help="Exact display name of the PST in Outlook's folder pane")
    ap.add_argument("--out", type=Path, default=Path("data/messages.jsonl"))
    ap.add_argument("--list-stores", action="store_true", help="List available top-level stores and exit")
    args = ap.parse_args()

    namespace = get_outlook_namespace()

    if args.list_stores:
        list_stores(namespace)
        return

    if not args.store_name:
        sys.exit("error: provide the PST's store name, or run with --list-stores to see options")

    store_root = find_store_root(namespace, args.store_name)
    target_folders = find_target_folders(store_root)
    if not target_folders:
        sys.exit(f"error: no Inbox or Sent Items folder found under {args.store_name!r}")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    written, skipped = 0, 0
    with open(args.out, "w", encoding="utf-8") as out_f:
        for folder in target_folders:
            label = folder_label(folder.Name)
            items = folder.Items
            count = items.Count
            for i in range(1, count + 1):
                try:
                    item = items.Item(i)
                    record = extract_item(item, label, folder.Name)
                except Exception as exc:
                    print(f"warn: failed to read item {i} in {folder.Name}: {exc}", file=sys.stderr)
                    skipped += 1
                    continue
                if record is None:
                    skipped += 1
                    continue
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
                if written % 200 == 0:
                    print(f"...{written} messages written so far", file=sys.stderr)

    print(f"wrote {written} messages to {args.out} ({skipped} skipped)")


if __name__ == "__main__":
    main()
