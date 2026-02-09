[English](README.md) | 中文

# ArxivPaper for LLM

ArxivPaper for LLM 是一个面向研究/工程团队的 arXiv 论文自动化筛选与速读流水线：
它会在指定时间窗口内从 arXiv 拉取论文，先进行去重，再用 LLM 对每篇论文做“主题相关性”评分并按阈值过滤；随后自动下载 PDF、生成预览页，并基于预览内容识别作者机构以筛出“大机构论文”。对入选论文会进一步做全文解析与中文摘要生成，同时输出“论文封面 + 结果图摘要页”（与封面同尺寸的多页 PNG）以便快速浏览，最后将 PDF/摘要/图片等产物按论文归档收集；Zotero 推送仅作为可选的最后一步。

最终产出两类结果：

  当日汇总文件（核心产物）：把当天精选论文的摘要聚合成一份可直接阅读的文本报告（用于每天快速扫读）。

  单篇论文材料包（可选但默认会生成）：PDF、中文摘要/压缩摘要、机构信息、结果图摘要页等落盘，便于回溯与精读。

Zotero 推送只是可选的最后一步，不影响上述汇总文件的生成。

> README 结构：
>
> 1. 配置准备 2) 运行指令 3) 项目结构 4) 代码流程（按执行顺序）

---

## 1. 配置准备

只需要改：`config/config.py`。

### 1.1 必填

* MinerU Token（`minerU_Token`）：PDF → Markdown 解析；在 `https://mineru.net/apiManage/token` 创建
* DashScope Key（`qwen_api_key`）：机构识别 + 摘要生成；在 `https://bailian.console.aliyun.com/?spm=a2c4g.11186623.0.0.519511fceUTPZn&tab=model#/api-key` 创建


### 1.2 模型与提示词（每项含义）

| 配置项                           | 作用脚本                | 含义                                   |
| ----------------------------- | ------------------- | ------------------------------------ |
| `theme_select_base_url`       | `llm_select_theme.py` | 主题评分模型的 OpenAI 兼容 base_url           |
| `theme_select_model`          | `llm_select_theme.py` | 主题评分模型名称                             |
| `theme_select_max_tokens`     | `llm_select_theme.py` | 主题评分输出 token 上限                      |
| `theme_select_temperature`    | `llm_select_theme.py` | 主题评分采样温度                             |
| `theme_select_concurrency`    | `llm_select_theme.py` | 主题评分并发数（线程数）                         |
| `theme_select_system_prompt`  | `llm_select_theme.py` | 主题评分系统提示词（要求输出 0~1 分数）               |
| `org_base_url`                | `pdf_info.py`       | 机构识别模型的 OpenAI 兼容 base_url           |
| `org_model`                   | `pdf_info.py`       | 机构识别模型名称                             |
| `org_max_tokens`              | `pdf_info.py`       | 机构识别输出 token 上限                      |
| `org_temperature`             | `pdf_info.py`       | 机构识别采样温度                             |
| `pdf_info_system_prompt`      | `pdf_info.py`       | 机构识别 + 是否大机构 + 生成短摘要的规则（要求输出 JSON）   |
| `summary_base_url`            | `paper_summary.py`  | 摘要模型的 OpenAI 兼容 base_url             |
| `summary_model`               | `paper_summary.py`  | 摘要模型名称                               |
| `summary_max_tokens`          | `paper_summary.py`  | 摘要输出 token 上限                        |
| `summary_temperature`         | `paper_summary.py`  | 摘要采样温度                               |
| `summary_input_hard_limit`    | `paper_summary.py`  | 输入硬上限（用于裁剪预算）                        |
| `summary_input_safety_margin` | `paper_summary.py`  | 安全边距（预留给提示词/结构）                      |
| `summary_concurrency`         | `paper_summary.py`  | 摘要并发数（线程数）                           |
| `summary_example`             | `config.py`         | 摘要提示词中的示例文本                          |
| `system_prompt`               | `paper_summary.py`  | 摘要系统提示词（含示例，决定结构/风格）                 |

---

## 2. 安装与运行

### 2.1 安装依赖

```bash
pip install -r requirements.txt
```

> 建议使用虚拟环境（如 `python -m venv .venv && source .venv/bin/activate` 或在 Windows 下 `.\.venv\Scripts\activate`）。

