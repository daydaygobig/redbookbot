# 碎碎念选题日报系统（redbookbot）

http://127.0.0.1:8932/


每天自动产出 10 个选题的日报工具：拉取红狐爆款榜单 → AI 按规则生成选题 →
渲染 HTML 日报 → 自动推送 GitHub Pages + 飞书群。

## 当前状态

- [x] 红狐 API 验证通过（数据真实、字段完整、内部一致）
- [x] rules.md v2（碎碎念 IP 宪法，依据 SOP/IP策划/竞品分析三份文档）
- [x] 第一期日报已产出（2026-09-13，md + html）
- [x] HTML 渲染器（题目卡片、可点击参考帖按钮、移动端适配）
- [x] 双通道推送脚本（GitHub Contents API + 飞书 webhook 卡片）
- [ ] **等待：填写 push_config.json（GitHub token + 飞书 webhook）**
- [ ] 配置每日定时（ZCode 定时任务，建议每天 19:30 后）

## 每日流程（四步管线）

```bash
cd /d/Backup/redbookbot

# 1. 拉数（昨日榜单，职业发展+学习教育）
python fetch_hot.py

# 2. AI 生成日报（对 ZCode 说"跑今天的选题日报"）
#    -> 生成 daily/YYYY-MM-DD.md，追加 history.md

# 3. 渲染 HTML
python build_report.py daily/YYYY-MM-DD.md

# 4. 推送 GitHub + 飞书（需先配好 push_config.json）
python push_report.py daily/YYYY-MM-DD --summary "今日主打XX话题"
```

## 推送配置（push_config.json）

| 字段 | 说明 |
|---|---|
| github.token | GitHub Personal Access Token（需要 repo 权限） |
| github.owner / repo | 目标仓库（建议专用公开仓库存日报，开 GitHub Pages） |
| github.pages_base | Pages 地址，如 https://用户名.github.io/仓库名/ |
| feishu.webhook | 飞书群机器人 webhook 地址（群设置→群机器人→自定义机器人） |

- GitHub 走 Contents API 直接上传 HTML（无需本地 git），已存在则覆盖更新
- 飞书发红色卡片：10 题标题 + 日报链接；注意飞书失败也返回 HTTP 200，
  脚本已按业务码判断成败
- `push_config.json` / `api_key.txt` 已列入 .gitignore，勿提交公开仓库

## 文件说明

| 文件 | 作用 |
|---|---|
| `rules.md` | IP 宪法 + 选题规则（人设/主航道/模板库/禁忌/日报格式） |
| `fetch_hot.py` | 拉取红狐每日/七日爆款榜单 → data/日期/ |
| `build_report.py` | daily md → HTML（小红书链接自动转"打开原帖"按钮） |
| `push_report.py` | 推送 GitHub Pages + 飞书卡片 |
| `history.md` | 已出题目清单（AI 去重用，每期追加） |
| `daily/` | 日报输出（md + html） |
| `data/` `samples/` | 榜单原始 JSON |
| `verify_redfox.py` | API 数据质量验证（已完成使命，留存备用） |

## 红狐 API 摘要

| 接口 | 用途 | 价格 |
|---|---|---|
| GET /story/api/cozeSkill/getXhsCozeSkillDataOne | 每日爆款 TOP50 | ¥0.03/次起 |
| GET /story/api/cozeSkill/getXhsCozeSkillDataSeven | 七日爆款 TOP50 | ¥0.03/次起 |
| POST /story/api/xhsUser/queryWorkDetail | 作品详情(完整正文) | ¥0.02/次起 |

- 鉴权 REDFOX_API_KEY（读 api_key.txt 或环境变量）；T+1（19:00 更新昨日）
- 每天成本约 0.06~0.1 积分；免费积分 7 天有效，之后按量充值（月约 ¥6）

## 已知风险与对策

- 红狐停服/涨价风险 → 调用集中在 fetch_hot.py 一处，可整体换源
- 榜单混泛娱乐内容 → rules.md 已写筛选要求，AI 生成时过滤
- GitHub Pages 未配置时，飞书卡片会提示本地查看
