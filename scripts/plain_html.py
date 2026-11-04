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
from urllib.parse import urlsplit, unquote, quote
from pathlib import PurePosixPath
import json

CSS = """
:root{color-scheme:light;--ink:#17263a;--muted:#50667a;--accent:#2563eb;--line:#dce6f1;--surface:#f5f8fc}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#fff;color:var(--ink);font:16px/1.75 system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}
main{max-width:960px;margin:0 auto;padding:42px 26px 90px}.eyebrow{color:var(--muted);font-size:.83rem;letter-spacing:.06em}
h1,h2,h3{line-height:1.4;overflow-wrap:anywhere}h1{font-size:clamp(1.75rem,4vw,2.65rem);margin:.6rem 0 1.4rem}
h2{font-size:1.35rem;border-top:1px solid var(--line);padding-top:1.55rem;margin-top:2.2rem}h3{font-size:1.08rem;margin-top:1.4rem}
p,li{overflow-wrap:anywhere}p{margin:.65rem 0 1.1rem}ul,ol{padding-left:1.5rem}li{margin:.3rem 0}
a{color:#1651a5;text-decoration-thickness:1px;text-underline-offset:3px}a:focus-visible{outline:3px solid #f59e0b;outline-offset:2px}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#f1f5fa;border-radius:4px;padding:.08em .3em;font-size:.92em}
pre{overflow-x:auto;padding:17px;border-radius:9px;background:#142238;color:#f3f6fd;font-size:.9rem;line-height:1.55}pre code{padding:0;background:transparent;color:inherit}
.table-wrap{width:100%;overflow-x:auto;margin:1.3rem 0;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;min-width:460px;font-size:.94rem}td,th{padding:.65rem .85rem;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--surface)}tr:last-child td{border-bottom:0}
blockquote{margin:1.3rem 0;border-left:4px solid var(--accent);padding:.45rem 1rem;background:var(--surface);color:#30485e}
.diagram{border:1px solid var(--line);border-radius:9px;padding:1rem;background:var(--surface)}.diagram pre{margin:.6rem 0}.diagram figcaption{color:var(--muted);font-size:.86rem}
img{max-width:100%;height:auto;border-radius:8px;border:1px solid var(--line)}.doc-grid{list-style:none;padding:0;display:grid;gap:12px}.doc-grid li{padding:16px;border:1px solid var(--line);border-radius:12px}.doc-sub{font-size:.86rem;color:var(--muted)}.doc-status{font-size:.81rem;color:#2457a6;margin-left:1rem}
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


def _safe_image(src: str) -> str | None:
    """Only local relative image paths or bounded safe image data URLs."""
    if any(ord(c) < 32 for c in src):
        return None
    uri = html.unescape(src).strip()
    if len(uri) > 150_000:
        return None
    if uri.startswith('data:'):
        if re.fullmatch(r'data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+', uri, re.I):
            return html.escape(uri, quote=True)
        return None
    parts = urlsplit(uri)
    if parts.scheme or parts.netloc or uri.startswith(('/', '\\')) or parts.query or parts.fragment:
        return None
    path = unquote(parts.path)
    if not path or '\\' in path or ':' in path or '..' in PurePosixPath(path).parts:
        return None
    return html.escape(uri, quote=True)


# Recognize inline elements only when outside code spans. No text-substitution
# placeholder tokens: a user's literal ZXQTOKEN0QXZ must remain unchanged.
INLINES = re.compile(r'(`+[^`\n]+`+|!\[[^]\n]*\]\([^)\s]+\)|\[[^]\n]+\]\([^)\s]+\)|\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*))')


def inline(text: str) -> str:
    out, pos = [], 0
    for match in INLINES.finditer(text):
        out.append(html.escape(text[pos:match.start()]))
        raw = match.group()
        if raw.startswith('`'):
            ticks = len(raw) - len(raw.lstrip('`'))
            if raw.endswith('`'*ticks):
                out.append('<code>'+html.escape(raw[ticks:-ticks])+'</code>')
            else:
                out.append(html.escape(raw))
        elif raw.startswith('!['):
            alt, src = raw[2:].split('](', 1)
            src = _safe_image(src[:-1])
            out.append('<img src="'+src+'" alt="'+html.escape(alt, quote=True)+'" loading="lazy">' if src else html.escape(raw))
        elif raw.startswith('['):
            label, url = raw[1:].split('](', 1)
            href = _safe_href(url[:-1])
            out.append('<a href="'+href+'" rel="noopener noreferrer">'+html.escape(label)+'</a>' if href else html.escape(raw))
        elif raw.startswith('**'):
            out.append('<strong>'+html.escape(raw[2:-2])+'</strong>')
        elif raw.startswith('*'):
            out.append('<em>'+html.escape(raw[1:-1])+'</em>')
        else:
            out.append(html.escape(raw))
        pos = match.end()
    out.append(html.escape(text[pos:]))
    return ''.join(out)


def _cells(line: str) -> list[str]:
    """Split unescaped pipes outside backtick spans, preserving every column."""
    cells, buf, code_len, i = [], [], 0, 0
    while i < len(line):
        c = line[i]
        if c == '\\' and code_len == 0 and i+1 < len(line) and line[i+1] == '|':
            buf.append('|'); i += 2; continue
        if c == '`':
            j = i
            while j < len(line) and line[j] == '`':
                j += 1
            n = j - i
            if code_len == 0:
                code_len = n
            elif n == code_len:
                code_len = 0
            buf.append(line[i:j]); i=j; continue
        if c == '|' and code_len == 0:
            cells.append(''.join(buf).strip()); buf=[]
        else:
            buf.append(c)
        i += 1
    cells.append(''.join(buf).strip())
    if line.lstrip().startswith('|') and cells and cells[0]=='':
        cells.pop(0)
    if line.rstrip().endswith('|') and cells and cells[-1]=='':
        cells.pop()
    return cells


def _table_start(lines: list[str], i: int) -> bool:
    if i+1 >= len(lines):
        return False
    cells, separators = _cells(lines[i]), _cells(lines[i+1])
    return len(cells) >= 2 and len(cells) == len(separators) and all(re.fullmatch(r':?-{3,}:?', c) for c in separators)


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
                cells = _cells(lines[i]); out.append('<tr>'+''.join('<td>'+inline(cell)+'</td>' for cell in cells)+'</tr>' if len(cells)==len(headers) else '<tr><td colspan="'+str(len(headers))+'">'+inline(lines[i])+'</td></tr>'); i+=1
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
      '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src &#39;self&#39; data: file:; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
      '<title>'+title+' · PlanShip</title><style>'+CSS+'</style></head><body>'
      '<main><nav aria-label="文档导航"><a href="index.html">返回大白话文档主入口</a></nav><div class="eyebrow">PlanShip · 大白话解释 / Plain-language guide</div>'
      + markdown_body(markdown)
      + '<footer class="footnote">本页与同名 Markdown 配对发布。测试与验收状态以文档中的真实记录为准；本页不执行代码或联网请求。</footer></main></body></html>\n')
    return document.encode('utf-8')


def render_index(index: dict, name: str) -> bytes:
    """Deterministic offline navigation generated only from indexed documents."""
    rows = []
    for key, doc in index.get('documents', {}).items():
        if not isinstance(doc, dict) or not isinstance(doc.get('filename'), str):
            continue
        filename = doc['filename']
        if not re.fullmatch(r'[0-9]+\. [^/\\]+\.md', filename):
            continue
        title = html.escape(str(doc.get('title', filename)))
        path = quote(Path(filename).with_suffix('.html').name)
        md_path = quote(filename)
        date = html.escape(str(doc.get('updated_at', '未记录')))
        rows.append((int(doc.get('number', 0)), '<li><strong><a href="'+path+'">'+title+'</a></strong><div class="doc-sub">文档编号：'+str(doc.get('number',''))+' · 更新时间：'+date+' · 状态：已登记（业务语义待独立复核）</div><a href="'+md_path+'">查看原始 Markdown</a></li>'))
    rows.sort(key=lambda x:x[0])
    body = '<h1>'+html.escape(name)+' · 大白话文档导航</h1><p>这是离线阅读入口。下方仅列出 PlanShip 已登记的文档；“已登记”不代表业务验收通过。</p><ul class="doc-grid">'+''.join(r[1] for r in rows)+'</ul>'
    if not rows:
        body += '<p>暂无已登记文档。</p>'
    return ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src &#39;self&#39; data: file:;"><title>'+html.escape(name)+' · PlanShip</title><style>'+CSS+'</style></head><body><main>'+body+'</main></body></html>\n').encode('utf-8')


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