### 2.2 运行指令

#### 2.2.1 直接运行（不带参数）

```bash
python app.py 
```

#### 2.2.2 带参数运行（示例 2 个）

```bash
# 示例1：自然语言查询 + 指定时区
python app.py default --query "LLM alignment" --anchor-tz Asia/Shanghai

```

> pipeline 名称（如 `default/daily`）之后的参数，**只会传给第一步** `Controller/arxiv_search04.py`。

### 可调参数（命令行）

| 参数                |                  默认值 | 说明                                                      |
| ----------------- | -------------------: | ------------------------------------------------------- |
| `--query`         |                `""` | 自然语言或高级表达式（ti:/abs:/AND/...）                          |
| `--categories`    | `SEARCH_CATEGORIES` | 逗号分隔分类列表                                               |
| `--start`         |                `""` | UTC 起始（YYYY-MM-DD 或 ISO8601）                           |
| `--end`           |                `""` | UTC 结束（右开；若为日期则自动 +1 天）                               |
| `--anchor-tz`     |   `Asia/Shanghai`   | 以该时区的当天 00:00 作为 end                                  |
| `--days`          |                 `1` | 未提供 start/end 时，从锚定 00:00 往前推 days 天                  |
| `--anchor-date`   |                `""` | 锚定日期（YYYY-MM-DD）                                      |
| `--last-hours`    |              `None` | 未提供 start/end 时使用 now_utc - last_hours 到 now_utc（互斥） |
| `--page-size`     |  `PAGE_SIZE_DEFAULT` | 每页拉取数量（1~2000）                                        |
| `--max-papers`    | `MAX_PAPERS_DEFAULT` | 最多保留论文数量                                              |
| `--sleep`         |      `SLEEP_DEFAULT` | 翻页间隔（秒）                                               |
| `--use-proxy`     |  `USE_PROXY_DEFAULT` | 允许从环境变量读取代理                                           |
| `--user-agent`    |      `REQUESTS_UA` | User-Agent                                              |
| `--out`           |                 （预留） | 脚本参数存在，但当前版本未实际生效                                    |

---

## 3. 项目结构

```markdown
. 📂 ArxivPaper                         # 项目根目录
├── 📄 README.md                        # 当前说明文档（主 README）
├── 📄 app.py                           # 主流程：按 pipeline 调用 Controller 下各步骤
├── 📄 pdf_download.log                 # pdf_download.py 的运行日志
├── 📄 readmePrinceple.md               # 撰写 README 的约定与原则记录
├── 📂 Controller/                      # 核心步骤脚本目录
│  ├── 📂 __pycache__/                  # Controller 下的 Python 字节码缓存
│  ├── 📄 arxiv_search04.py             # Step1：arXiv 拉取（支持查询与时间窗口）
│  ├── 📄 llm_select_theme.py           # Step2：LLM 主题相关性评分
│  ├── 📄 paper_theme_filter.py         # Step3：按相关性分数过滤
│  ├── 📄 http_session.py               # 统一的 requests Session 构建与重试逻辑
│  ├── 📄 instutions_filter.py          # Step6：基于机构信息筛选出“大机构论文”
│  ├── 📄 paperList_remove_duplications.py  # Step1.1：去重并记录历史处理论文
│  ├── 📄 paper_summary.py              # Step11：根据 MinerU 全文生成中文摘要
│  ├── 📄 pdf_download.py               # Step4：根据清单下载原始 PDF（按日期分子目录）
│  ├── 📄 pdf_info.py                   # Step7：调用大模型解析机构信息与摘要要点
│  ├── 📄 pdf_split.py                  # Step5：截取前若干页生成预览 PDF（按日期分子目录）
│  ├── 📄 pdfsplite_to_minerU.py        # Step6：预览 PDF → MinerU 解析为 Markdown
│  ├── 📄 selectedpaper_to_mineru.py    # Step10：精选 PDF → MinerU 全文解析
│  ├── 📄 selectpaper.py                # Step9：按“大机构清单”迁移精选 PDF
│  ├── 📄 summary_limit.py              # Step11.5：摘要分块压缩
│  ├── 📄 zotero_push.py                # Step12：导入精选论文到 Zotero
├── 📂 config/                          # 集中配置目录
│  ├── 📂 __pycache__/                  # config 下的字节码缓存
│  ├── 📄 config copy.py                # 早期配置备份（保留历史用）
│  ├── 📄 paperList.json                # 全局“已处理论文列表”（去重用）
├── 📂 data/                            # 运行数据目录（按日期分子目录）
│  ├── 📂 arxivList/                    # 每日候选清单（md/json）
│  │  ├── 📂 md/                        # 候选清单 Markdown
│  │  └── 📂 json/                      # 候选清单 JSON
│  ├── 📂 paperList_remove_duplications/ # 去重后的候选清单 JSON
│  ├── 📂 llm_select_theme/             # LLM 评分后的清单 JSON
│  ├── 📂 paper_theme_filter/           # 主题过滤后的清单 JSON
│  ├── 📂 raw_pdf/                      # 原始 PDF + manifest
│  ├── 📂 preview_pdf/                  # 预览 PDF + manifest
│  ├── 📂 preview_pdf_to_mineru/        # 预览 MinerU md + manifest
│  ├── 📂 pdf_info/                     # 机构识别 JSON
│  ├── 📂 instutions_filter/            # 大机构清单 JSON
│  ├── 📂 selectedpaper/                # 精选 PDF + manifest
│  ├── 📂 selectedpaper_to_mineru/      # 精选 MinerU md + manifest
│  ├── 📂 paper_summary/                # 摘要输出
│  ├── 📂 summary_limit/                # 摘要压缩输出
│  ├── 📂 select_image/                 # 结果图摘要页 PNG + report
│  └── 📂 file_collect/                 # 文件收集输出（按论文ID组织）
├── 📂 logs/                            # 运行日志目录（按日期分子目录）
└── 📂 reference/                       # 参考项目与示例代码（旧仓库拷贝）
```

