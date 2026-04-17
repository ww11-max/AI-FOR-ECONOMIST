# eco-acquire

> 经济学核心期刊文献智能检索工具 v3.0

基于 Selenium 的 CNKI / Google Scholar 文献检索系统，纯题录模式——只获取元数据，不下载全文 PDF。支持 AI Agent 智能分析用户检索意图，自动生成检索计划并执行。

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Selenium 4](https://img.shields.io/badge/Selenium-4.15+-green.svg)](https://www.selenium.dev/)

## 特性

- **AI 智能分析** — 用户自然语言描述需求，AI 自动生成检索策略（关键词、期刊、年份、搜索模式）
- **纯题录模式** — 获取标题、作者、期刊、年份、摘要、关键词、DOI，不涉及 PDF 下载
- **双源检索** — CNKI 主搜索 + Google Scholar 备用，自动降级
- **批量元数据提取** — 搜索结果自动进详情页提取摘要和关键词
- **跨浏览器** — 自动检测 Chrome / Edge / Firefox，零配置驱动管理
- **连接模式** — 复用用户已登录的浏览器，绕过 CNKI 验证码
- **多格式输出** — Markdown 题录表格 + CSV + JSON

## 支持期刊

在中国知网开放获取的所有期刊文献

> 支持任意 CNKI 收录期刊的检索，以上为内置推荐列表。

## 快速开始

### 安装

```bash
git clone https://github.com/ww11-max/Document-acquisition-tool.git
cd Document-acquisition-tool
pip install -r requirements.txt
```

> **前置条件**：Python 3.9+、Selenium 4.6+、Chrome/Edge/Firefox 任一浏览器。
> Selenium 4.6+ 自动管理浏览器驱动，无需手动安装 chromedriver 等。

### 基本使用

```bash
# 关键词搜索
python run.py --keywords "FDI" --max-results 10

# 指定期刊 + 年份范围
python run.py --keywords "数字经济" --journal "世界经济" --year-start 2023 --year-end 2025

# 精确定位单篇文献
python run.py --exact-title "数字经济对FDI的影响" --author "李四" --journal "金融研究"

# 连接模式（复用已登录的浏览器，推荐）
python run.py --connect 9222 --keywords "绿色金融" --journal "金融研究"

# 批量模式（JSON 检索计划）
python run.py --batch search_plan.json --connect 9222

# 列出支持的期刊
python run.py --list-journals
```

### 连接模式（推荐）

CNKI 有严格的反爬策略，推荐复用已登录的浏览器：

```bash
# 1. 先启动带调试端口的浏览器（以 Edge 为例）
msedge --remote-debugging-port=9222

# 2. 在浏览器中手动登录 CNKI（如果需要下载或查看全文）

# 3. 用 --connect 参数连接
python run.py --connect 9222 --keywords "自贸试验区" --journal "经济研究"
```

### 批量检索 JSON

批量模式支持一次执行多个检索任务：

```json
[
  {
    "keywords": "自贸试验区 企业创新",
    "journal": "世界经济",
    "strategy": "keyword",
    "year_start": 2022,
    "year_end": 2025,
    "max_results": 20
  },
  {
    "title": "数字经济对全要素生产率的影响",
    "author": "张三",
    "journal": "中国工业经济",
    "strategy": "exact",
    "year": 2024
  }
]
```

```bash
python run.py --batch search_plan.json --connect 9222 --year-start 2022 --year-end 2025
```

### Python API

```python
from src.workflow import EcoAcquireWorkflow, setup_logging

setup_logging()
wf = EcoAcquireWorkflow(connect_port=9222)

report = wf.run(
    keywords="FDI",
    journal="世界经济",
    year_start=2023,
    max_results=10,
)
# report["status"]: completed / no_results / error
# report["search_source"]: cnki / google_scholar
# report["articles"]: [{title, authors, journal, year, abstract, keywords, doi, ...}]
```

## 搜索模式

| 参数组合 | 模式 | 说明 |
|---------|------|------|
| `--exact-title` | 精确定位 | 标题 + 作者/期刊/年份 匹配单篇 |
| `--journal`（无关键词） | 期刊导航 | 浏览整本期刊最新目录 |
| `--keywords` + 其他条件 | 高级检索 | CNKI 专业检索 + 客户端过滤 |
| 仅 `--keywords` | 普通搜索 | 全站关键词搜索 |

## 输出

```
~/eco-acquire/                              ← 用户数据目录
└── outputs/
    └── 04-17-世界经济-自贸试验区与企业创新/
        ├── task_report.json                ← 完整 JSON 数据
        └── report/
            └── 04-17-世界经济-自贸试验区与企业创新_results.md  ← 题录表格
```

### 报告示例（Markdown 题录表格）

```markdown
# 检索结果：世界经济-自贸试验区与企业创新

| # | 标题 | 作者 | 期刊 | 年份 | 关键词 |
|---|------|------|------|------|--------|
| 1 | 自贸试验区对企业创新的影响... | 张三, 李四 | 世界经济 | 2023 | 自贸试验区;企业创新... |
| 2 | ... | ... | ... | ... | ... |
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--keywords` | 搜索关键词（可多个） | - |
| `--journal` | 限定期刊名称 | - |
| `--author` | 按作者筛选 | - |
| `--exact-title` | 精确文章标题 | - |
| `--year-start` | 起始年份（含） | - |
| `--year-end` | 结束年份（含） | - |
| `--max-results` | 最大结果数 | 10 |
| `--connect` | 连接已运行浏览器的调试端口 | - |
| `--browser` | 浏览器：auto/chrome/edge/firefox | auto |
| `--task-name` | 自定义任务名 | 自动生成 |
| `--batch` | 批量检索 JSON 文件路径 | - |
| `--no-abstract` | 不提取摘要（仅标题+作者+期刊+年份） | false |
| `--headless` | 无头浏览器模式 | false |

> `--keywords`、`--journal`、`--author`、`--exact-title` 至少提供一个。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ECO_ACQUIRE_HOME` | 用户数据目录 | `~/eco-acquire/` |
| `BROWSER` | 浏览器选择 | `auto` |
| `USE_HEADLESS` | 无头模式 | `false` |
| `MAX_RETRIES` | 最大重试次数 | `3` |

## 项目结构

```
eco-acquire/
├── SKILL.md              # AI Agent Skill 描述
├── README.md             # 本文件
├── LICENSE               # MIT
├── pyproject.toml        # Python 项目配置
├── run.py                # CLI 入口
├── requirements.txt      # 依赖
├── .env.example          # 环境变量模板
├── .gitignore
├── config/
│   ├── __init__.py
│   └── settings.py       # 全局配置（路径、期刊、容错策略）
├── src/
│   ├── __init__.py
│   ├── driver_manager.py # 跨浏览器驱动 + 反检测
│   ├── crawler.py        # CNKI + Google Scholar 检索与元数据提取
│   └── workflow.py       # 工作流引擎
└── scripts/              # 辅助脚本
```

## 反检测机制

- 浏览器指纹伪装（禁用 AutomationControlled）
- JS 属性覆写（navigator.webdriver / chrome / plugins）
- UA 轮换（随机版本号）
- 人类行为模拟（随机滚动、点击）
- 验证码感知（检测"拼图校验"并自动重试）

## 免责声明

- 仅供个人学术研究使用
- 请遵守相关法律法规和网站使用条款
- 本工具仅获取公开的题录信息（标题、摘要等），不涉及全文下载

## License

[MIT](LICENSE)
