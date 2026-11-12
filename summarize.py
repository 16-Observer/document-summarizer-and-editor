#!/usr/bin/env python3
"""Document summarizer and editor.

Point it at a folder: it reads each document (.txt, .md, .pdf, .docx),
summarizes it, detects whether it is fiction, proposes character edits for
fictional works, and writes an HTML + JSON report listing every document's
readable title, file name, and summary.

Usage:
    python summarize.py <folder> [--out <report-folder>] [--apply-edits]
                        [--model <model-id>]

Requires an Anthropic API key (ANTHROPIC_API_KEY, or any credential source
the SDK resolves).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}
MAX_DOC_CHARS = 350_000  # ~87K tokens; larger docs are refused, not silently cut

ANALYSIS_SYSTEM = """\
You are a careful literary and document analyst. You will be given the full
text of one document. Respond with a single JSON object, no markdown fences,
with exactly these keys:

- "title": the document's own title if it has a readable English one;
  otherwise invent a short, descriptive, readable title for it.
- "title_invented": true if you invented the title, false if it came from
  the document.
- "summary": a faithful 2-4 sentence summary of what the document is.
- "is_fiction": true if the document is a work of fiction (story, novel
  excerpt, screenplay, etc.), false otherwise.
- "characters": for fiction, a list of the named characters; [] otherwise.
- "character_edits": for fiction, a list of objects, one per suggested
  character improvement, each with "character", "issue" (what is weak,
  inconsistent, or flat about them), and "suggestion" (a concrete edit);
  [] for non-fiction or when the characters need no work.