---

## 4. 代码流程（按执行文件顺序）

**app.py 默认流程**

- 1) arXiv 拉取与窗口过滤（`arxiv_search04.py`）
- 2) 去重并记录处理过的论文（`paperList_remove_duplications.py`）
- 3) LLM 主题相关性评分（`llm_select_theme.py`）
- 4) 主题相关性过滤（`paper_theme_filter.py`）
- 5) 下载原始 PDF（`pdf_download.py`）
- 5) 切预览页（`pdf_split.py`）
- 6) 预览 PDF → MinerU 解析（`pdfsplite_to_minerU.py`）
- 7) 机构识别与结构化信息（`pdf_info.py`）
- 8) 生成“大机构 PDF 清单”（`instutions_filter.py`）
- 9) 迁移精选 PDF（`selectpaper.py`）
- 10) 精选 PDF → MinerU 全文解析（`selectedpaper_to_mineru.py`）
- 11) 生成中文摘要（`paper_summary.py`）
- 12) 摘要分块压缩（`summary_limit.py`）
- 13) 结果图摘要页（`select_image.py`）
- 14) 文件收集（`file_collect.py`）
- 15) 导入精选论文到 Zotero（`zotero_push.py`）

### 0) 总编排（`app.py`）

**输入**：pipeline 名称与额外参数（`app.py`）

**输出**：依次执行各步骤脚本（`Controller/*.py`，见下文步骤 1~10）

**逻辑流程**

* 读取 pipeline（默认 `default`）
* 按 pipeline 顺序 `subprocess.run()` 执行步骤
* pipeline 之后的参数仅转发给 Step1（`arxiv_search04.py`）

---

### 1) arXiv 拉取与窗口过滤（`Controller/arxiv_search04.py`）

**输入**

* arXiv 检索条件（`SEARCH_CATEGORIES` + `--query`）
* 时间窗口与规模（`--start/--end/--anchor-*` + `PAGE_SIZE_DEFAULT/MAX_PAPERS_DEFAULT/SLEEP_DEFAULT`）

**输出**

* 当天候选清单（`data/arxivList/md/<date>.md`）
* 当天候选清单 JSON（`data/arxivList/json/<date>.json`）

**逻辑流程**

