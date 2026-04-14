# SKILL.md — eco-acquire

> 经济学期刊文献智能获取与分析 Skill v2.2
> License: MIT | 适用于 AI Agent 调用

---

## 概述

eco-acquire 是一个自动化经济学文献检索工具，支持从 CNKI（知网）搜索、下载、分析经济学核心期刊文献，并在 CNKI 不可用时自动切换到 Google Scholar。

**核心能力**：搜索 → 下载 PDF → 提取研究结论 → 输出结构化报告

## 何时触发

当用户的请求涉及以下意图时，加载此 Skill：

- "搜索/查找/获取 文献/论文/文章"
- "下载 XX 期刊的文章"
- "找 XX 关于 XX 的研究"
- "帮我搜集 XX 领域的文献"
- 提及具体经济学期刊名称
- 用户提供文献列表/参考文献要求 AI 获取

## 支持期刊

经济研究 | 经济学（季刊） | 中国工业经济 | 世界经济 | 金融研究
管理世界 | 数量经济技术经济研究 | 财贸经济 | 中国农村经济 | 国际金融研究

---

## 两种调用模式

### 模式一：直接搜索（简单场景）

用户明确知道要搜什么关键词时，直接调用。

### 模式二：AI Planning 模式（推荐，精准场景）

**当用户要求获取多篇特定文献、或基于研究主题收集文献时，必须使用此模式。**

#### 工作流程

```
用户请求 → AI 分析意图 → AI 生成文献清单 JSON → skill 执行清单 → 返回结果
```

#### Step 1：AI 分析用户意图

AI 应理解用户的研究需求，识别：
- 需要哪些具体文献（标题、作者、期刊、年份）
- 搜索策略（每篇文献的最佳搜索方式）
- 文献优先级和备注

#### Step 2：AI 生成文献清单 JSON

AI 应创建如下格式的 JSON 文件：

```json
{
  "task_name": "FDI与数字经济文献收集",
  "papers": [
    {
      "title": "数字经济对全要素生产率的影响",
      "authors": ["赵涛", "张智", "梁上坤"],
      "journal": "中国工业经济",
      "year": 2020,
      "doi": "",
      "strategy": "title_author",
      "search_text": "数字经济对全要素生产率的影响",
      "notes": "经典数字经济TFP论文"
    },
    {
      "title": "Digitalization and the labor market",
      "authors": ["Brynjolfsson"],
      "journal": "",
      "year": 2023,
      "doi": "10.1093/restud/rdad015",
      "strategy": "keyword",
      "search_text": "digitalization labor market Brynjolfsson",
      "notes": "英文文献，用关键词搜索"
    }
  ]
}
```

#### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `task_name` | 是 | 任务名称（用于创建输出文件夹） |
| `papers[].title` | 是* | 目标文献标题（strategy 为 keyword 时可选） |
| `papers[].authors` | 否 | 作者列表 |
| `papers[].journal` | 否 | 期刊名称 |
| `papers[].year` | 否 | 发表年份 |
| `papers[].doi` | 否 | DOI 号（如有） |
| `papers[].strategy` | 是 | 搜索策略（见下表） |
| `papers[].search_text` | 条件必填 | 搜索时输入的文本（strategy=title 时默认用 title） |
| `papers[].notes` | 否 | 备注（仅用于记录，不影响搜索） |

#### 搜索策略 (strategy)

| 策略 | 适用场景 | 说明 |
|------|---------|------|
| `title` | 有标题但信息不全 | 仅用标题搜索，模糊匹配 |
| `title_author` | 标题+作者 | 用标题搜索，客户端验证作者匹配 |
| `title_journal` | 标题+期刊 | 用标题搜索，客户端验证期刊匹配 |
| `journal_browse` | 按期刊浏览 | 搜索指定期刊+年份的所有文章 |
| `keyword` | 关键词广泛搜索 | 用关键词搜索，返回前5条，不要求标题匹配 |
| `doi` | 有 DOI 号 | 记录 DOI，后续处理 |

#### search_text 构造技巧（重要！）

**CNKI 搜索结果不保证按相关度排序**，搜索词的质量直接影响命中率。

✅ **好的 search_text 示例**：
```json
"search_text": "数字经济 全要素生产率 赵涛"
```
用标题中**最有区分度的2-4个核心词** + **第一作者姓氏**，空格分隔。

❌ **不好的 search_text 示例**：
```json
"search_text": "数字经济对全要素生产率的影响"
```
完整标题作为搜索词可能搜不到目标（CNKI 排序问题），且容易匹配到标题相似的其他论文。

