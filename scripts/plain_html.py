#!/usr/bin/env python3
"""Offline, zero-dependency HTML companion for published plain-language Markdown.

Presentation follows the public Gen UI principles: readable hierarchy, responsive
layouts, accessible text, and faithful evidence states. This does NOT execute the
Gen UI Skill, a Mermaid renderer, or untrusted Markdown HTML/JavaScript.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
from pathlib import Path
from urllib.parse import urlsplit

CSS = """
:root{color-scheme:light;--ink:#17263a;--muted:#50667a;--accent:#2563eb;--line:#dce6f1;--surface:#f5f8fc}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#fff;color:var(--ink);font:16px/1.75 system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}
main{max-width:900px;margin:0 auto;padding:42px 26px 90px}.eyebrow{color:var(--muted);font-size:.83rem;letter-spacing:.06em}
h1,h2,h3{line-height:1.4;overflow-wrap:anywhere}h1{font-size:clamp(1.75rem,4vw,2.65rem);margin:.6rem 0 1.4rem}
h2{font-size:1.35rem;border-top:1px solid var(--line);padding-top:1.55rem;margin-top:2.2rem}h3{font-size:1.08rem;margin-top:1.4rem}
p,li{overflow-wrap:anywhere}p{margin:.65rem 0 1.1rem}ul,ol{padding-left:1.5rem}li{margin:.3rem 0}
a{color:#1651a5;text-decoration-thickness:1px;text-underline-offset:3px}a:focus-visible{outline:3px solid #f59e0b;outline-offset:2px}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#f1f5fa;border-radius:4px;padding:.08em .3em;font-size:.92em}
pre{overflow-x:auto;padding:17px;border-radius:9px;background:#142238;color:#f3f6fd;font-size:.9rem;line-height:1.55}pre code{padding:0;background:transparent;color:inherit}
.table-wrap{width:100%;overflow-x:auto;margin:1.3rem 0;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;min-width:460px;font-size:.94rem}td,th{padding:.65rem .85rem;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--surface)}tr:last-child td{border-bottom:0}
blockquote{margin:1.3rem 0;border-left:4px solid var(--accent);padding:.45rem 1rem;background:var(--surface);color:#30485e}
.diagram{border:1px solid var(--line);border-radius:9px;padding:1rem;background:var(--surface)}.diagram pre{margin:.6rem 0}.diagram figcaption{color:var(--muted);font-size:.86rem}
hr{border:0;border-top:1px solid var(--line);margin:2rem 0}.footnote{color:var(--muted);font-size:.87rem;border-top:1px solid var(--line);margin-top:3rem;padding-top:1rem}
@media(max-width:560px){main{padding:22px 16px 56px}table{font-size:.87rem}h2{margin-top:1.7rem}}
@media print{main{max-width:none;padding:0}body{font-size:11pt}pre,.table-wrap{break-inside:avoid}a{color:inherit}}
""".strip()

CODE_FENCE = re.compile(r'^\s*(`{3,}|~{3,})([a-zA-Z0-9_-]*)\s*$')
HEAD = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
LIST = re.compile(r'^\s*([-*+]\s+|\d+\.\s+)(.+)$')
LINK = re.compile(r'\[([^\]\n]+)\]\(([^)\s]+)\)')


def _safe_href(href: str) -> str | None:
    if any(ord(ch) < 32 for ch in href):
        return None
    uri = html.unescape(href).strip()
    parts = urlsplit(uri)
    if parts.scheme and parts.scheme not in ('https', 'http', 'mailto'):
        return None
    if uri.startswith('//') or uri.startswith('\\'):
        return None
    if not parts.scheme and uri.startswith('/'):
        return None
    return html.escape(uri, quote=True)


def inline(text: str) -> str:
    """Escape all raw HTML; apply only known safe inline Markdown affordances."""
    fragments: list[str] = []

    def protect(value: str) -> str:
        fragments.append(value)
        return f'ZXQTOKEN{len(fragments)-1}QXZ'

    text = re.sub(r'`([^`\n]+)`', lambda m: protect('<code>'+html.escape(m.group(1))+'</code>'), text)
    def link_sub(m: re.Match) -> str:
        href = _safe_href(m.group(2))
        if href is None:
            return html.escape(m.group(0))
        return protect('<a href="'+href+'" rel="noopener noreferrer">'+html.escape(m.group(1))+'</a>')
    text = LINK.sub(link_sub, text)
    safe = html.escape(text)
    safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
    safe = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', safe)
    for index in reversed(range(len(fragments))):
        safe = safe.replace(f'ZXQTOKEN{index}QXZ', fragments[index])
    return safe


def _table_start(lines: list[str], i: int) -> bool:
    if i+1 >= len(lines) or '|' not in lines[i] or '|' not in lines[i+1]:
        return False
    cols = [col.strip() for col in lines[i+1].strip().strip('|').split('|')]
    return bool(cols) and all(re.fullmatch(r':?-{3,}:?', col) for col in cols)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip('|').split('|')]


def markdown_body(markdown: str) -> str:
    lines = markdown.replace('\r\n', '\n').split('\n')
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = CODE_FENCE.match(line)
        if fence:
            delimiter, lang = fence.groups()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(delimiter):
                code.append(lines[i]); i += 1
            if i < len(lines): i += 1
            body = '<pre><code>'+html.escape('\n'.join(code))+'</code></pre>'
            if lang.lower() == 'mermaid':
                out.append('<figure class="diagram"><figcaption>流程图结构（离线文本表示；具体含义以正文说明为准）</figcaption>'+body+'</figure>')
            else:
                out.append(body)
            continue
        if _table_start(lines, i):
            headers = _cells(line); i += 2
            out.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+inline(c)+'</th>' for c in headers) + '</tr></thead><tbody>')
            while i < len(lines) and lines[i].strip() and '|' in lines[i]:
                cells = _cells(lines[i]); out.append('<tr>'+''.join('<td>'+inline(cells[j] if j < len(cells) else '')+'</td>' for j in range(len(headers)))+'</tr>'); i+=1
            out.append('</tbody></table></div>')
            continue
        h = HEAD.match(line)
        if h:
            level=len(h.group(1));out.append(f'<h{level}>'+inline(h.group(2))+f'</h{level}>');i+=1;continue
        if re.fullmatch(r'\s*(?:-{3,}|\*{3,}|_{3,})\s*', line):
            out.append('<hr>');i+=1;continue
        if line.startswith('> '):
            quoted=[]
            while i < len(lines) and lines[i].startswith('> '):
                quoted.append(lines[i][2:]);i+=1
            out.append('<blockquote><p>'+inline(' '.join(quoted))+'</p></blockquote>');continue
        li=LIST.match(line)
        if li:
            ordered=li.group(1).strip()[0].isdigit();tag='ol' if ordered else 'ul';rows=[]
            while i<len(lines) and (m:=LIST.match(lines[i])) and m.group(1).strip()[0].isdigit()==ordered:
                rows.append('<li>'+inline(m.group(2))+'</li>');i+=1
            out.append('<'+tag+'>'+''.join(rows)+'</'+tag+'>');continue
        paragraph=[line.strip()];i+=1
        while i < len(lines) and lines[i].strip() and not (HEAD.match(lines[i]) or CODE_FENCE.match(lines[i]) or LIST.match(lines[i]) or lines[i].startswith('> ') or _table_start(lines,i)):
            paragraph.append(lines[i].strip());i+=1
        out.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(out)


def render(markdown: str, title: str = '大白话解释') -> bytes:
    """Deterministic stand-alone HTML; no external requests, JS or raw HTML execution."""
    raw = markdown.encode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    lang = 'zh-CN' if re.search(r'[\u4e00-\u9fff]', markdown) else 'en'
    title = html.escape(title, quote=True)
    document = ('<!DOCTYPE html>\n<html lang="'+lang+'"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<meta name="plan-ship-source-sha256" content="'+sha+'">'
      '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src data:; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
      '<title>'+title+' · PlanShip</title><style>'+CSS+'</style></head><body>'
      '<main><div class="eyebrow">PlanShip · 大白话解释 / Plain-language guide</div>'
      + markdown_body(markdown)
      + '<footer class="footnote">本页与同名 Markdown 配对发布。测试与验收状态以文档中的真实记录为准；本页不执行代码或联网请求。</footer></main></body></html>\n')
    return document.encode('utf-8')


def main() -> int:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--markdown', type=Path, required=True)
    cli.add_argument('--html', type=Path, required=True)
    args=cli.parse_args()
    args.html.write_bytes(render(args.markdown.read_text(encoding='utf-8-sig'),args.markdown.stem))
    print('GENERATED:', args.html)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