* 计算 UTC 窗口（`submittedDate:[START TO END]`）
* 构建 query：`(cat:... OR ...) AND (all:... OR 高级表达式) AND submittedDate`
* `submittedDate desc` 分页拉取
* 仅按时间窗口过滤（不做正则计分/分桶）
* 输出 Markdown：写窗口信息与统计，按列表顺序输出

---

### 2) 去重并记录处理过的论文（`Controller/paperList_remove_duplications.py`）

**输入**

* 当天候选清单（`data/arxivList/json/<date>.json`，默认选最新一份）
* 历史处理记录（`config/paperList.json`，首次运行可为空）

**输出**

* 更新后的处理记录（`config/paperList.json`，JSON 数组）
* 去重后的清单（`data/paperList_remove_duplications/<date>.json`）

  * 每条记录字段：
    * `title`：论文标题
    * `source`：论文编号（如 `2601.02454`）
    * `writing_datetime`：写入记录的时间（UTC ISO 格式）

**逻辑流程**

* 从 `config/paperList.json` 读取已有记录，构造去重键集合（`(title, source)`）
* 解析当天候选清单 json 中的论文条目（`papers` 数组）
* 对每条 `title + source`：
  * 若在历史记录中已存在，则视为“以前处理过”，仅跳过本次写入
  * 若不存在，则认为是首次处理：
    * 追加一条 `{title, source, writing_datetime}` 到 `paperList.json`

* 根据“未重复论文列表”重写一份去重后的 json：
  * 复用输入的元信息结构（例如窗口、统计等）
  * `papers` 仅保留未在历史记录中出现过的条目

> 后续若希望下载步骤只基于“未处理论文”的 json，可以通过 `--json data/paperList_remove_duplications/<date>.json` 方式显式传给 `Controller/pdf_download.py`。

> 注意：当前版本只负责维护全局“处理过的论文列表”，不会修改原始的 `data/arxivList/md/*.md` 内容。后续如果需要在下载前直接改写 md（删除重复论文条目），可以在此基础上再扩展。

---

### 3) LLM 主题相关性评分（`Controller/llm_select_theme.py`）

**输入**

* 去重后的清单（`data/paperList_remove_duplications/<date>.json`）
* 评分模型配置（`theme_select_*`）

**输出**

* 评分清单（`data/llm_select_theme/<date>.json`，追加 `theme_relevant_score`）

**逻辑流程**

* 解析每条论文的标题与摘要
* 并发调用模型获取 0~1 分
* 写回原始结构并追加分数字段

---

### 4) 主题相关性过滤（`Controller/paper_theme_filter.py`）

**输入**

* 评分清单（`data/llm_select_theme/<date>.json`）

**输出**

* 过滤后清单（`data/paper_theme_filter/<date>.json`）

**逻辑流程**

* 解析 `theme_relevant_score`
* 仅保留 `score >= threshold` 的条目（保留头部）

---

### 5) 下载原始 PDF（`Controller/pdf_download.py`）

**输入**

* 候选清单（`data/paper_theme_filter/<date>.json`）

**输出**

* 原始 PDF（`data/raw_pdf/<date>/<arxiv_id>.pdf`）
* 下载 manifest（`data/raw_pdf/<date>/_manifest.json`）

**逻辑流程**

* 从清单解析 arXiv id
* 若本地已存在且文件头为 `%PDF-`：认为有效并跳过
* 否则下载（含重试），写入临时 `.part`，通过基础校验后原子替换为 `.pdf`

---

### 6) 切预览页（`Controller/pdf_split.py`）

**输入**

* 原始 PDF（`data/raw_pdf/<date>/<arxiv_id>.pdf`）

**输出**

* 预览 PDF（前 2 页，`data/preview_pdf/<date>/<arxiv_id>.pdf`）
* 切分 manifest（`data/preview_pdf/<date>/_manifest.json`）

**逻辑流程**

* 对每篇 PDF 截取前 2 页并写入预览目录；已存在则跳过

---

### 7) 预览 PDF → MinerU 解析（`Controller/pdfsplite_to_minerU.py`）

**输入**

* 预览 PDF / manifest（`data/preview_pdf/<date>/*.pdf` / `data/preview_pdf/<date>/_manifest.json`）
* MinerU 凭证（`minerU_Token`）

**输出**

