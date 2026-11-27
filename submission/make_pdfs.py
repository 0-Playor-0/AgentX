"""Export ABSTRACT.md and ARCHITECTURE.md to PDF (A4) in submission/.

    python submission/make_pdfs.py

A small Markdown subset (headings, paragraphs, bullet and numbered lists, code blocks, bold, code,
links) is converted to HTML here, then printed with Playwright's Chromium (Node). Prints each page count.
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [("ABSTRACT.md", "ABSTRACT.pdf", 10.5), ("ARCHITECTURE.md", "ARCHITECTURE.pdf", 10)]
CSS = """@page{size:A4;margin:13mm 15mm}
body{font-family:"DejaVu Sans","Helvetica Neue",Arial,sans-serif;font-size:%spt;line-height:1.38;color:#111}
h1{font-size:1.65em;margin:0 0 .35em}h2{font-size:1.15em;margin:.85em 0 .3em}
p{margin:.35em 0}ul,ol{margin:.25em 0 .35em;padding-left:1.4em}li{margin:.1em 0}
code{font-family:"DejaVu Sans Mono",Menlo,monospace;font-size:.92em;background:#f2f2f2;padding:0 .2em;border-radius:2px}
pre{font-family:"DejaVu Sans Mono",Menlo,monospace;font-size:.85em;line-height:1.15;background:#f6f6f6;
padding:.5em .7em;border-radius:4px;margin:.4em 0;white-space:pre;overflow:hidden}
a{color:#0b57d0;text-decoration:none}"""


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])_([^_]+)_(?![\w*])", r"<i>\1</i>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)


def convert(md):
    out, lines, i = [], md.splitlines(), 0
    stack = []                                   # [(indent, tag)]

    def close(to=-1):
        while stack and stack[-1][0] > to:
            out.append(f"</li></{stack.pop()[1]}>")

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            close(); j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>"); i = j + 1; continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            close(); n = len(m[1]); out.append(f"<h{n}>{inline(m[2])}</h{n}>"); i += 1; continue
        m = re.match(r"^(\s*)([-*]|\d+\.) (.*)", ln)
        if m:
            ind, tag = len(m[1]), "ul" if m[2] in "-*" else "ol"
            if stack and stack[-1][0] == ind:
                out.append("</li><li>")
            elif stack and stack[-1][0] > ind:
                close(ind); out.append("</li><li>")
            else:
                out.append(f"<{tag}><li>"); stack.append((ind, tag))
            text = m[3]; i += 1
            while i < len(lines) and lines[i].strip() and re.match(r"^\s+\S", lines[i]) and \
                    not re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                text += " " + lines[i].strip(); i += 1
            out.append(inline(text)); continue
        if not ln.strip():
            if not (i + 1 < len(lines) and re.match(r"^\s+([-*]|\d+\.) ", lines[i + 1] or "")):
                close()
            i += 1; continue
        close(); para = [ln.strip()]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|```|\s*([-*]|\d+\.) )", lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    close()
    return "\n".join(out)


JS = """const {chromium}=require('playwright');(async()=>{const jobs=JSON.parse(process.argv[2]);
const b=await chromium.launch();const p=await b.newPage();
for(const [h,out] of jobs){await p.goto('file://'+h);await p.pdf({path:out,format:'A4',printBackground:true,preferCSSPageSize:true});}
await b.close();})();"""


def main():
    jobs, tmp = [], Path(tempfile.mkdtemp())
    for src, dst, size in DOCS:
        md = (ROOT / src).read_text(encoding="utf-8")
        title = re.search(r"^# (.*)", md, re.M)[1]
        page = (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
                f"<style>{CSS % size}</style></head><body>{convert(md)}</body></html>")
        h = tmp / (Path(src).stem + ".html"); h.write_text(page, encoding="utf-8")
        jobs.append([str(h), str(ROOT / "submission" / dst)])
    js = tmp / "print.js"; js.write_text(JS)
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["node", str(js), json.dumps(jobs)], check=True, env=dict(os.environ, NODE_PATH=npm_root))
    for _, out in jobs:
        pages = len(re.findall(rb"/Type\s*/Page[^s]", Path(out).read_bytes()))
        print(f"{Path(out).relative_to(ROOT)}: {pages} page(s)")


if __name__ == "__main__":
    main()