**构造规则**：
1. 从标题提取2-4个核心名词/动词（去掉"对"、"的"、"与"、"研究"等虚词）
2. 如果有作者，加上第一作者姓名
3. 如果有期刊，考虑加上期刊名
4. 用空格分隔（CNKI 会按 AND 逻辑处理）
5. 控制在10个字以内

#### Step 3：调用 skill 执行

```bash
cd {SKILL_DIR}
python run.py --batch /path/to/literature_list.json --connect 9222
```

#### Step 4：处理结果

读取返回的 `task_report.json`，检查每篇文献的执行状态：

```json
{
  "papers": [
    {
      "input_title": "数字经济对全要素生产率的影响",
      "strategy": "title_author",
      "status": "found",
      "match_score": 0.95,
      "downloaded": true,
      "article": { "title": "...", "authors": "...", ... }
    }
  ]
}
```

每篇文献的 `status` 值：
- `found` — 成功找到并匹配
- `not_found` — 搜索无结果或相似度过低
- `error` — 执行过程出错（查看 `message` 字段）
- `skip_search` — 跳过搜索（如 DOI 模式）

---

## 参数说明（直接搜索模式）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--keywords` | str/list | 与其他至少一项 | 搜索关键词，可多个 |
| `--batch` | str | 否 | AI Planning 模式，指定文献清单 JSON 文件 |
| `--journal` | str | 同上 | 限定期刊名称 |
| `--author` | str | 同上 | 按作者姓名筛选 |
| `--exact-title` | str | 同上 | 精确文章标题（定位单篇） |
| `--year-start` | int | 否 | 起始年份（含） |
| `--year-end` | int | 否 | 结束年份（含） |
| `--max-results` | int | 否 | 最大结果数（默认10） |
| `--browser` | str | 否 | auto/chrome/edge/firefox |
| `--connect` | int | 否 | 连接已打开的浏览器调试端口 |
| `--headless` | flag | 否 | 无头模式 |
| `--no-download` | flag | 否 | 仅搜索不下载 |
| `--no-conclusion` | flag | 否 | 不提取结论 |
| `--task-name` | str | 否 | 自定义任务名 |

## 输出说明

### 目录结构

```
~/eco-acquire/outputs/
└── MM-DD-任务名/
    ├── task_report.json       # 完整JSON报告（AI应读取此文件）
    ├── pdfs/                  # PDF文献
    └── report/                # 分析报告
        ├── MM-DD-任务名_results.md
        └── MM-DD-任务名_results.csv
```

### AI Agent 应如何处理结果

1. 读取 `task_report.json`
2. 检查 `status`：若 `error` → 向用户报告 `error` 字段内容
3. 若 batch 模式 → 逐篇检查 `papers[].status`，告知用户哪些找到、哪些没找到
4. 若 `completed` → 从 `articles` 提取标题、作者、结论，格式化展示
5. 若 PDF 下载失败数 > 0 → 告知用户"部分文献受版权保护无法自动下载"

## 容错机制

```
CNKI搜索 ──失败──→ Google Scholar搜索
    │                       │
    ├─成功─→ 继续          ├─成功─→ 继续
    │                       │
CNKI下载 ──失败──→ Sci-Hub → Unpaywall → Scholar PDF
```

每一步失败都会记录到 report 中，不会中断整个流程。

## 推荐使用方式

```bash
# 1. 用户启动 Edge（一次性）
msedge --remote-debugging-port=9222

# 2. 在 Edge 中手动通过 CNKI 验证码（一次性）

# 3. 之后所有操作都走 --connect，不再弹验证码
python run.py --batch literature_list.json --connect 9222
python run.py --keywords "FDI" --connect 9222
```

## 环境要求

- Python >= 3.8
- Selenium >= 4.6（自动管理浏览器驱动）
- 系统需安装 Chrome / Edge / Firefox 任一浏览器
- CNKI 不可达时自动切换 Google Scholar，**不强制要求知网权限**

## 前置检查

AI Agent 在调用前应确认：
1. `python run.py --list-journals` 能正常输出期刊列表
2. 若报权限错误，检查 `~/eco-acquire/` 目录是否可写

## 注意事项

- 仅供个人学术研究使用
- 请求间隔 2-5 秒，请勿频繁调用
- AI Planning 模式下，AI 应根据文献信息选择最合适的 strategy
- 客户端模糊匹配的阈值为 0.3（相似度），标题搜索时自动启用