* 预览页 Markdown（`data/preview_pdf_to_mineru/<date>/<arxiv_id>.md`）
* 解析 manifest（`data/preview_pdf_to_mineru/<date>/_manifest.json`）

**逻辑流程**

* MinerU 批处理：申请上传 URL → PUT 上传 → 轮询结果 → 下载 zip → 提取 md
* 若 `out/<id>.md` 已存在则跳过该篇

---

### 8) 机构识别与结构化信息（`Controller/pdf_info.py`）

**输入**

* 预览页文本（MinerU md，`data/preview_pdf_to_mineru/<date>/*.md`）
* 清单元信息（标题/发布时间，`data/paper_theme_filter/<date>.json`）
* 机构识别模型与提示词（`org_*`, `pdf_info_system_prompt`）

**输出**

* 结构化结果（`data/pdf_info/<date>.json`，字段含 `instution/is_large/abstract`）

**逻辑流程**

* 对每篇预览 md 并发调用模型（默认并发=8，可在 `config/config.py` 配置）
* 合并 title/published/arxiv_id 等元信息，追加写入；已存在则按 arxiv_id 去重跳过

---

### 9) 生成“大机构 PDF 清单”（`Controller/instutions_filter.py`）

**输入**

* 结构化结果（`data/pdf_info/<date>.json`）

**输出**

* 仅包含“大机构论文”的 PDF 清单（`data/instutions_filter/<date>/<date>.json`）

**逻辑流程**

* 过滤 `is_large == true` 的条目并写出（供后续迁移 PDF）

---

### 10) 迁移精选 PDF（`Controller/selectpaper.py`）

**输入**

* 大机构 PDF 清单（`data/instutions_filter/<date>/<date>.json`）
* 原始 PDF（`data/raw_pdf/<arxiv_id>.pdf`）

**输出**

* 精选 PDF（`data/selectedpaper/<date>/<arxiv_id>.pdf`）
* 迁移 manifest（`data/selectedpaper/<date>/_manifest.json`）

**逻辑流程**

* 从清单解析 arxiv_id，使用 `shutil.move` 将 PDF 移到精选目录（源文件会消失）

---

### 11) 精选 PDF → MinerU 全文解析（`Controller/selectedpaper_to_mineru.py`）

**输入**

* 精选 PDF / manifest（`data/selectedpaper/<date>/*.pdf` / `data/selectedpaper/<date>/_manifest.json`）
* MinerU 凭证（`minerU_Token`）

**输出**

* 全文 Markdown（`data/selectedpaper_to_mineru/<date>/<arxiv_id>.md`）
* 解析 manifest（`data/selectedpaper_to_mineru/<date>/_manifest.json`）

**逻辑流程**

* MinerU 批处理解析全文；若 `out/<id>.md` 已存在则跳过

---

### 12) 生成中文摘要（`Controller/paper_summary.py`）

**输入**

* 全文文本（MinerU md，`data/selectedpaper_to_mineru/<date>/*.md`）
* 摘要模型与提示词（`summary_*`, `system_prompt`）

**输出**

* 单篇摘要（`data/paper_summary/single/<date>/<arxiv_id>.md`）
* 当日汇总（`data/paper_summary/gather/<date>/<date>.txt`）

**逻辑流程**

* 按输入预算裁剪全文 md 后并发调用摘要模型
* 单篇落盘后拼接生成当日汇总

---

### 13) 摘要分块压缩（`Controller/summary_limit.py`）

**输入**

* 单篇摘要（`data/paper_summary/single/<date>/<arxiv_id>.md`）
* 压缩模型与提示词（`summary_limit_*`, `summary_limit_prompt_*`）

**输出**

* 单篇压缩摘要（`data/summary_limit/single/<date>/<arxiv_id>.md`）
* 当日汇总（`data/summary_limit/gather/<date>/<date>.txt`）

**逻辑流程**

* 若整体长度 ≤ 950（去空白字符计）则直接复制
* 否则按标题分块：文章简介 / 重点思路 / 分析总结 / 个人观点
* 超出分块上限则按对应提示词改写并复检
* 拼接回原结构并生成汇总
* 使用 `pdf_info/<date>.json` 覆盖标题与来源
* 文章简介/重点思路/分析总结最多 4 条，强制 `🔸` 开头；个人观点保留 1–2 句

