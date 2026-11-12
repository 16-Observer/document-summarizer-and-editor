# document-summarizer-and-editor

Point it at a folder of documents: it reads each one, summarizes it, detects
whether it is fiction, suggests (and optionally applies) character edits for
fictional works, and produces a report listing every document's readable
title, file name, and summary.

Supported formats: `.txt`, `.md`, `.pdf`, `.docx`.

## Setup from scratch (Windows)

1. **Install Python** (if `python --version` in a terminal errors):
   download it from <https://www.python.org/downloads/> and, during install,
   tick **"Add Python to PATH"**. `pip` comes with it.

2. **Get this repository onto your machine** — either:

   ```powershell
   git clone https://github.com/16-Observer/document-summarizer-and-editor.git
   cd document-summarizer-and-editor
   ```

   or, without Git: on the repo's GitHub page click **Code → Download ZIP**,
   extract it, and open a terminal in the extracted folder.

3. **Install the dependencies** (one time only):

   ```powershell
   pip install -r requirements.txt
   ```

4. **Set your Anthropic API key** (create one at
   <https://console.anthropic.com/> under API Keys). In PowerShell:

   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-...your key..."
   ```

   or in classic cmd: `set ANTHROPIC_API_KEY=sk-ant-...`. This lasts until
   the terminal window closes; to make it permanent, add it under
   Windows Settings → System → About → Advanced system settings →
   Environment Variables.

5. **Run it** (see Usage below), e.g.:

   ```powershell
   python summarize.py "C:\Users\you\Documents\my-docs"
   ```

> **Note:** every supported document in the folder (subfolders included) is
> sent to the Claude API, which costs real API usage. Try a small test
> folder before pointing it at something large like Downloads.

## Setup (macOS / Linux)

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
