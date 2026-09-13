# -*- coding: utf-8 -*-
"""
AI 生成选题日报（需在配置页填写 LLM 接口，OpenAI 兼容格式）

用法: python generate_report.py [--date 2026-09-13] [--force]
流程: data/<昨日>/ 榜单 + rules.md + history.md -> 调 LLM -> daily/<日期>.md -> 追加 history.md
"""
import glob
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")


def parse_count(s):
    s = str(s or "").strip().lower().replace("+", "")
    try:
        return int(float(s[:-1]) * 10000) if s.endswith("w") else int(float(s))
    except ValueError:
        return 0


def load_llm():
    p = os.path.join(HERE, "push_config.json")
    if not os.path.exists(p):
        sys.exit("[FAIL] 请先在配置页填写 LLM 接口（http://127.0.0.1:8932/）")
    cfg = json.load(open(p, encoding="utf-8"))
    llm = cfg.get("llm", {})
    if not (llm.get("api_key") and llm.get("base_url") and llm.get("model")):
        sys.exit("[FAIL] LLM 接口未配置或未保存，请到配置页 'AI 模型' 卡片填写并保存")
    return llm


def collect_candidates(rank_date):
    """读 data/<date>/*.json -> 去重、按新增互动排序，返回 (文本行, 链接集合)"""
    files = glob.glob(os.path.join(HERE, "data", rank_date, "*.json"))
    if not files:
        sys.exit("[FAIL] 找不到 data/%s/ 榜单数据，请先执行拉取（fetch_hot.py）" % rank_date)
    seen = {}
    for f in files:
        tag = os.path.basename(f).replace(".json", "")
        rows = json.load(open(f, encoding="utf-8")).get("data") or []
        for r in rows:
            aid = (r.get("photoJumpUrl") or "")[-24:]
            if not aid or aid in seen:
                continue
            ana = r.get("anaAdd") or {}
            seen[aid] = {
                "cat": tag.split("_")[0],
                "inter": parse_count(ana.get("addInteractiveount")),
                "line": "[%s|%s粉] %s | 赞%s 藏%s 新增互动%d | %s | https://www.xiaohongshu.com/explore/%s | %s" % (
                    tag.split("_")[0], r.get("fans") or "?",
                    (r.get("title") or "").strip()[:40],
                    ana.get("addLikeCount", "?"), ana.get("addCollectedCunt", "?"),
                    parse_count(ana.get("addInteractiveount")),
                    (r.get("publicTime") or "")[:10], aid,
                    (r.get("desc") or "").replace("\n", " ")[:50]),
            }
    top = sorted(seen.values(), key=lambda x: -x["inter"])[:80]
    return [t["line"] for t in top]


def call_llm(llm, system, user):
    url = llm["base_url"].strip()
    if "/chat/completions" not in url:
        url = url.rstrip("/") + "/chat/completions"
    payload = {
        "model": llm["model"].strip(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        # glm-5.3 始终开启思考(思考也占输出额度), 需要更大输出空间
        "max_tokens": 32768 if "5.3" in llm["model"] else 12000,
        "stream": False,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % llm["api_key"].strip()},
        method="POST")
    print("调用 LLM 生成中（%s, 约 1~3 分钟）..." % payload["model"])
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        sys.exit("[FAIL] LLM 返回异常: %s" % json.dumps(data, ensure_ascii=False)[:300])


def main():
    args = sys.argv[1:]
    force = "--force" in args
    today = str(date.today())
    if "--date" in args:
        today = args[args.index("--date") + 1]
    rank_date = str(date.today() - timedelta(days=1))

    out_path = os.path.join(HERE, "daily", today + ".md")
    if os.path.exists(out_path) and not force:
        print("[SKIP] daily/%s.md 已存在（加 --force 覆盖重新生成）" % today)
        return

    llm = load_llm()
    rules = open(os.path.join(HERE, "rules.md"), encoding="utf-8").read()
    hist_path = os.path.join(HERE, "history.md")
    hist = open(hist_path, encoding="utf-8").read()
    hist_lines = [l for l in hist.splitlines() if re.match(r"\d{4}-\d{2}-\d{2}", l.strip())]
    recent = "\n".join(hist_lines[-60:]) or "（暂无）"

    cand_lines = collect_candidates(rank_date)
    candidates = "\n".join(cand_lines)

    system = (
        "你是小红书账号「有词儿念念」的选题日报生成器，叙事人设是「大厂高管（退休版）」"
        "——高层视角回顾式叙事，见惯勾心斗角与跨部门内斗，退休后把真话讲给中层听。"
        "严格遵循下面的规则文件生成日报。\n"
        "要求：\n"
        "1) 输出纯 Markdown，不要任何解释性开场白，第一行必须是 '# 有词儿念念选题日报 <日期>'\n"
        "2) 严格遵守规则文件的日报输出格式（热点速览/10题/暴论候选），不输出任何数据口径说明\n"
        "3) 所有标题必须过'人设标题三板斧'（视角转换/高管黑话/回顾句式），"
        "像退休大厂高管在开口，不是普通博主在分析\n"
        "4) 每日 10 题 = 热点题约 6 个（必须从候选清单选参考帖并引用赞藏数据）"
        "+ 情景题约 4 个（情景再现模式，编剧式高管视角，标注情景来源，不需参考帖）\n"
        "5) 参考帖链接从候选清单原样复制（24位ID一个字符都不能改）\n"
        "6) 互动数据引用时保留模糊值原样（如 3w+）\n"
        "7) 过滤纯娱乐内容（明星/游戏/二次元/K12课程等），只取职场/成长/搞钱相关信号\n"
        "8) 主航道题不少于 6 个，模板裂变题不少于 3 个（模板 1~11），"
        "与历史清单重复的题不许出现\n\n"
        "===== 规则文件 rules.md =====\n" + rules +
        "\n\n===== 历史已出题目（禁止重复）=====\n" + recent
    )
    user = (
        "今天是 %s。以下是 %s 红狐爆款榜单候选（按新增互动降序，格式：[分类|粉丝] 标题 | 数据 | 日期 | 链接 | 描述）：\n\n%s\n\n"
        "请生成今天（%s）的选题日报。" % (today, rank_date, candidates, today)
    )

    md = call_llm(llm, system, user)
    md = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", md.strip())

    n_topics = len(re.findall(r"^### ", md, flags=re.M))
    if n_topics < 8:
        sys.exit("[FAIL] 生成结果只有 %d 个题目（要求10个），请重试" % n_topics)

    # 校验链接真实性：输出的笔记ID必须存在于候选数据
    valid_ids = set(re.findall(r"explore/(\w{24})", "\n".join(cand_lines)))
    used_ids = set(re.findall(r"explore/(\w{24})", md))
    bad = used_ids - valid_ids
    if bad:
        print("[WARN] LLM 引用了 %d 个候选清单外的链接（已保留，建议人工核对）: %s"
              % (len(bad), ", ".join(list(bad)[:5])))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print("[OK] 日报已生成: daily/%s.md（%d 题）" % (today, n_topics))

    # 追加历史清单
    with open(hist_path, "a", encoding="utf-8") as f:
        for t in re.findall(r"^### \d+\.《(.+?)》", md, flags=re.M):
            f.write("%s | %s | (LLM生成) | 未采用\n" % (today, t))
    print("[OK] history.md 已追加去重记录")


if __name__ == "__main__":
    main()
