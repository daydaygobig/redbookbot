# -*- coding: utf-8 -*-
"""
拉取红狐小红书爆款榜单（日报系统采集环节）

用法:
  python fetch_hot.py                          # 昨日 + 默认分类(职业发展,学习教育)
  python fetch_hot.py --date 2026-09-12        # 指定日期
  python fetch_hot.py --categories "职业发展,学习教育,星座情感"
输出: data/<date>/<分类>_daily.json / <分类>_weekly.json + 控制台摘要
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://redfox.hk"
DAILY_API = "/story/api/cozeSkill/getXhsCozeSkillDataOne"
WEEKLY_API = "/story/api/cozeSkill/getXhsCozeSkillDataSeven"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CATEGORIES = ["职业发展", "学习教育"]


def get_api_key():
    # 读取顺序: push_config.json(redfox.api_key) -> api_key.txt -> 环境变量
    import json
    p = os.path.join(HERE, "push_config.json")
    if os.path.exists(p):
        try:
            key = json.load(open(p, encoding="utf-8")).get("redfox", {}).get("api_key", "")
            if key and "****" not in key:
                return key.strip()
        except Exception:
            pass
    key = os.environ.get("REDFOX_API_KEY", "").strip()
    if not key:
        p = os.path.join(HERE, "api_key.txt")
        if os.path.exists(p):
            key = open(p, encoding="utf-8").read().strip()
    if not key:
        sys.exit("[FAIL] 未找到红狐 API Key（控制台 '红狐数据源' 卡片 / api_key.txt / 环境变量）")
    return key


def http_get(path, params, key, retries=3):
    """带重试的 GET：本地代理抖动会造成 SSL 断连，自动退避重试"""
    import time
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={
            "REDFOX_API_KEY": key,
            "User-Agent": "xhs-topic-daily/0.2",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = attempt * 2
                print("  [重试] 第%d次失败(%s)，%d秒后重试..." % (attempt, type(e).__name__, wait))
                time.sleep(wait)
    print("  [FAIL] 连接红狐失败：%r" % last_err)
    print("  提示: 若在用 VPN/代理，请确认节点可用后重试")
    return None


def fetch_rank(kind, api, rank_date, category, key):
    """返回 (data, 实际日期)。每日榜在当天19:00前尚未生成昨日数据 -> 自动回退前天"""
    data = http_get(api, {"rankDate": rank_date, "category": category}, key)
    if data is None:
        return None, rank_date
    rows = data.get("data") if data.get("code") == 2000 else None
    if rows is None:
        print("[FAIL] %s %s code=%s msg=%s" % (category, kind, data.get("code"), data.get("msg")))
        return None, rank_date
    if not rows and rank_date == str(date.today() - timedelta(days=1)):
        # 昨日榜单还没生成(每天19:00更新昨日), 回退到前天
        prev = str(date.today() - timedelta(days=2))
        print("  [提示] %s 的%s榜尚未生成（每天19:00更新昨日），自动改用 %s" % (rank_date, kind, prev))
        data = http_get(api, {"rankDate": prev, "category": category}, key)
        if data is None or data.get("code") != 2000 or not data.get("data"):
            print("[FAIL] %s %s 前天(%s)也无数据" % (category, kind, prev))
            return None, rank_date
        return data, prev
    return data, rank_date


def parse_count(s):
    """'4w+' -> 40000, '1221' -> 1221, 失败 -> 0"""
    s = str(s or "").strip().lower().replace("+", "")
    try:
        return int(float(s[:-1]) * 10000) if s.endswith("w") else int(float(s))
    except ValueError:
        return 0


def main():
    args = sys.argv[1:]
    rank_date = str(date.today() - timedelta(days=1))
    categories = DEFAULT_CATEGORIES
    if "--date" in args:
        rank_date = args[args.index("--date") + 1]
    if "--categories" in args:
        categories = [c.strip() for c in args[args.index("--categories") + 1].split(",") if c.strip()]

    key = get_api_key()
    out_dir = os.path.join(HERE, "data", rank_date)
    os.makedirs(out_dir, exist_ok=True)

    print("采集日期: %s (T+1 口径) | 分类: %s" % (rank_date, "、".join(categories)))
    total = 0
    ok_count = 0
    expect = len(categories) * 2
    for cat in categories:
        for kind, api in (("daily", DAILY_API), ("weekly", WEEKLY_API)):
            data, used_date = fetch_rank(kind, api, rank_date, cat, key)
            if data is None:
                continue
            # 回退时目录名用实际日期, 保证 generate 能对上
            used_dir = os.path.join(HERE, "data", used_date)
            os.makedirs(used_dir, exist_ok=True)
            path = os.path.join(used_dir, "%s_%s.json" % (cat, kind))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            rows = data["data"]
            total += len(rows)
            ok_count += 1
            if rows:
                top = max(rows, key=lambda r: parse_count(
                    (r.get("anaAdd") or {}).get("addInteractiveount")))
                t = (top.get("title") or top.get("desc") or "(无标题)")[:30]
            else:
                t = "-"
            print("  [OK] %s/%s: %d 条 -> %s | 热度Top: %s" %
                  (cat, kind, len(rows), os.path.relpath(path, HERE), t))
    print("共 %d 条" % total)
    if ok_count == 0:
        sys.exit("[FAIL] 全部接口失败，请检查网络（VPN/代理节点）后重试")
    if ok_count < expect:
        print("[WARN] %d/%d 个接口成功，日报生成可能数据不足" % (ok_count, expect))


if __name__ == "__main__":
    main()
