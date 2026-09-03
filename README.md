# outlook-pst-files

Pipeline for mining Outlook Inbox/Sent Items PST exports for emails that carry
"meaningful context" - decisions, borrower declines/approvals, recommendations
to IRE/INCREF, significant good/bad news to IRE, covenant/DY issues, and
modification/waiver calls. The flagged output is meant to seed a Claude skill
trained on your writing style for future borrower/IRE communications.

Everything runs **locally**, where your PST files live. Raw and classified
mail content is never committed to this repo (`data/` is gitignored) and
should never be uploaded to a hosted Claude session, since it contains
borrower and loan-level financial detail.

## Pipeline

### 1. Extract the PST

Install `readpst` (from `libpst`):

```
apt install pst-utils      # Debian/Ubuntu
brew install libpst        # macOS
```

Export each PST to per-message `.eml` files:

```
readpst -e -o pst_export/ path/to/mailbox.pst
```

This produces a directory tree like `pst_export/Inbox/*.eml` and
`pst_export/Sent Items/*.eml`.

### 2. Parse into structured records

```
python3 scripts/parse_emails.py pst_export/ --out data/messages.jsonl
```

Walks the export, keeps only `Inbox`/`Sent` folders, strips quoted reply
chains and signature blocks, and writes one JSON record per message
(`message_id`, `folder`, `date`, `from`, `to`, `cc`, `subject`, `body_text`,
`thread_id`, `source_path`) to `data/messages.jsonl`.

### 3. Classify against the taxonomy

```
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python3 scripts/classify_emails.py --in data/messages.jsonl --out data/classified.jsonl
```

Calls the Claude API once per non-noise message (calendar invites,
auto-replies, and out-of-office notices are filtered out by subject regex
without a model call) and tags each with a category from
[`scripts/taxonomy.md`](scripts/taxonomy.md), a confidence level, a one-line
rationale, and a supporting excerpt. This step sends email content
(borrower/loan detail) to the Anthropic API - review `taxonomy.md` and the
script before running against a full mailbox, and use `--limit N` to test on
a small batch first. The script is resumable: re-running it skips
`message_id`s already present in the output file.

### 4. Curate the flagged set

```
python3 scripts/summarize_flagged.py --in data/classified.jsonl --out data/flagged_report.md
```

Produces a Markdown report of every flagged (non-`none`) message, grouped by
category and sorted by date, for you to scan and hand-pick the strongest
~15-30 examples across categories.

### 5. Build the writing-style skill

Once you've picked representative examples, use the `skill-creator` skill to
turn them into a house-style skill for drafting borrower/IRE emails -
capturing tone, structure, and how you frame good vs. bad news.

## Repo layout

```
scripts/
  parse_emails.py       # PST .eml export -> data/messages.jsonl
  classify_emails.py    # data/messages.jsonl -> data/classified.jsonl
  summarize_flagged.py  # data/classified.jsonl -> data/flagged_report.md
  taxonomy.md           # classification categories (source of truth)
data/                    # gitignored - all extracted/classified mail content
```
