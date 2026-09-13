# -*- coding: utf-8 -*-
"""
红狐(RedFoxHub)小红书数据质量验证脚本

用途: 在正式搭建选题日报系统前, 一键验证红狐 API 的可用性与数据质量。
用法:
  1. 设置环境变量 REDFOX_API_KEY, 或将 key 写入同目录 api_key.txt
  2. python verify_redfox.py [分类名]     # 分类默认: 职业发展
输出:
  - 控制台: 接口状态 / 字段完整性 / 热度 TOP5 摘要 / 抽样核对链接
  - samples/: 每个接口的原始 JSON 响应
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://redfox.hk"
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "samples")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# 每日爆款榜单(当日互动暴涨TOP50) — GET
DAILY_API = "/story/api/cozeSkill/getXhsCozeSkillDataOne"
# 七日爆款榜单(近7天热门TOP50) — GET
WEEKLY_API = "/story/api/cozeSkill/getXhsCozeSkillDataSeven"
# 作品内容详情(完整正文) — POST
DETAIL_API = "/story/api/xhsUser/queryWorkDetail"

# 红狐支持的 25 个分类(榜单接口的 category 参数)
CATEGORIES = [
    "综合全部", "出行代步", "医疗保健", "休闲爱好", "综合杂项", "婚庆婚礼",
    "居家装修", "影视娱乐", "星座情感", "拍摄记录", "学习教育", "旅行度假",
    "亲子育儿", "日常生活", "科学探索", "数码科技", "时尚穿搭", "化妆美容",
    "个人护理", "美味佳肴", "职业发展", "宠物天地", "新闻资讯", "体育锻炼",
    "潮流鞋包",
]

# 榜单返回中必须非空才算合格的字段
REQUIRED_FIELDS = ["title", "publicTime", "photoJumpUrl", "coverUrl",
                   "userName", "fans", "desc"]
REQUIRED_ANAADD = ["addInteractiveount", "addLikeCount", "addCollectedCunt"]


def get_api_key():
    # 读取顺序: push_config.json(redfox.api_key) -> api_key.txt -> 环境变量
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
        key_file = os.path.join(HERE, "api_key.txt")
        if os.path.exists(key_file):
            with open(key_file, encoding="utf-8") as f:
                key = f.read().strip()
    if not key:
        print("[FAIL] 未找到红狐 API Key（控制台 '红狐数据源' 卡片 / api_key.txt / 环境变量）")
        sys.exit(1)
    return key


def http_get(path, params, key):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "REDFOX_API_KEY": key,
        "User-Agent": "xhs-topic-daily-verify/0.1",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post(path, payload, key):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "REDFOX_API_KEY": key,
            "Content-Type": "application/json",
            "User-Agent": "xhs-topic-daily-verify/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def save_sample(name, payload):
    path = os.path.join(SAMPLES_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("  原始数据已存: %s" % os.path.relpath(path, HERE))


def parse_count(s):
    """'4w+'/'4w' -> 40000, '1221' -> 1221, 解析失败 -> None"""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip().lower().replace("+", "")
    try:
        if s.endswith("w"):
            return int(float(s[:-1]) * 10000)
        return int(float(s))
    except ValueError:
        return None


def check_rank_list(tag, rows):
    """字段完整性与热度分布检查, 返回热度 TOP5"""
    print("  条目数: %d" % len(rows))
    total = max(len(rows), 1)
    for field in REQUIRED_FIELDS:
        ok = sum(1 for r in rows if str(r.get(field) or "").strip())
        print("  字段 %-14s 非空 %d/%d (%.0f%%)%s" % (
            field, ok, len(rows), ok * 100.0 / total,
            "" if ok == len(rows) else "  <-- 注意"))
    ana_ok = sum(
        1 for r in rows
        if all(str((r.get("anaAdd") or {}).get(k) or "").strip()
               for k in REQUIRED_ANAADD)
    )
    print("  互动数据 anaAdd     非空 %d/%d" % (ana_ok, len(rows)))

    scored = []
    for r in rows:
        v = parse_count((r.get("anaAdd") or {}).get("addInteractiveount", ""))
        scored.append((v if v is not None else -1, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:5]]


def print_top5(tag, rows):
    print("  ---- 热度 TOP5 (请人工点开链接, 与小红书实际数据核对) ----")
    for i, r in enumerate(rows, 1):
        ana = r.get("anaAdd") or {}
        print("  %d. %s" % (i, r.get("title") or "(无标题)"))
        print("     发布: %s | 新增互动: %s 赞:%s 藏:%s | 作者: %s(%s粉)"
              % (r.get("publicTime"), ana.get("addInteractiveount"),
                 ana.get("addLikeCount"), ana.get("addCollectedCunt"),
                 r.get("userName"), r.get("fans")))
        print("     链接: %s" % r.get("photoJumpUrl"))
        desc = (r.get("desc") or "").replace("\n", " ")
        if desc:
            print("     描述: %s" % desc[:60])


def main():
    category = sys.argv[1] if len(sys.argv) > 1 else "职业发展"
    if category not in CATEGORIES:
        print("[WARN] 分类 '%s' 不在红狐支持的 25 个分类中:" % category)
        print("       %s" % "、".join(CATEGORIES))
    key = get_api_key()
    # T+1 口径: 榜单每天 19:00 更新"昨日"数据, 因此默认查昨天
    yesterday = str(date.today() - timedelta(days=1))

    print("=" * 64)
    print("红狐数据质量验证 | 分类: %s | 榜单日期: %s (昨日)" % (category, yesterday))
    print("=" * 64)

    # ---- 1. 每日爆款榜单 ----
    print("\n[1/3] 每日爆款笔记榜单 (当日互动暴涨 TOP50)")
    try:
        daily = http_get(DAILY_API, {"rankDate": yesterday,
                                     "category": category}, key)
        save_sample("daily_%s_%s.json" % (category, yesterday), daily)
        if daily.get("code") == 2000 and isinstance(daily.get("data"), list):
            top5 = check_rank_list("daily", daily["data"])
            print_top5("daily", top5)
            first_link = next((r.get("photoJumpUrl")
                               for r in daily["data"] if r.get("photoJumpUrl")),
                              None)
        else:
            print("  [FAIL] 业务码异常: code=%s msg=%s"
                  % (daily.get("code"), daily.get("msg")))
            first_link = None
    except Exception as e:
        print("  [FAIL] 请求失败: %r" % e)
        first_link = None

    # ---- 2. 七日爆款榜单 ----
    print("\n[2/3] 七日爆款笔记榜单 (近7天热门 TOP50)")
    weekly_rows = []
    try:
        weekly = http_get(WEEKLY_API, {"rankDate": yesterday,
                                       "category": category}, key)
        save_sample("weekly_%s_%s.json" % (category, yesterday), weekly)
        if weekly.get("code") == 2000 and isinstance(weekly.get("data"), list):
            weekly_rows = weekly["data"]
            top5 = check_rank_list("weekly", weekly_rows)
            print_top5("weekly", top5)
        else:
            print("  [FAIL] 业务码异常: code=%s msg=%s"
                  % (weekly.get("code"), weekly.get("msg")))
    except Exception as e:
        print("  [FAIL] 请求失败: %r" % e)

    # ---- 3. 作品详情(验证能否拿到完整正文) ----
    print("\n[3/3] 作品内容详情 (验证完整正文的可获取性)")
    detail_ok = False
    if weekly_rows or (first_link if 'first_link' in dir() else None):
        link = None
        for r in weekly_rows:
            if r.get("photoJumpUrl"):
                link = r["photoJumpUrl"]
                break
        if not link and first_link:
            link = first_link
        if link:
            try:
                detail = http_post(DETAIL_API, {"workLink": link}, key)
                save_sample("detail_sample.json", detail)
                d = detail.get("data") or {}
                if detail.get("code") == 2000 and d:
                    desc_len = len(d.get("workDesc") or "")
                    print("  [OK] 标题: %s" % (d.get("workTitle") or "")[:50])
                    print("       正文长度: %d 字 | 点赞 %s | 收藏 %s | 发布 %s"
                          % (desc_len, d.get("workLikedCount"),
                             d.get("workCollectedCount"),
                             d.get("workPublishTime")))
                    print("       正文开头: %s"
                          % (d.get("workDesc") or "")[:80].replace("\n", " "))
                    detail_ok = desc_len > 50
                else:
                    print("  [FAIL] 业务码异常: code=%s msg=%s"
                          % (detail.get("code"), detail.get("msg")))
            except Exception as e:
                print("  [FAIL] 请求失败: %r" % e)
        else:
            print("  [SKIP] 前两步未取得任何笔记链接")
    else:
        print("  [SKIP] 前两步未取得任何笔记链接")

    # ---- 结论 ----
    print("\n" + "=" * 64)
    print("验证要点回顾:")
    print("  a. TOP5 链接请逐条点开, 核对标题/点赞量是否与小红书实际一致")
    print("  b. 字段非空比例 100%% 且链接核对无误 -> 数据质量合格")
    print("  c. 详情接口%s拿到完整正文(选题分析的主要素材)" %
          ("已" if detail_ok else "未能"))
    print("=" * 64)


if __name__ == "__main__":
    main()
