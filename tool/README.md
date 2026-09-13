# 有词儿念念 · 选题日报系统（redbookbot）

每天自动产出 10 个选题的日报工具：拉取红狐爆款榜单 → AI 按规则生成选题 →
渲染 HTML 日报 → 自动推送 GitHub Pages + 飞书群。

**日常使用：双击 `一键启动.cmd` → 浏览器自动打开控制台 [http://127.0.0.1:8932/](http://127.0.0.1:8932/) → 页面上点按钮执行。**

## 当前状态

- [x] 红狐数据源验证通过（数据真实、字段完整、T+1 口径，key 已配置）
- [x] GitHub 推送已配置（Fine-grained token，Contents 读写）
- [x] 飞书群机器人已配置（webhook 卡片推送）
- [x] 网页控制台：一键执行全流程 / 规则在线编辑 / 凭据脱敏管理
- [x] 第一期日报已产出（2026-09-13，md + html，含 19 个可点击参考帖）
- [ ] **待办：控制台"AI 模型"卡填 LLM key（智谱/DeepSeek 等 OpenAI 兼容接口）**
- [ ] 可选：每日定时（Windows 任务计划每天 19:30 后自动跑全流程）

## 控制台功能（http://127.0.0.1:8932/）

| 区域 | 功能 |
|---|---|
| 执行日报 | ① 拉取榜单 / ② AI 生成 / ③ 渲染 HTML / ④ 推送 / 🚀 一键全流程，带实时终端输出 |
| 选题规则 | rules.md 在线编辑，保存自动备份旧版到 backups/（留 20 份），下次生成即生效 |
| 红狐数据源 | API key 管理 + 测试连接（真实调一次榜单接口） |
| AI 模型 | OpenAI 兼容接口配置（智谱 `glm-4.7` / `glm-4-flash`，DeepSeek 等）+ 测试连接 |
| GitHub | token 管理、一键建仓+开 Pages（Fine-grained token 需手动建仓） |
| 飞书 | webhook 管理 + 发送测试消息 |

所有凭据在页面上**脱敏显示**（如 `ak_609****4c76`），保存时占位符/留空不会覆盖原值。

## 每日流程

**网页方式（推荐）**：双击 `一键启动.cmd` → 控制台点 🚀 一键执行全流程。

**命令行方式（备用）**：

```bash
cd /d/Backup/redbookbot
python fetch_hot.py                                # 1. 拉昨日榜单（职业发展+学习教育）
python generate_report.py                          # 2. LLM 按 rules.md 生成 daily/日期.md
python build_report.py daily/日期.md               # 3. 渲染 HTML（参考帖转可点击按钮）
python push_report.py daily/日期 --summary "主打话题"  # 4. 推 GitHub Pages + 飞书卡片
```

## 数据与产物

| 位置 | 内容 |
|---|---|
| `data/日期/` | 红狐榜单原始 JSON（每分类 每日/七日 各 50 条） |
| `daily/` | 日报产物（md + html），HTML 内小红书链接一键直达原帖 |
| `backups/` | 规则文件历史版本（自动） |
| `history.md` | 已出题目清单（AI 去重用，每期自动追加） |

## 文件说明

| 文件 | 作用 |
|---|---|
| `一键启动.cmd` | 双击启动：自动拉起控制台服务 + 打开浏览器（GBK 编码，勿转 UTF-8） |
| `config_server.py` | 控制台服务（执行/规则/配置/测试，仅绑定 127.0.0.1） |
| `fetch_hot.py` | 拉取红狐每日/七日爆款榜单 |
| `generate_report.py` | LLM 生成日报（rules.md + 历史去重 + 榜单 top80 → 10 题） |
| `build_report.py` | daily md → HTML（移动端适配，小红书链接转按钮） |
| `push_report.py` | 推送 GitHub（Contents API）+ 飞书卡片（按业务码判成败） |
| `rules.md` | IP 宪法 + 选题规则（人设/主航道/模板库/禁忌/日报格式） |
| `verify_redfox.py` | 红狐数据质量验证脚本（一次性，留存备用） |

## 红狐 API 摘要

| 接口 | 用途 | 价格 |
|---|---|---|
| GET /story/api/cozeSkill/getXhsCozeSkillDataOne | 每日爆款 TOP50 | ¥0.03/次起 |
| GET /story/api/cozeSkill/getXhsCozeSkillDataSeven | 七日爆款 TOP50 | ¥0.03/次起 |
| POST /story/api/xhsUser/queryWorkDetail | 作品详情(完整正文) | ¥0.02/次起 |

- 鉴权 REDFOX_API_KEY；T+1（每天 19:00 更新"昨日"榜单）
- 每天成本约 0.06~0.1 积分，月约 ¥6；互动数为"4w+"式模糊值
- key 统一存 push_config.json（兼容 api_key.txt / 环境变量）

## 安全须知

- `push_config.json`（GitHub token / 飞书 webhook / LLM key）和 `api_key.txt`（红狐 key）
  **永不提交**，已列入 .gitignore；本仓库只同步工具代码，不含任何凭据与数据
- 控制台仅绑定 127.0.0.1，只有本机可访问

## 已知风险与对策

- 红狐停服/涨价 → 调用集中在 fetch_hot.py，可整体换数据源
- 榜单混泛娱乐内容 → rules.md 已写筛选要求，生成时过滤
- 生成质量依赖 LLM → 换模型只改控制台"模型名"一格；glm-5.3 系列生成慢（思考模式）属正常
