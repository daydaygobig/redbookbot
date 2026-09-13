# -*- coding: utf-8 -*-
"""
redbookbot 配置 + 执行中心（本地网页）

用法: python config_server.py   (或双击 启动工具.cmd 选 1)
打开: http://127.0.0.1:8932/
功能: 推送配置(GitHub/飞书/LLM) / 凭据脱敏显示 / 一键执行日报全流程 / 测试按钮
仅绑定 127.0.0.1，只有本机能访问。
"""
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "push_config.json")
PORT = 8932
sys.stdout.reconfigure(encoding="utf-8")

DEFAULTS = {
    "redfox": {"api_key": ""},
    "github": {"enabled": False, "token": "", "owner": "", "repo": "",
               "branch": "main", "pages_base": "", "remote_path": "daily"},
    "feishu": {"enabled": False, "webhook": ""},
    "llm": {"enabled": True, "base_url": "", "api_key": "", "model": ""},
}
SECRET_FIELDS = [("redfox", "api_key"), ("github", "token"),
                 ("feishu", "webhook"), ("llm", "api_key")]


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                cfg.setdefault(k, {})
                if isinstance(v, dict):
                    cfg[k].update(v)
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def mask(v):
    if not v:
        return ""
    if len(v) <= 12:
        return "****"
    return v[:6] + "****" + v[-4:]


def http_json(method, url, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


RULES_PATH = os.path.join(HERE, "rules.md")
BACKUP_DIR = os.path.join(HERE, "backups")


def read_rules():
    if os.path.exists(RULES_PATH):
        return open(RULES_PATH, encoding="utf-8").read()
    return ""


def write_rules(content):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if os.path.exists(RULES_PATH):
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.replace(RULES_PATH, os.path.join(BACKUP_DIR, "rules_%s.bak.md" % stamp))
        # 只保留最近 20 份备份
        baks = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("rules_"))
        for old in baks[:-20]:
            os.remove(os.path.join(BACKUP_DIR, old))
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        f.write(content)


# ---------- 动作 ----------

def test_redfox(cfg):
    key = cfg.get("redfox", {}).get("api_key", "")
    if not key:
        # 兼容旧方式: api_key.txt
        p = os.path.join(HERE, "api_key.txt")
        if os.path.exists(p):
            key = open(p, encoding="utf-8").read().strip()
    if not key:
        return {"ok": False, "msg": "请先填写红狐 API Key（redfox.hk 控制台 → 密钥管理）"}
    try:
        from datetime import date as _d, timedelta as _td
        from urllib.parse import quote, urlencode
        yesterday = str(_d.today() - _td(days=1))
        url = ("https://redfox.hk/story/api/cozeSkill/getXhsCozeSkillDataOne?"
               + urlencode({"rankDate": yesterday, "category": "职业发展"}))
        data = http_json("GET", url, headers={"REDFOX_API_KEY": key})
        if data.get("code") == 2000:
            n = len(data.get("data") or [])
            return {"ok": True, "msg": "红狐接口正常，职业发展当日榜返回 %d 条（本次测试消耗约 0.03 积分）" % n}
        return {"ok": False, "msg": "业务码异常 code=%s：%s" % (data.get("code"), data.get("msg"))}
    except urllib.error.HTTPError as e:
        hint = {401: "key 无效", 403: "key 无权限", 3201: "积分不足"}.get(e.code, "HTTP %d" % e.code)
        return {"ok": False, "msg": "红狐接口失败：%s" % hint}
    except Exception as e:
        return {"ok": False, "msg": "失败：%r" % e}


def test_github(cfg):
    gh = cfg["github"]
    if not gh.get("token"):
        return {"ok": False, "msg": "请先填写 GitHub token"}
    try:
        me = http_json("GET", "https://api.github.com/user",
                       headers={"Authorization": "Bearer %s" % gh["token"]})
        return {"ok": True, "msg": "token 有效，账号：%s" % me.get("login")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "msg": "token 验证失败 (HTTP %d)：%s"
                % (e.code, e.read().decode("utf-8", "ignore")[:120])}
    except Exception as e:
        return {"ok": False, "msg": "网络错误：%r" % e}


