# -*- coding: utf-8 -*-
"""
把 daily/YYYY-MM-DD.md 选题日报渲染成 HTML（可点击链接、移动端友好）

用法: python build_report.py daily/2026-09-13.md
输出: daily/2026-09-13.html
"""
import html
import os
import re
import sys

CSS = """
:root { --red: #ff2442; --ink: #222; --sub: #666; --bg: #f7f7f8; --card: #fff; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--ink); line-height: 1.75; padding: 16px;
  max-width: 860px; margin: 0 auto;
}
h1 { font-size: 1.5em; margin: 8px 0 4px; }
h1 .date { color: var(--red); }
.meta { color: var(--sub); font-size: 0.86em; background: #fff3f4;
  border-radius: 8px; padding: 8px 12px; margin: 10px 0 18px; }
h2 { font-size: 1.15em; margin: 28px 0 10px; padding-left: 10px;
  border-left: 4px solid var(--red); }
blockquote { color: var(--sub); font-size: 0.86em; border-left: 3px solid #ddd;
  padding-left: 10px; margin: 4px 0 12px; }
hr { border: none; border-top: 1px solid #e8e8e8; margin: 20px 0; }
.topic { background: var(--card); border-radius: 14px; padding: 16px 18px;
  margin: 14px 0; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.topic h3 { font-size: 1.05em; margin-bottom: 8px; }
.topic > h3:first-child { color: var(--ink); }
.topic p { margin: 5px 0; font-size: 0.92em; }
.topic .hot { color: var(--red); font-weight: 600; font-size: 0.78em;
  border: 1px solid var(--red); border-radius: 20px; padding: 0 8px;
  margin-right: 6px; vertical-align: 2px; white-space: nowrap; display: inline-block; }
a { color: #0a66c2; text-decoration: none; word-break: break-all; }
a:hover { text-decoration: underline; }
a.xhs { display: inline-block; background: var(--red); color: #fff;
  border-radius: 18px; padding: 1px 12px; font-size: 0.82em; margin: 2px 0;
  white-space: nowrap; }
a.xhs:hover { background: #e01e3c; text-decoration: none; }
ul { padding-left: 20px; }
li { margin: 4px 0; font-size: 0.92em; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.88em; }
th, td { border: 1px solid #e5e5e5; padding: 6px 10px; text-align: left; }
th { background: #fafafa; }
.footer { color: var(--sub); font-size: 0.8em; margin-top: 30px;
  border-top: 1px dashed #ddd; padding-top: 10px; }
strong { font-weight: 700; }
@media (max-width: 640px) {
  body { padding: 10px; }
  .topic { padding: 12px 14px; }
}
"""

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"(?<![\(\"'>])(https?://[^\s<)\]]+)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline_html(text):
    """行内元素转义 + 链接/加粗。小红书链接渲染成按钮样式。"""
    out = html.escape(text, quote=False)

    def link_repl(m):
        label, url = m.group(1), m.group(2)
        if "xiaohongshu.com" in url:
            return '<a class="xhs" href="%s" target="_blank">打开原帖 ↗</a>' % html.escape(url, quote=True)
        return '<a href="%s" target="_blank">%s</a>' % (html.escape(url, quote=True), html.escape(label))

    out = LINK_RE.sub(link_repl, out)

    def bare_repl(m):
        url = m.group(1).rstrip(".,;:，。；")  # 去掉行尾紧跟的标点
        if "xiaohongshu.com" in url:
            return '<a class="xhs" href="%s" target="_blank">打开原帖 ↗</a>' % html.escape(url, quote=True)
        return '<a href="%s" target="_blank">%s</a>' % (html.escape(url, quote=True), html.escape(url))

    # 占位符保护已转换的 <a> 标签, 只对剩余裸 URL 生效
    placeholders = []
    def stash(m):
        placeholders.append(m.group(0))
        return "\x00%d\x00" % (len(placeholders) - 1)
    out = re.sub(r'<a [^>]+>.*?</a>', stash, out)
    out = BARE_URL_RE.sub(bare_repl, out)
    for idx, ph in enumerate(placeholders):
        out = out.replace("\x00%d\x00" % idx, ph)

    out = BOLD_RE.sub(r"<strong>\1</strong>", out)
    return out


def parse_table(lines, i):
    """从 lines[i] 开始解析表格, 返回 (html, 下一行索引)"""
    rows = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            rows.append(cells)
        i += 1
    if not rows:
        return None, i
    head, body = rows[0], rows[1:]
    t = ["<table><thead><tr>"]
    t += ["<th>%s</th>" % inline_html(c) for c in head]
    t.append("</tr></thead><tbody>")
    for r in body:
        t.append("<tr>")
        t += ["<td>%s</td>" % inline_html(c) for c in r]
        t.append("</tr>")
    t.append("</tbody></table>")
    return "".join(t), i


def build(md_text):
    lines = md_text.splitlines()
    out = []
    i = 0
    in_topic = False
    title = ""
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("|"):
            tbl, i = parse_table(lines, i)
            if tbl:
                out.append(tbl)
            continue
        if s.startswith("### "):
            if in_topic:
                out.append("</div>")
            head = s[4:].strip()
            # 主航道徽章
            badge = ""
            m = re.search(r"（(暴论式标题)）", head)
            title_text = head.replace("（暴论式标题）", "").strip()
            out.append('<div class="topic"><h3><span class="hot">选题</span>%s</h3>' % inline_html(title_text))
            in_topic = True
            i += 1
            continue
        if s.startswith("## "):
            if in_topic:
                out.append("</div>")
                in_topic = False
            out.append("<h2>%s</h2>" % inline_html(s[3:].strip()))
            i += 1
            continue
        if s.startswith("# "):
            title = s[2:].strip()
            out.append("<h1>%s</h1>" % inline_html(title))
            i += 1
            continue
        if s.startswith("> "):
            out.append("<blockquote>%s</blockquote>" % inline_html(s[2:].strip()))
            i += 1
            continue
        if s == "---":
            if in_topic:
                out.append("</div>")
                in_topic = False
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                out.append("<li>%s</li>" % inline_html(lines[i].strip()[2:]))
                i += 1
            out.append("</ul>")
            continue
        # 普通段落
        out.append("<p>%s</p>" % inline_html(s))
        i += 1
    if in_topic:
        out.append("</div>")
    return "".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python build_report.py daily/YYYY-MM-DD.md")
    md_path = sys.argv[1]
    md = open(md_path, encoding="utf-8").read()
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(md_path))
    date = date_m.group(1) if date_m else ""
    body = build(md)
    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>有词儿念念选题日报 %s</title><style>%s</style></head>
<body>%s
<p class="footer">有词儿念念 · 选题日报系统 · 参考帖链接点击直达小红书原帖</p>
</body></html>""" % (date, CSS, body)
    html_path = md_path[:-3] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print("[OK] HTML 已生成: %s (%.1f KB)" % (html_path, os.path.getsize(html_path) / 1024))


if __name__ == "__main__":
    main()