"""

EDIT_SYSTEM = """\
You are a skilled fiction editor. You will be given the full text of a work
of fiction and a list of character edits to apply. Rewrite the document
applying those edits while preserving the author's voice, plot, and
everything not covered by an edit. Respond with only the full revised
document text - no preamble, no commentary, no markdown fences.
"""


def read_document(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError(f"Unsupported file type: {ext}")


def response_text(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def call_claude(client: anthropic.Anthropic, model: str, system: str, user: str):
    """One streamed request with server-side refusal fallback enabled."""
    with client.beta.messages.stream(
        model=model,
        max_tokens=64000,
        system=system,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        explanation = getattr(details, "explanation", "") or "no explanation given"
        raise RuntimeError(f"Model declined the request: {explanation}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response was truncated at the output-token limit.")
    return response


def parse_analysis(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model response: {raw[:200]!r}")
    data = json.loads(text[start : end + 1])
    for key in ("title", "summary", "is_fiction"):
        if key not in data:
            raise ValueError(f"Model response missing {key!r}")
    data.setdefault("title_invented", False)
    data.setdefault("characters", [])
    data.setdefault("character_edits", [])
    return data


def analyze_document(client, model: str, path: Path, text: str) -> dict:
    user = (
        f"File name: {path.name}\n\nDocument text:\n\n{text}"
    )
    response = call_claude(client, model, ANALYSIS_SYSTEM, user)
    return parse_analysis(response_text(response))


def edit_document(client, model: str, text: str, edits: list) -> str:
    user = (
        "Character edits to apply:\n"
        + json.dumps(edits, indent=2)
        + "\n\nDocument text:\n\n"
        + text
    )
    response = call_claude(client, model, EDIT_SYSTEM, user)
    return response_text(response).strip() + "\n"


def build_html_report(results: list, generated_at: str) -> str:
    cards = []
    for item in results:
        if item.get("error"):
            cards.append(
                f"""
      <article class="card error">
        <h2>{html.escape(item['file'])}</h2>
        <p class="meta">Could not process</p>
        <p>{html.escape(item['error'])}</p>
      </article>"""
            )
            continue
        badge = "Fiction" if item["is_fiction"] else "Non-fiction"
        title_note = " (title invented)" if item["title_invented"] else ""
        characters = ", ".join(item["characters"]) if item["characters"] else ""
        edits_html = ""
        if item["character_edits"]:
            rows = "".join(
                f"<li><strong>{html.escape(e.get('character', '?'))}</strong>: "
                f"{html.escape(e.get('issue', ''))} &mdash; "
                f"<em>{html.escape(e.get('suggestion', ''))}</em></li>"
                for e in item["character_edits"]
            )
            applied = (
                f'<p class="meta">Edited copy: {html.escape(item["edited_file"])}</p>'
                if item.get("edited_file")
                else ""
            )
            edits_html = f"<h3>Suggested character edits</h3><ul>{rows}</ul>{applied}"
        chars_html = (
            f'<p class="meta">Characters: {html.escape(characters)}</p>'
            if characters
            else ""
        )
        cards.append(
            f"""
      <article class="card">
        <h2>{html.escape(item['title'])}{title_note}</h2>
        <p class="meta"><span class="badge">{badge}</span> &middot; {html.escape(item['file'])}</p>
        <p>{html.escape(item['summary'])}</p>
        {chars_html}
        {edits_html}
      </article>"""
        )
    body = "\n".join(cards) or "<p>No supported documents found.</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Document Report</title>
<style>
  :root {{
    --bg: #f6f5f1; --card: #ffffff; --ink: #1f2430; --muted: #6b7280;
    --accent: #3d5a80; --border: #e3e1da;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #15171c; --card: #1e2128; --ink: #e8e8e4; --muted: #9aa0ab;
      --accent: #8fb3d9; --border: #2c3038;
    }}
  }}
  body {{
    margin: 0; padding: 32px 16px; background: var(--bg); color: var(--ink);
    font: 16px/1.6 Georgia, "Times New Roman", serif;
  }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px 24px; margin: 16px 0;
  }}
  .card h2 {{ margin: 0 0 4px; font-size: 1.15rem; color: var(--accent); }}
  .meta {{ color: var(--muted); font-size: 0.85rem; }}
  .badge {{
    border: 1px solid var(--border); border-radius: 999px;
    padding: 1px 10px; font-size: 0.75rem;
  }}
  .error h2 {{ color: #b4524b; }}
</style>
</head>
<body>
<main>
  <h1>Document Report</h1>
  <p class="meta">Generated {html.escape(generated_at)} &middot; {len(results)} document(s)</p>
  {body}
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=Path, help="Folder of documents to process")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Where to write report.html / report.json (default: <folder>/report)",
    )
    parser.add_argument(
        "--apply-edits", action="store_true",
        help="For fictional documents, write an edited copy applying the "
             "suggested character edits (originals are never touched)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model id")
    args = parser.parse_args()

    folder: Path = args.folder
    if not folder.is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        return 2
    out_dir: Path = args.out or (folder / "report")
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in folder.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and out_dir not in p.parents
    )
    if not files:
        print(f"No supported documents found in {folder}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()
    results = []
    for path in files:
        rel = str(path.relative_to(folder))
        print(f"-> {rel}")
        try:
            text = read_document(path)
            if not text.strip():
                raise ValueError("Document is empty or no text could be extracted")
            if len(text) > MAX_DOC_CHARS:
                raise ValueError(
                    f"Document is too large ({len(text)} chars > {MAX_DOC_CHARS})"
                )
            analysis = analyze_document(client, args.model, path, text)
            item = {"file": rel, **analysis, "edited_file": None}
            if args.apply_edits and analysis["is_fiction"] and analysis["character_edits"]:
                print(f"   applying {len(analysis['character_edits'])} character edit(s)")
                revised = edit_document(client, args.model, text, analysis["character_edits"])
                edited_path = out_dir / "edited" / (path.stem + ".edited.txt")
                edited_path.parent.mkdir(parents=True, exist_ok=True)
                edited_path.write_text(revised, encoding="utf-8")
                item["edited_file"] = str(edited_path.relative_to(out_dir))
            results.append(item)
        except Exception as exc:  # keep going; the report records the failure
            print(f"   failed: {exc}", file=sys.stderr)
            results.append({"file": rel, "error": str(exc)})

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (out_dir / "report.json").write_text(
        json.dumps({"generated_at": generated_at, "documents": results}, indent=2),
        encoding="utf-8",
    )
    (out_dir / "report.html").write_text(
        build_html_report(results, generated_at), encoding="utf-8"
    )
    ok = sum(1 for r in results if not r.get("error"))
    print(f"\nDone: {ok}/{len(results)} documents processed.")
    print(f"Report: {out_dir / 'report.html'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
