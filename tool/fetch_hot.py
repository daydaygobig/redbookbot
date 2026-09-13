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


def http_get(path, params, key):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "REDFOX_API_KEY": key,
        "User-Agent": "xhs-topic-daily/0.2",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_rank(kind, api, rank_date, category, key):
    data = http_get(api, {"rankDate": rank_date, "category": category}, key)
    rows = data.get("data") if data.get("code") == 2000 else None
    if rows is None:
        print("[FAIL] %s %s code=%s msg=%s" % (category, kind, data.get("code"), data.get("msg")))
        return None
    return data


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
    for cat in categories:
        for kind, api in (("daily", DAILY_API), ("weekly", WEEKLY_API)):
            data = fetch_rank(kind, api, rank_date, cat, key)
            if data is None:
                continue
            path = os.path.join(out_dir, "%s_%s.json" % (cat, kind))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            rows = data["data"]
            total += len(rows)
            top = max(rows, key=lambda r: parse_count(
                (r.get("anaAdd") or {}).get("addInteractiveount")))
            t = (top.get("title") or top.get("desc") or "(无标题)")[:30] if top else "-"
            print("  [OK] %s/%s: %d 条 -> %s | 热度Top: %s" %
                  (cat, kind, len(rows), os.path.relpath(path, HERE), t))
    print("共 %d 条" % total)


if __name__ == "__main__":
    main()