def github_setup(cfg):
    gh = cfg["github"]
    token, owner, repo = gh.get("token", ""), gh.get("owner", ""), gh.get("repo", "")
    if not (token and owner and repo):
        return {"ok": False, "msg": "请先填 token / owner / repo 并保存"}
    headers = {"Authorization": "Bearer %s" % token,
               "Accept": "application/vnd.github+json"}
    try:
        try:
            http_json("GET", "https://api.github.com/repos/%s/%s" % (owner, repo),
                      headers=headers)
            msg = "仓库已存在：%s/%s" % (owner, repo)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return {"ok": False, "msg":
                        "检查仓库失败 (HTTP %d)。Fine-grained token 请确认 Repository access "
                        "里已勾选该仓库（并勾 Metadata 只读）" % e.code}
            try:
                http_json("POST", "https://api.github.com/user/repos",
                          {"name": repo, "private": False,
                           "description": "有词儿念念选题日报 auto-pushed by redbookbot",
                           "auto_init": True}, headers)
                msg = "仓库创建成功：%s/%s" % (owner, repo)
            except urllib.error.HTTPError as e2:
                return {"ok": False, "msg":
                        "建仓失败 (HTTP %d)。Fine-grained token 无法创建仓库，请先在 GitHub "
                        "网页手动建好仓库并把它加入 token 的 Repository access，再点本按钮开 Pages" % e2.code}
        pages_url = ""
        try:
            p = http_json("POST", "https://api.github.com/repos/%s/%s/pages" % (owner, repo),
                          {"source": {"branch": gh.get("branch", "main"), "path": "/"}}, headers)
            pages_url = p.get("html_url", "")
            msg += "；Pages 已开启"
        except urllib.error.HTTPError as e:
            if e.code == 409:
                msg += "；Pages 已是开启状态"
            else:
                msg += ("；Pages 开启失败 (HTTP %d)。可在仓库 Settings→Pages 手动开，"
                        "或给 token 加 Pages 读写权限后重试" % e.code)
        if not pages_url:
            pages_url = "https://%s.github.io/%s/" % (owner, repo)
        cfg["github"]["pages_base"] = pages_url
        save_config(cfg)
        return {"ok": True, "msg": "%s；pages_base=%s（已保存）" % (msg, pages_url)}
    except Exception as e:
        return {"ok": False, "msg": "失败：%r" % e}


def test_feishu(cfg):
    hook = cfg["feishu"].get("webhook", "")
    if not hook:
        return {"ok": False, "msg": "请先填写飞书 webhook"}
    card = {
        "schema": "2.0", "config": {"wide_screen_mode": True},
        "header": {"template": "green",
                   "title": {"tag": "plain_text", "content": "redbookbot 测试消息"}},
        "body": {"direction": "vertical", "elements": [
            {"tag": "markdown", "content": "**配置成功！**\n以后每天的选题日报会推送到这个群。"}]},
    }
    try:
        req = urllib.request.Request(
            hook, data=json.dumps({"msg_type": "interactive", "card": card}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") not in (None, 0):
            return {"ok": False, "msg": "飞书拒绝 (code=%s)：%s" % (data.get("code"), data.get("msg"))}
        return {"ok": True, "msg": "测试卡片已发送，去飞书群里看看"}
    except Exception as e:
        return {"ok": False, "msg": "发送失败：%r" % e}


def test_llm(cfg):
    llm = cfg.get("llm", {})
    if not (llm.get("api_key") and llm.get("base_url") and llm.get("model")):
        return {"ok": False, "msg": "请先填写并保存 base_url / api_key / 模型名"}
    url = llm["base_url"].strip()
    if "/chat/completions" not in url:
        url = url.rstrip("/") + "/chat/completions"
    payload = {"model": llm["model"].strip(),
               "messages": [{"role": "user", "content": "只回复两个字：正常"}],
               "max_tokens": 20, "stream": False}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % llm["api_key"].strip()}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "msg": "接口正常，模型回复：%s" % reply.strip()[:30]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "msg": "HTTP %d：%s"
                % (e.code, e.read().decode("utf-8", "ignore")[:150])}
    except Exception as e:
        return {"ok": False, "msg": "失败：%r" % e}