---

### 14) 结果图摘要页（`Controller/select_image.py`）

**目标**：把论文第 1 页渲染为封面，并从 MinerU 输出中筛选"结果相关"的图，排版成与封面**同宽高**的多页 PNG（便于快速浏览）。

**输入**

- 精选 PDF（`data/selectedpaper/<date>/<arxiv_id>.pdf`）
- 精选 MinerU 输出（`data/selectedpaper_to_mineru/<date>/<arxiv_id>/...`，含 `*.md` / 图片 / `*_content_list.json`）

**输出**

- 结果图摘要页（`data/select_image/<date>/<arxiv_id>/01.png`：论文第 1 页封面）
- 结果图摘要页（`data/select_image/<date>/<arxiv_id>/02.png...`：结果图摘要页，与封面同尺寸）
- 筛选报告（`data/select_image/<date>/<arxiv_id>/report.json`：筛选/分组/跳过统计）

**逻辑流程**

- 从精选 PDF 提取第 1 页作为封面
- 从 MinerU 输出中筛选"结果相关"的图片（基于内容列表与关键词匹配）
- 按指定布局引擎（HTML/CSS 或 ReportLab）排版成多页 PNG
- 生成筛选统计报告

**运行示例**

```bash
# 方案A：HTML/CSS 排版 → Chromium 打印 PDF → 渲染成 PNG（更稳定）
python Controller/select_image.py --layout-engine html
```

> 方案A 需要安装 Playwright + Chromium：
>
> ```bash
> pip install playwright
> python -m playwright install chromium
> ```
>
> 若未安装依赖，会自动回退到旧的 PIL 拼版（`--layout-engine pil`）。

```bash
# 方案B：确定性布局（Justified rows）→ ReportLab 生成 PDF → 渲染成 PNG
python Controller/select_image.py --layout-engine reportlab
```

> 方案B 需要安装 ReportLab：
>
> ```bash
> pip install reportlab
> ```

---

### 15) 文件收集（`Controller/file_collect.py`）

**输入**

- 精选 PDF（`data/selectedpaper/<date>/<arxiv_id>.pdf`）
- 中文摘要（`data/paper_summary/single/<date>/<arxiv_id>.md`）
- 压缩摘要（`data/summary_limit/single/<date>/<arxiv_id>.md`）
- 机构信息（`data/pdf_info/<date>.json`）
- 结果图摘要页（`data/select_image/<date>/<arxiv_id>/*.png`）

**输出**

- 收集后的文件目录（`data/file_collect/<date>/<arxiv_id>/`）
  - `{arxiv_id}.pdf`：精选 PDF
  - `{arxiv_id}_summary.md`：中文摘要
  - `{arxiv_id}_limit.md`：压缩摘要
  - `pdf_info.json`：机构信息 JSON
  - `image/01.png, 02.png...`：结果图摘要页（0X.png 格式）

**逻辑流程**

- 根据日期定位精选 PDF 与相关文件目录
- 为每篇论文创建独立的输出目录（`data/file_collect/<date>/<arxiv_id>/`）
- 复制 PDF、摘要文件、机构信息 JSON 到对应目录
- 复制结果图摘要页（匹配 `0[0-9].png` 格式）到 `image/` 子目录
- 记录缺失文件并输出统计信息

**运行示例**

```bash
# 使用默认日期（今天或最新可用日期）
python Controller/file_collect.py

# 指定日期
python Controller/file_collect.py --date 2025-01-26
```

---

### 16) 导入精选论文到 Zotero（`Controller/zotero_push.py`）

**输入**

* 精选 PDF（`data/selectedpaper/<date>/*.pdf`）
* 中文摘要（`data/paper_summary/single/<date>/*.md`）

**输出**

* Zotero 中创建的条目及附件（本地无额外文件输出）

**逻辑流程**

* 根据日期定位精选 PDF 与摘要目录
* 为每篇论文构造 Zotero item（标题、摘要、arXiv 链接等元信息）
* 通过 Zotero Connector 的 `/connector/saveItems` 创建条目
* 再调用 `/connector/saveAttachment` 上传对应的 PDF/MD/summary 附件
* 终端以单行进度方式展示导入状态，并在最后输出汇总统计

