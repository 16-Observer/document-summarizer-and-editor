# document-summarizer-and-editor

Point it at a folder of documents: it reads each one, summarizes it, detects
whether it is fiction, suggests (and optionally applies) character edits for
fictional works, and produces a report listing every document's readable
title, file name, and summary.

Supported formats: `.txt`, `.md`, `.pdf`, `.docx`.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# Summarize everything in a folder; report lands in <folder>/report/
python summarize.py path/to/documents

# Also write edited copies of fictional documents (originals untouched)
python summarize.py path/to/documents --apply-edits

# Choose where the report goes
python summarize.py path/to/documents --out ./my-report
```

Output:

- `report.html` — one card per document: readable title (invented when the
  document has none), file name, summary, fiction/non-fiction, characters,
  and suggested character edits.
- `report.json` — the same data, machine-readable.
- `edited/` — revised copies of fictional documents when `--apply-edits`
  is passed. Originals are never modified.
