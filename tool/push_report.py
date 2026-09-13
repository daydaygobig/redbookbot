# -*- coding: utf-8 -*-
"""
日报双通道推送：GitHub (Contents API, 配合 Pages) + 飞书 (群机器人 webhook)

用法:
  python push_report.py daily/2026-09-13          # 自动找 .md/.html
  python push_report.py daily/2026-09-13 --summary "今日主打双休话题"

配置: push_config.json (首次运行自动生成模板, 填好后再跑)
"""
import base64
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "push_config.json")

CONFIG_TEMPLATE = {
    "github": {
        "enabled": False,
        "token": "",
        "owner": "",
        "repo": "",
        "branch": "main",
        "pages_base": "https://OWNER.github.io/REPO/",
        "remote_path": "daily"
    },
    "feishu": {
        "enabled": False,
        "webhook": ""
    }
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG_TEMPLATE, f, ensure_ascii=False, indent=2)
        sys.exit("[提示] 已生成配置模板 %s，请填写 token/webhook 后将 enabled 改为 true 再运行" % CONFIG_PATH)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def http_json(method, url, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------- GitHub ----------------

def github_upload(cfg, html_path, date):
    gh = cfg["github"]
    token, owner, repo = gh["token"], gh["owner"], gh["repo"]
    if not (token and owner and repo):
        print("[SKIP] GitHub 配置不完整")
        return None
    api = "https://api.github.com/repos/%s/%s/contents/%s/%s.html" % (
        owner, repo, gh.get("remote_path", "daily"), date)
    headers = {
        "Authorization": "Bearer %s" % token,
        "Accept": "application/vnd.github+json",
    }
    content = open(html_path, "rb").read()
    payload = {
        "message": "选题日报 %s" % date,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": gh.get("branch", "main"),
    }
    # 已存在则携带 sha 覆盖
    try:
        existing = http_json("GET", api, headers=headers)
        if isinstance(existing, dict) and existing.get("sha"):
            payload["sha"] = existing["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    result = http_json("PUT", api, payload, headers)
    print("[OK] GitHub 已上传: %s (commit %s)" % (
        result.get("content", {}).get("html_url", api),
        str(result.get("commit", {}).get("sha", ""))[:7]))
    base = gh.get("pages_base", "").rstrip("/")
    return "%s/%s/%s.html" % (base, gh.get("remote_path", "daily"), date) if base else None


# ---------------- 飞书 ----------------

def extract_topics(md_path, limit=10):
    """从日报 md 提取题目列表 (### 行)"""
    topics = []
    if md_path and os.path.exists(md_path):
        for line in open(md_path, encoding="utf-8"):
            m = re.match(r"### \d+\.《(.+?)》", line.strip())
            if m:
                topics.append(m.group(1))
            if len(topics) >= limit:
                break
    return topics


def feishu_push(cfg, date, topics, page_url, summary=""):
    hook = cfg["feishu"]["webhook"]
    if not hook:
        print("[SKIP] 飞书 webhook 未配置")
        return False
    lines = ["**有词儿念念选题日报 %s**" % date]
    if summary:
        lines.append("")
        lines.append(summary)
    if topics:
        lines.append("")
        lines.append("**今日 10 题**")
        lines.extend("%d. %s" % (i, t) for i, t in enumerate(topics, 1))
    lines.append("")
    if page_url:
        lines.append("[点开今日完整日报（参考帖可点击直达）](%s)" % page_url)
    else:
        lines.append("（GitHub Pages 未配置，请在本地查看 HTML）")
    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "选题日报 %s" % date},
        },
        "body": {"direction": "vertical", "elements": [{"tag": "markdown", "content": "\n".join(lines)}]},
    }
    payload = {"msg_type": "interactive", "card": card}
    req = urllib.request.Request(
        hook, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # 飞书失败也返回 HTTP 200, 必须查业务码
    code = data.get("code")
    if code not in (None, 0):
        print("[FAIL] 飞书拒绝消息 (code=%s): %s" % (code, data.get("msg")))
        return False
    print("[OK] 飞书已推送")
    return True


def main():
    args = sys.argv[1:]
    base = args[0] if args else ""
    summary = ""
    if "--summary" in args:
        summary = args[args.index("--summary") + 1]
    m = re.search(r"(\d{4}-\d{2}-\d{2})", base)
    if not m:
        sys.exit("用法: python push_report.py daily/YYYY-MM-DD [--summary ...]")
    date = m.group(1)
    html_path = base if base.endswith(".html") else base + ".html"
    md_path = base + ".md"
    if not os.path.exists(html_path):
        sys.exit("找不到 %s（先运行 build_report.py 生成 HTML）" % html_path)

    cfg = load_config()
    page_url = None
    if cfg["github"].get("enabled"):
        page_url = github_upload(cfg, html_path, date)
    else:
        print("[SKIP] GitHub 推送未启用")
    if cfg["feishu"].get("enabled"):
        feishu_push(cfg, date, extract_topics(md_path), page_url, summary)
    else:
        print("[SKIP] 飞书推送未启用")


if __name__ == "__main__":
    main()
