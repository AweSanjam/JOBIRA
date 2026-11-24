#!/usr/bin/env python3
"""Convert a Markdown file to a styled PDF using a small built-in Markdown->HTML
converter + LibreOffice headless (--convert-to pdf). No external Python deps.

Usage: python3 md2pdf.py input.md output.pdf
"""
import html
import re
import subprocess
import sys
import tempfile
import os


def md_to_html_body(md_text):
    lines = md_text.replace("\r\n", "\n").split("\n")
    html_lines = []
    in_ul = False
    in_ol = False
    para_buf = []

    def flush_para():
        if para_buf:
            html_lines.append("<p>" + inline(" ".join(para_buf)) + "</p>")
            para_buf.clear()

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

    def inline(text):
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
        text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
        text = re.sub(r"(?<!_)_(.+?)_(?!_)", r"<i>\1</i>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
        return text

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_para()
            close_lists()
            continue

        if re.match(r"^-{3,}$|^\*{3,}$", stripped):
            flush_para()
            close_lists()
            html_lines.append("<hr/>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            close_lists()
            level = len(m.group(1))
            html_lines.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue

        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            flush_para()
            if not in_ul:
                close_lists()
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{inline(m.group(1))}</li>")
            continue

        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            flush_para()
            if not in_ol:
                close_lists()
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{inline(m.group(1))}</li>")
            continue

        close_lists()
        para_buf.append(stripped)

    flush_para()
    close_lists()
    return "\n".join(html_lines)


PAGE_CSS = """
@page { size: Letter; margin: 0.45in; }
body { font-family: 'Liberation Sans', Arial, sans-serif; font-size: 10.3pt;
       color: #1a1a1a; line-height: 1.15; }
h1 { font-size: 22pt; margin: 0 0 3pt 0; border-bottom: 1.5pt solid #333; padding-bottom: 3pt; }
h2 { font-size: 12pt; margin: 7pt 0 2pt 0; color: #222; border-bottom: 0.75pt solid #999; padding-bottom: 2pt; }
h3 { font-size: 11pt; margin: 6pt 0 1pt 0; }
p { margin: 1.5pt 0; }
ul, ol { margin: 1.5pt 0 1.5pt 15pt; padding: 0; }
li { margin: 0.5pt 0; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 5pt 0; }
a { color: #1a1a1a; text-decoration: none; }
"""


# Resume v2 (2026-10-20): slightly tighter spacing so a v2 resume fits on one page.
RESUME_CSS = (PAGE_CSS.replace("line-height: 1.15;", "line-height: 1.1;")
              .replace("h2 { font-size: 12pt; margin: 7pt 0 2pt 0;", "h2 { font-size: 11.5pt; margin: 5pt 0 1.5pt 0;")
              .replace("li { margin: 0.5pt 0; }", "li { margin: 0; }"))


def convert(md_path, pdf_path, css=None):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    body = md_to_html_body(md_text)
    doc = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css or PAGE_CSS}</style></head><body>{body}</body></html>"

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "doc.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(doc)

        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, html_path],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError(f"soffice failed: {result.stdout}\n{result.stderr}")

        produced = os.path.join(tmpdir, "doc.pdf")
        if not os.path.exists(produced):
            raise RuntimeError(f"soffice did not produce a PDF: {result.stdout}\n{result.stderr}")

        os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
        with open(produced, "rb") as src, open(pdf_path, "wb") as dst:
            dst.write(src.read())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: md2pdf.py input.md output.pdf", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
    print(f"Wrote {sys.argv[2]}")



def convert_docx(md_path, docx_path):
    """Markdown -> .docx (Word) via the same HTML + LibreOffice route. Used for cover letters
    since 2026-10-12 (naming: cover_letters/[Company]_[JobTitle]_cover.docx)."""
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    body = md_to_html_body(md_text)
    doc = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{PAGE_CSS}</style></head><body>{body}</body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "doc.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(doc)
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "docx:MS Word 2007 XML", "--outdir", tmpdir, html_path],
            capture_output=True, text=True, timeout=90,
        )
        produced = os.path.join(tmpdir, "doc.docx")
        if result.returncode != 0 or not os.path.exists(produced):
            raise RuntimeError(f"soffice docx failed: {result.stdout}\n{result.stderr}")
        os.makedirs(os.path.dirname(docx_path) or ".", exist_ok=True)
        with open(produced, "rb") as src, open(docx_path, "wb") as dst:
            dst.write(src.read())