# ---------- 任务执行系统 ----------

TASKS = {}
TASK_LOCK = threading.Lock()
TASK_SEQ = [0]


def build_cmd(step, day, yesterday):
    return {
        "fetch": "python fetch_hot.py",
        "generate": "python generate_report.py",
        "build": "python build_report.py daily\\%s.md" % day,
        "push": "python push_report.py daily\\%s" % day,
        "all": ("python fetch_hot.py && python generate_report.py && "
                "python build_report.py daily\\%s.md && python push_report.py daily\\%s" % (day, day)),
    }.get(step)


def _exec(task_id, cmd):
    task = TASKS[task_id]
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=HERE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in p.stdout:
            task["output"].append(line.rstrip())
            if len(task["output"]) > 400:
                task["output"] = task["output"][-400:]
        code = p.wait()
        task["status"] = "done" if code == 0 else "fail"
    except Exception as e:
        task["output"].append("[FAIL] %r" % e)
        task["status"] = "fail"
    task["output"].append("[结束] 状态: %s" % {"done": "成功", "fail": "失败"}[task["status"]])


def start_task(step):
    day = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    cmd = build_cmd(step, day, yesterday)
    if not cmd:
        return None, "未知步骤: %s" % step
    with TASK_LOCK:
        running = [t for t in TASKS.values() if t["status"] == "running"]
        if running:
            return None, "已有任务在执行（%s），请等它完成" % running[0]["name"]
        TASK_SEQ[0] += 1
        task_id = "t%d" % TASK_SEQ[0]
        TASKS[task_id] = {"status": "running", "output": [],
                          "name": {"fetch": "拉取榜单", "generate": "AI生成日报",
                                   "build": "渲染HTML", "push": "推送",
                                   "all": "全流程"}[step]}
    threading.Thread(target=_exec, args=(task_id, cmd), daemon=True).start()
    return task_id, None


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>有词儿念念 · 选题日报控制台</title><style>
:root { --red:#ff2442; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f7f7f8; color:#222; max-width:680px; margin:0 auto; padding:20px 16px; }
h1 { font-size:1.25em; margin-bottom:4px; }
.sub { color:#888; font-size:.85em; margin-bottom:20px; }
.card { background:#fff; border-radius:14px; padding:16px 18px; margin:14px 0;
  box-shadow:0 1px 4px rgba(0,0,0,.06); }
.card h2 { font-size:1em; margin-bottom:12px; padding-left:8px; border-left:4px solid var(--red); }
label { display:block; font-size:.85em; color:#555; margin:10px 0 4px; }
input[type=text], input[type=password] { width:100%; padding:8px 10px;
  border:1px solid #ddd; border-radius:8px; font-size:.9em; }
input:focus { outline:none; border-color:var(--red); }
.secret { display:flex; gap:6px; }
.secret input { flex:1; }
.secret button { background:#eee; border:none; border-radius:8px; padding:0 10px;
  font-size:.8em; cursor:pointer; color:#333; }
.row { display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap; }
button { border:none; border-radius:20px; padding:7px 18px; font-size:.88em; cursor:pointer; }
.primary { background:var(--red); color:#fff; }
.big { background:var(--red); color:#fff; font-size:1em; padding:10px 26px; }
.plain { background:#eee; color:#333; }
.msg { font-size:.85em; margin-top:10px; padding:8px 12px; border-radius:8px; display:none; }
.ok { background:#e8f7ee; color:#187a46; } .err { background:#fdecec; color:#b0213c; }
.switch { display:flex; align-items:center; gap:6px; font-size:.88em; }
.tip { color:#999; font-size:.78em; margin-top:4px; }
a { color:#0a66c2; }
.steps { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
.term { background:#1e1e1e; color:#4ee38a; font-family:Consolas,monospace;
  font-size:.78em; border-radius:10px; padding:12px; margin-top:12px;
  white-space:pre-wrap; word-break:break-all; max-height:280px; overflow-y:auto;
  display:none; }
.status { font-size:.85em; color:#666; margin-top:8px; }
</style></head><body>
<h1>有词儿念念 · 选题日报控制台</h1>
<p class="sub">配置与执行都在这页。凭据只存本机 push_config.json。</p>

<div class="card"><h2>执行日报</h2>
  <div class="steps">
    <button class="plain" onclick="run('fetch')">① 拉取榜单</button>
    <button class="plain" onclick="run('generate')">② AI 生成日报</button>
    <button class="plain" onclick="run('build')">③ 渲染 HTML</button>
    <button class="plain" onclick="run('push')">④ 推送</button>
  </div>
  <div class="row"><button class="big" onclick="run('all')">🚀 一键执行全流程</button></div>
  <div class="status" id="run_status">步骤说明：①拉昨日榜单 → ②LLM按规则生成10题 → ③渲染网页版 → ④推GitHub+飞书</div>
  <div class="term" id="term"></div>
</div>

<div class="card"><h2>红狐数据源（榜单抓取）</h2>
  <label>红狐 API Key（<a href="https://redfox.hk/dashboard/keys" target="_blank">redfox.hk 控制台 → 密钥管理</a>，ak_ 开头）</label>
  <div class="secret"><input type="password" id="rf_key" placeholder="ak_xxxxxxxx">
    <button onclick="toggle('rf_key',this)">显示</button></div>
  <div class="row">
    <button class="primary" onclick="save('redfox')">保存</button>
    <button class="plain" onclick="act('test_redfox','rm')">测试连接</button>
  </div>
  <div class="msg" id="rm"></div>
</div>

<div class="card"><h2>选题规则（rules.md · AI 生成日报的宪法）</h2>
  <textarea id="rules" spellcheck="false" style="width:100%; min-height:320px;
    font-family:Consolas,monospace; font-size:.8em; line-height:1.6; padding:10px;
    border:1px solid #ddd; border-radius:8px;" placeholder="加载中..."></textarea>
  <div class="row">
    <button class="primary" onclick="saveRules()">保存规则</button>
    <button class="plain" onclick="loadRules()">放弃修改，重新加载</button>
  </div>
  <div class="msg" id="rsm"></div>
  <p class="tip">修改后下一次生成日报即生效；每次保存自动备份旧版到 backups/（保留最近 20 份）。
  想回滚就到 backups/ 目录把 .bak.md 改回 rules.md。</p>
</div>

<div class="card"><h2>AI 模型（生成日报用）</h2>
  <label>接口地址 base_url（OpenAI 兼容，如智谱 https://open.bigmodel.cn/api/paas/v4/chat/completions）</label>
  <input type="text" id="llm_url" placeholder="https://open.bigmodel.cn/api/paas/v4/chat/completions">
  <label>API Key</label>
  <div class="secret"><input type="password" id="llm_key" placeholder="sk-xxx">
    <button onclick="toggle('llm_key',this)">显示</button></div>
  <label>模型名（如 glm-4.7 / deepseek-chat / gpt-4o-mini）</label>
  <input type="text" id="llm_model" placeholder="glm-4.7">
  <div class="row">
    <button class="primary" onclick="save('llm')">保存</button>
    <button class="plain" onclick="act('test_llm','lm')">测试连接</button>
  </div>
  <div class="msg" id="lm"></div>
</div>

<div class="card"><h2>GitHub Pages（日报网页版）</h2>
  <label>Token（<a href="https://github.com/settings/tokens" target="_blank">前往生成</a>，Contents 读写）</label>
  <div class="secret"><input type="password" id="gh_token" placeholder="github_pat_xxx / ghp_xxx">
    <button onclick="toggle('gh_token',this)">显示</button></div>
  <label>GitHub 用户名（owner）</label>
  <input type="text" id="gh_owner" placeholder="your-name">
  <label>仓库名（repo）</label>
  <input type="text" id="gh_repo" placeholder="redbook-daily">
  <label>Pages 地址（可点下面按钮自动生成）</label>
  <input type="text" id="gh_pages" placeholder="https://用户名.github.io/仓库名/">
  <div class="row">
    <button class="primary" onclick="save('github')">保存</button>
    <button class="plain" onclick="act('test_github','gm')">测试 Token</button>
    <button class="plain" onclick="act('github_setup','gm')">一键建仓+开Pages</button>
    <label class="switch"><input type="checkbox" id="gh_on"> 启用 GitHub 推送</label>
  </div>
  <div class="msg" id="gm"></div>
</div>

<div class="card"><h2>飞书群机器人</h2>
  <label>Webhook（飞书群 → 设置 → 群机器人 → 添加自定义机器人）</label>
  <div class="secret"><input type="password" id="fs_webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx">
    <button onclick="toggle('fs_webhook',this)">显示</button></div>
  <div class="row">
    <button class="primary" onclick="save('feishu')">保存</button>
    <button class="plain" onclick="act('test_feishu','fm')">发送测试消息</button>
    <label class="switch"><input type="checkbox" id="fs_on"> 启用飞书推送</label>
  </div>
  <div class="msg" id="fm"></div>
</div>

<script>
let curTask = null, pollTimer = null;
function toggle(id, btn) {
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
  btn.textContent = el.type === 'password' ? '显示' : '隐藏';
}
function show(id, ok, msg) {
  const el = document.getElementById(id);
  el.className = 'msg ' + (ok ? 'ok' : 'err');
  el.textContent = msg; el.style.display = 'block';
}
async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)} : undefined);
  return r.json();
}
async function load() {
  const cfg = await api('/api/config');
  document.getElementById('gh_token').value = cfg.github.token_mask || '';
  document.getElementById('gh_owner').value = cfg.github.owner || '';
  document.getElementById('gh_repo').value = cfg.github.repo || '';
  document.getElementById('gh_pages').value = cfg.github.pages_base || '';
  document.getElementById('gh_on').checked = !!cfg.github.enabled;
  document.getElementById('fs_webhook').value = cfg.feishu.webhook_mask || '';
  document.getElementById('fs_on').checked = !!cfg.feishu.enabled;
  document.getElementById('llm_url').value = cfg.llm.base_url || '';
  document.getElementById('llm_key').value = cfg.llm.api_key_mask || '';
  document.getElementById('llm_model').value = cfg.llm.model || '';
  document.getElementById('rf_key').value = cfg.redfox.api_key_mask || '';
}
async function save(part) {
  const val = id => document.getElementById(id).value.trim();
  const body = part === 'github'
    ? {github: {enabled: document.getElementById('gh_on').checked,
        token: val('gh_token'), owner: val('gh_owner'),
        repo: val('gh_repo'), pages_base: val('gh_pages')}}
    : part === 'feishu'
    ? {feishu: {enabled: document.getElementById('fs_on').checked,
        webhook: val('fs_webhook')}}
    : part === 'redfox'
    ? {redfox: {api_key: val('rf_key')}}
    : {llm: {base_url: val('llm_url'), api_key: val('llm_key'), model: val('llm_model')}};
  const r = await api('/api/config', body);
  const id = {github:'gm', feishu:'fm', llm:'lm', redfox:'rm'}[part];
  show(id, r.ok, r.msg); if (r.ok) load();
}
async function act(name, id) {
  show(id, true, '执行中…');
  const r = await api('/api/' + name, {});
  show(id, r.ok, r.msg);
  if (r.ok && name === 'github_setup') load();
}
async function run(step) {
  const r = await api('/api/run', {step});
  if (!r.ok) { document.getElementById('run_status').textContent = r.msg; return; }
  curTask = r.id;
  document.getElementById('term').style.display = 'block';
  document.getElementById('run_status').textContent = '⏳ ' + r.name + ' 执行中…';
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 1000);
}
async function poll() {
  if (!curTask) return;
  const t = await api('/api/task?id=' + curTask);
  document.getElementById('term').textContent = t.output.join('\\n');
  document.getElementById('term').scrollTop = 1e9;
  if (t.status !== 'running') {
    clearInterval(pollTimer); pollTimer = null;
    document.getElementById('run_status').textContent =
      t.status === 'done' ? '✅ 执行成功' : '❌ 执行失败，看下方输出定位';
  }
}
async function loadRules() {
  const r = await api('/api/rules');
  document.getElementById('rules').value = r.content;
}
async function saveRules() {
  const r = await api('/api/rules', {content: document.getElementById('rules').value});
  show('rsm', r.ok, r.msg);
}
load(); loadRules();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                return {}
        return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_html(PAGE)
        elif self.path == "/api/config":
            cfg = load_config()
            pub = {"redfox": dict(cfg.get("redfox", {})),
                   "github": dict(cfg["github"]), "feishu": dict(cfg["feishu"]),
                   "llm": dict(cfg.get("llm", {}))}
            pub["redfox"]["api_key_mask"] = mask(cfg.get("redfox", {}).get("api_key", ""))
            pub["github"]["token_mask"] = mask(cfg["github"].get("token", ""))
            pub["feishu"]["webhook_mask"] = mask(cfg["feishu"].get("webhook", ""))
            pub["llm"]["api_key_mask"] = mask(cfg.get("llm", {}).get("api_key", ""))
            self._send(pub)
        elif self.path == "/api/rules":
            self._send({"content": read_rules()})
        elif self.path.startswith("/api/task"):
            tid = re.search(r"id=(\w+)", self.path)
            task = TASKS.get(tid.group(1)) if tid else None
            if task:
                self._send({"status": task["status"], "output": task["output"]})
            else:
                self._send({"status": "missing", "output": []})
        else:
            self._send({"ok": False, "msg": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/config":
            cfg = load_config()
            body = self._body()
            for part, values in body.items():
                if part not in cfg or not isinstance(values, dict):
                    continue
                for k, v in values.items():
                    # 凭据脱敏占位（含****）或留空 = 不修改原值
                    if (part, k) in SECRET_FIELDS:
                        if not v or "****" in v:
                            continue
                    cfg[part][k] = v
            save_config(cfg)
            self._send({"ok": True, "msg": "已保存（凭据未改动时保留原值）"})
            return
        if self.path == "/api/run":
            body = self._body()
            tid, err = start_task(body.get("step", ""))
            if err:
                self._send({"ok": False, "msg": err})
            else:
                self._send({"ok": True, "id": tid, "name": TASKS[tid]["name"]})
            return
        if self.path == "/api/rules":
            body = self._body()
            content = body.get("content")
            if content is None or not content.strip():
                self._send({"ok": False, "msg": "内容为空，拒绝保存"})
                return
            write_rules(content)
            self._send({"ok": True, "msg": "已保存（旧版本自动备份到 backups/）"})
            return
        cfg = load_config()
        if self.path == "/api/test_redfox":
            self._send(test_redfox(cfg))
        elif self.path == "/api/test_github":
            self._send(test_github(cfg))
        elif self.path == "/api/github_setup":
            self._send(github_setup(cfg))
        elif self.path == "/api/test_feishu":
            self._send(test_feishu(cfg))
        elif self.path == "/api/test_llm":
            self._send(test_llm(cfg))
        else:
            self._send({"ok": False, "msg": "not found"}, 404)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("控制台已启动: http://127.0.0.1:%d/  (Ctrl+C 退出)" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
