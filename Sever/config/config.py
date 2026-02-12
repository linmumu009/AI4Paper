"""arXiv 检索与导出脚本的统一配置
- 修改此文件即可调整查询、分类、输出等行为
- 部分参数可被命令行覆盖（如 --page-size 等）
"""

import os

"""
========================
一、数据与流程基础配置
（检索 → 预处理/筛选 → 下载 → 解析）
========================
"""

# [Controller/arxiv_search.py] arXiv API 基础地址
# 使用 http 可规避部分代理的 TLS 问题；若网络环境稳定也可改为 https
API_URL = "http://export.arxiv.org/api/query"

# [Controller/arxiv_search.py] 检索学科分类（arXiv 分类代码）
SEARCH_CATEGORIES = ["cs.CL", "cs.LG", "cs.AI", "stat.ML"]

# [Controller/arxiv_search.py] 请求 User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"

# [全局] 数据根目录 —— 基于本文件位置计算绝对路径，确保无论 CWD 在哪都指向 Sever/data
_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(_SEVER_DIR, "data")

# [Controller/arxiv_search.py] 输出文件目录与文件名格式
OUTPUT_DIR = os.path.join(DATA_ROOT, "arxivList", "md")
ARXIV_JSON_DIR = os.path.join(DATA_ROOT, "arxivList", "json")
FILENAME_FMT = "%Y-%m-%d.md"
JSON_FILENAME_FMT = "%Y-%m-%d.json"
MANIFEST_FILENAME = "_manifest.json"

# [Controller/llm_select_theme.py] 主题相关性筛选输出目录
LLM_SELECT_THEME_DIR = os.path.join(DATA_ROOT, "llm_select_theme")

# [Controller/paper_theme_filter.py] 主题过滤输出目录
PAPER_THEME_FILTER_DIR = os.path.join(DATA_ROOT, "paper_theme_filter")

# [Controller/paperList_remove_duplications.py] 去重输出目录
PAPER_DEDUP_DIR = os.path.join(DATA_ROOT, "paperList_remove_duplications")

# [Controller/pdf_download.py] PDF 下载与预览目录
PDF_OUTPUT_DIR = os.path.join(DATA_ROOT, "raw_pdf")
PDF_PREVIEW_DIR = os.path.join(DATA_ROOT, "preview_pdf")

# [Controller/pdfsplite_to_minerU.py] PDF 预处理/拆分输出目录
PREVIEW_MINERU_DIR = os.path.join(DATA_ROOT, "preview_pdf_to_mineru")
SELECTED_MINERU_DIR = os.path.join(DATA_ROOT, "selectedpaper_to_mineru")

# [Controller/file_collect.py] 文件收集输出目录
FILE_COLLECT_DIR = os.path.join(DATA_ROOT, "file_collect")

# [Controller/arxiv_search.py] 分页与筛选参数
PAGE_SIZE_DEFAULT = 200
MAX_PAPERS_DEFAULT = 500
SLEEP_DEFAULT = 3.1

# [Controller/arxiv_search.py] 代理与重试配置
USE_PROXY_DEFAULT = False
RETRY_COUNT = 5
PROGRESS_SINGLE_LINE = True
RETRY_TOTAL = 7
RETRY_BACKOFF = 1.5
REQUESTS_UA = USER_AGENT
PROXIES = None
RESPECT_ENV_PROXIES = False


"""
========================
二、大模型调用配置
（主题筛选 → 机构抽取 → 摘要生成 → 精简 → 批量）
========================
"""

# [全局] API KEY 配置项

# [Controller/pdfsplite_to_minerU.py] minerU Token（请从环境变量 MINERU_TOKEN 读取，或在本地未提交文件中配置）
minerU_Token = ""

# [全局] Qwen API Key（摘要/精简/批量）（请从环境变量 QWEN_API_KEY 读取，或在本地未提交文件中配置）
qwen_api_key = ""

# [全局] NVIDIA API Key（请从环境变量 NVIDIA_API_KEY 读取，或在本地未提交文件中配置）
nvidia_api_key = ""


# [Controller/llm_select_theme.py] 主题相关性评分模型
theme_select_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
theme_select_model = "qwen-plus"
theme_select_max_tokens = 16
theme_select_temperature = 1.0
theme_select_concurrency = 8

# [Controller/pdf_info.py] 机构判别模型参数
org_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
org_model = "qwen-plus"
org_max_tokens = 2048
org_temperature = 1.0
pdf_info_concurrency = 8

# [Controller/paper_summary.py] 摘要生成模型参数
summary_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# summary_model = "qwen2.5-72b-instruct"
summary_model = "qwen-plus"
summary_max_tokens = 2048
summary_temperature = 1.0
# [Controller/paper_summary.py] 摘要输入长度控制（模型上下文窗口硬上限与安全边距）
# 总输入预算 = summary_input_hard_limit - summary_input_safety_margin
# 用户内容裁剪预算 = 总输入预算 - 系统提示词近似长度（按 UTF-8 字节近似 token）
# 最终传入 ≈ 系统提示词 + 裁剪后的用户内容 ≤ 总输入预算
summary_input_hard_limit = 129024
summary_input_safety_margin = 4096
summary_concurrency = 16




# [Controller/paper_summary_claude.py] 摘要生成模型2
summary_base_url_2 = "https://gptgod.cloud/v1"
summary_gptgod_apikey = ""  # 请从环境变量 SUMMARY_GPTGOD_APIKEY 读取
summary_model_2 = "claude-sonnet-4-5-all"

# [Controller/paper_summary.py] 摘要生成模型3（VectorEngine）
summary_base_url_3 = "https://api.vectorengine.ai/v1"
summary_apikey_3 = ""  # 请从环境变量 SUMMARY_APIKEY_3 读取
summary_model_3 = "claude-opus-4-5-20251101"

# [Controller/paper_summary.py] & [Controller/summary_limit.py]
# 摘要生成 / 摘要精简 模型选择参数：
# 1 = Qwen（阿里云 DashScope）
# 2 = GPTGod Claude（summary_*_2 配置）
# 3 = VectorEngine Claude（summary_*_3 配置）
try:
    SLLM = int(os.environ.get("SLLM", "1") or "1")
except ValueError:
    SLLM = 1
if SLLM not in (1, 2, 3):
    SLLM = 1

# [Controller/summary_limit.py] 摘要精简模型参数
summary_limit_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
summary_limit_model = "qwen-plus"
summary_limit_max_tokens = 2048
summary_limit_temperature = 1.0
summary_limit_concurrency = 8
# [Controller/summary_limit.py] 摘要精简输入长度控制（模型上下文窗口硬上限与安全边距）
# 总输入预算 = summary_limit_input_hard_limit - summary_limit_input_safety_margin
summary_limit_input_hard_limit = 129024
summary_limit_input_safety_margin = 4096


# [Controller/summary_limit.py] 摘要精简模型2
summary_limit_url_2 = "https://gptgod.cloud/v1"
summary_limit_gptgod_apikey = ""  # 请从环境变量 SUMMARY_LIMIT_GPTGOD_APIKEY 读取
summary_limit_model_2 = "claude-sonnet-4-5-all"

# [Controller/summary_limit.py] 摘要精简模型3（VectorEngine）
summary_limit_url_3 = "https://api.vectorengine.ai/v1"
summary_limit_apikey_3 = ""  # 请从环境变量 SUMMARY_LIMIT_APIKEY_3 读取
summary_limit_model_3 = "claude-opus-4-5-20251101"

# [Controller/selectpaper_to_jsonl.py] [Controller/paper_summary_batch.py] 批量摘要配置
summary_batch_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
summary_batch_api_key = qwen_api_key
summary_batch_model = "qwen-plus"
summary_batch_temperature = 0.5
summary_batch_completion_window = "24h"
summary_batch_endpoint = "/v1/chat/completions"
summary_batch_out_root = os.path.join(DATA_ROOT, "paper_summary_batch")
summary_batch_jsonl_root = os.path.join(DATA_ROOT, "selectpaper_to_jsonl")



"""
========================
三、提示词配置
（主题筛选/摘要/精简/批量/机构抽取）
========================
"""

# [Controller/llm_select_theme.py] 主题相关性评分系统提示词
theme_select_system_prompt = (
    "你是论文主题相关性评分助手。"
    "请判断给定论文是否与以下主题相关："
    "大模型/LLM、算法与训练/推理、多模态、Agent/智能体、强化学习、SFT、GRPO、DPO、DAPO、SAPO等偏好优化、推理解码、模型评测，"
    "LangChain/LangGraph，工具调用/工具调度，上下文与记忆管理等相关变体。"
    "只根据给定的标题和摘要，输出主题相关性分数。"
    "分数范围 0 到 1，越相关越接近 1。"
    "只输出一个数字，不要输出其他内容。"
)

# [Controller/paper_summary.py] 摘要生成示例
summary_example="""
微软：多模态大模型能力解耦分析
📖标题：What MLLMs Learn about When they Learn about Multimodal Reasoning: Perception, Reasoning, or their Integration?
🌐来源：arXiv,[论文编号]
	
🛎️文章简介
🔸研究问题：多模态大型语言模型（MLLM）在进行多模态推理时，如何分辨出来自感知、推理还是两者的整合的问题？
🔸主要贡献：论文提出了MATHLENS benchmark，旨在分离多模态推理中的感知、推理及其整合能力，提供了新方法以分析模型的性能。
	
📝重点思路
🔸引入MATHLENS基准，通过926道几何问题及其8种视觉修改，设计实验以分离感知、推理和整合能力。
🔸采用四种相关注释，分别测试感知（图形）、推理（文本描述）、多模态问题和微调探测器。
🔸通过先训练文本后训练图像的方式，以评估不同训练策略对模型的影响。
🔸进行对比实验，从开放模型中收集数据，评估7-9B参数范围内的多模态推理模型的表现。
	
🔎分析总结
🔸感知能力主要通过强化学习增强，且在已有文本推理能力的前提下效果更佳。
🔸多模态推理训练同时促进感知与推理的提升，但推理能力并未表现出独立的额外增益。
🔸整合能力是三者中提升最少的，表明存在持续的整合错误，成为主要的失败模式。
🔸在视觉输入变化的情况下，强化学习提高了一致性，而多模态监督微调则导致了过拟合，从而降低了一致性。
	
💡个人观点
论文通过基准明确分离多模态推理的关键能力，使得对模型性能的评估更加细致和准确。
"""
# [Controller/paper_summary.py] 摘要生成系统提示词
system_prompt = (
    "你是一个论文笔记助手，请阅读论文内容，严格按照格式写这篇论文的笔记，"
    "不要带有markdown格式，字数控制在900字以内。格式如下："
    "笔记标题：（10个字左右的中文短句说明论文的贡献）\n"
    "🛎️文章简介\n"
    "🔸研究问题：（用一个问句描述论文试图解决什么问题）\n"
    "🔸主要贡献：（一句话回答这篇论文有什么贡献）\n"
    "📝重点思路 （逐条写论文的研究方法是什么，每一条都以🔸开头）\n"
    "🔎分析总结 （逐条写论文通过实验分析得到了哪些结论，每一条都以🔸开头）\n"
    "💡个人观点\n"
    "（总结论文的创新点）"
    ""
)

# [Controller/summary_limit.py] 摘要精简提示词：文章简介
summary_limit_prompt_intro = (
    "你是一名严谨的学术论文摘要编辑。你的任务是把用户提供的【文章简介】压缩成更短的版本。\n"
    "硬性规则：\n"
    "只允许基于原文改写与删减，禁止新增论文未明确出现的数字、结论、因果解释、背景信息。\n"
    "必须保留两件事：①研究问题（1句内）②主要贡献/做了什么（1句内）。\n"
    "删除所有修饰、铺垫、泛化评价（如“很有意义/非常重要”）。\n"
    "输出 2 句中文，整体不超过 180 字（按去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要字数说明、不要解释。"
)
# [Controller/summary_limit.py] 摘要精简提示词：重点思路
summary_limit_prompt_method = (
    "你是一名学术方法部分的精炼编辑。你的任务是把用户提供的【重点思路】压缩到更短、更“信息密度高”的版本。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的实验设置、对比对象、指标、结论与数字。\n"
    "只保留“怎么做”的关键动作：benchmark/数据/任务设计/训练或评测策略（优先保留带数字/专有名词的信息）。\n"
    "输出格式固定为 最多 4 条，每条以“🔸”开头，每条 1 句。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要额外说明。"
)
# [Controller/summary_limit.py] 摘要精简提示词：分析总结
summary_limit_prompt_findings = (
    "你是一名结果与结论部分的审稿式编辑。你的任务是把用户提供的【分析总结】压缩为更短的“关键发现列表”。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的解释、推断、因果链、建议或外延应用。\n"
    "必须保留最核心的 2–4 个发现（优先保留：一致性变化、失败模式、能力对比、训练方式影响）。\n"
    "输出格式固定为 最多 4 条，每条以“🔸”开头，每条 1 句，句子尽量短。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要总结段、不要字数说明。"
)
# [Controller/summary_limit.py] 摘要精简提示词：个人观点
summary_limit_prompt_opinion = (
    "你是一名克制、保真的学术评论编辑。你的任务是把用户提供的【个人观点】压缩为极短版本。\n"
    "硬性规则：\n"
    "只允许基于原文观点做删减与改写，禁止新增论文未提到的价值判断、应用场景、改进建议或任何推断性结论。\n"
    "允许保留“评价框架”，但措辞必须克制（避免“必然/革命性/全面提升”等强断言）。\n"
    "输出 1–2 句中文，整体不超过 160 字（去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要解释、不要字数说明。"
)

# [Controller/summary_limit.py] 摘要结构校验提示词
summary_limit_prompt_structure_check = (
    "你是一名摘要结构校验器。你的任务是判断用户提供的摘要是否符合示例的结构与顺序。\n"
    "示例：\n"
    f"{summary_example}\n"
    "规则：\n"
    "1) 必须包含 机构/标题/来源 三行（内容可不同）。\n"
    "2) 第一行格式必须为：机构：一句话概括论文解决的问题（不写原标题）。\n"
    "3) 必须包含四个段落标题，并按顺序出现：文章简介、重点思路、分析总结、个人观点（允许前缀符号）。\n"
    "4) 内容可以为空，但标题行必须存在。\n"
    "只输出 YES 或 NO，不要输出其他内容。"
)

# [Controller/summary_limit.py] 摘要结构重排提示词
summary_limit_prompt_structure_rewrite = (
    "你是一名摘要结构整理器。你的任务是把用户提供的文本整理为示例的结构与顺序，且不改内容。\n"
    "示例：\n"
    f"{summary_example}\n"
    "规则：\n"
    "1) 输出必须包含 机构/标题/来源 三行；若原文缺失，留空内容但保留行。\n"
    "2) 第一行格式必须为：机构：一句话概括论文解决的问题（不写原标题）。\n"
    "3) 输出必须包含四个段落标题，并按顺序出现：文章简介、重点思路、分析总结、个人观点。\n"
    "4) 只允许搬运原文内容到对应段落，不允许新增、删减或改写。\n"
    "5) 保留原文中的要点条目、句子与措辞。\n"
    "只输出整理后的正文，不要解释。"
)

# [Controller/summary_limit.py] 首行压缩提示词
summary_limit_prompt_headline = (
    "你是一名摘要首行压缩器。你的任务是压缩给定的首行文本。\n"
    "规则：\n"
    "1) 输出格式必须为：机构：一句话概括论文解决的问题（不写原标题）。\n"
    "2) 机构名称必须控制在 5 个字符以内。\n"
    "3) 若机构是众所周知的英文品牌/机构名，保留原英文（如 Google、Meta、OpenAI、Microsoft、DeepMind、MiniMax）。\n"
    "4) 若机构不是广为人知的英文名，请翻译为中文；若原文同时给出中文全称，优先使用中文全称再压缩。\n"
    "5) 若出现中文简称且难以理解（例如“上智”），优先改成原文中的全称；若原文没有全称，则保留原简称。\n"
    "6) 总长度不超过 20 字（按去空白字符计）。\n"
    "7) 只做压缩与改写，不引入原文不存在的事实。\n"
    "只输出压缩后的单行文本，不要解释。"
)


# [Controller/selectpaper_to_jsonl.py] [Controller/paper_summary_batch.py] 批量摘要系统提示词
summary_batch_system_prompt = (
    "你是一个论文笔记助手，请阅读论文内容，严格按照格式写这篇论文的笔记，"
    "不要带有markdown格式，字数控制在900字以内。格式如下："
    "笔记标题：（10个字左右的中文短句说明论文的贡献）\n"
    "🛎️文章简介\n"
    "🔸研究问题：（用一个问句描述论文试图解决什么问题）\n"
    "🔸主要贡献：（一句话回答这篇论文有什么贡献）\n"
    "📝重点思路 （逐条写论文的研究方法是什么，每一条都以🔸开头）\n"
    "🔎分析总结 （逐条写论文通过实验分析得到了哪些结论，每一条都以🔸开头）\n"
    "💡个人观点\n"
    "（总结论文的创新点）"
)

# [Controller/pdf_info.py] 机构判断系统提示词
pdf_info_system_prompt = """
你将仅基于给定论文前两页的 Markdown 文本做信息抽取与判断。你必须只输出一个 JSON 对象，且字段严格只有：instution、is_large、abstract。不得输出任何额外文本、解释、代码块或多余字段。

【instution 提取优先级】
1) 优先通讯作者（Corresponding author）的机构；若能识别通讯作者标记（如 *、†、脚注含“Corresponding author / Correspondence”），以其机构为准。
2) 若无法可靠识别通讯作者，则取第一作者的机构。
3) 若机构信息缺失或不确定，instution 输出 null（不要猜）。
4) instution 输出必须进行“机构名标准化/缩减”（见下方规则）。

【机构名标准化/缩减规则（非常重要）】
目标：让 instution 输出“人们一眼能懂的短名称”，避免过长、避免不常见英文全称。

I. 直接用常见短名（优先级最高；命中即替换）
- 任何出现 OpenAI / OpenAI, Inc. → 输出 "OpenAI"
- 任何出现 Google Research / Google LLC / Google → 输出 "Google"（不要输出“Google Research”）
- 任何出现 DeepMind / Google DeepMind → 输出 "DeepMind"
- 任何出现 Meta / Meta AI / FAIR / Facebook AI Research → 输出 "Meta"
- 任何出现 Microsoft Research / Microsoft → 输出 "Microsoft"
- 任何出现 NVIDIA / NVIDIA Research → 输出 "NVIDIA"
- 任何出现 Amazon / AWS / Amazon Web Services → 输出 "Amazon"
- 任何出现 Apple / Apple Inc. → 输出 "Apple"
- 任何出现 IBM Research / IBM → 输出 "IBM"
- 任何出现 Anthropic → 输出 "Anthropic"
- 任何出现 xAI → 输出 "xAI"
- 任何出现 Hugging Face → 输出 "Hugging Face"
- 任何出现 Allen Institute for AI / AI2 → 输出 "AI2"

II. 国内常见机构：翻译/识别后输出耳熟能详简称（命中即替换）
- 清华大学 → "清华"
- 北京大学 → "北大"
- 上海交通大学 → "上交"
- 浙江大学 → "浙大"
- 复旦大学 → "复旦"
- 南京大学 → "南大"
- 中国科学院 / 中科院 / Chinese Academy of Sciences / CAS → "中科院"
- 上海人工智能实验室 → "上智院"
- 智源研究院 / Beijing Academy of AI / BAAI → "智源"
- 之江实验室 → "之江"
- 华为诺亚方舟实验室 / Noah’s Ark Lab → "华为"
- 阿里达摩院 / DAMO Academy → "阿里"
- 腾讯 AI Lab / Tencent AI Lab → "腾讯"
- 百度研究院 / 百度研究 / 文心 / ERNIE 团队 → "百度"
- 字节跳动 / ByteDance / Seed / ByteDance AI Lab → "字节"

III. 海外“原文可能不好懂”的机构：先翻译成常用中文，再缩减（命中即替换）
（以下属于示例清单，可按需继续扩充）
- University of Oxford / Oxford University → "牛津"
- University of Cambridge / Cambridge University → "剑桥"
- Massachusetts Institute of Technology / MIT → "MIT"
- Stanford University → "Stanford"
- Carnegie Mellon University / CMU → "CMU"
- University of California, Berkeley / UC Berkeley → "伯克利"
- ETH Zurich / ETH Zürich → "苏黎世联邦理工"
- EPFL → "洛桑联邦理工"
- University of Washington → "华盛顿大学"
- University of Illinois Urbana-Champaign / UIUC → "UIUC"
说明：
- 对于 MIT/Stanford/CMU 等全球极常见缩写，可直接保留英文缩写（如 "MIT"、"CMU"）。
- 对于 Oxford/Cambridge 等，优先输出中文简称（"牛津"、"剑桥"），避免原文导致读者不熟悉。

IV. 规则化缩短（用于未命中以上映射时）
若机构未命中 I/II/III，则按以下规则尽量缩短为“易读短名”，但禁止瞎造简称：
1) 去掉常见后缀：University/Universität/Université、Department of、School of、Faculty of、Institute of、Laboratory、Research Center、College 等（中文同理：学院/系/研究中心/实验室等），尽量保留核心组织名。
2) 若文本给出了明确缩写（如 “University of X (UX)” 或 “...简称 UX”），可使用该缩写。
3) 若机构名为不常见外文且你能可靠翻译出常见中文名称，则“先翻译成中文全称，再酌情缩短为常用叫法”；若无法可靠翻译，则保留原文但尽量去除部门级前后缀（不要硬翻）。
4) 避免输出过长：尽量控制在 2~8 个汉字或 1~3 个英文词/常见缩写。

【is_large 判断：大机构/强背书机构】
只能依据前两页可见信息判断，禁止臆测。输出布尔值。
判定逻辑为“强命中白名单 OR 启发式满足条件”，否则为 false。

A. 强命中白名单（出现其机构名或明确组织名即 true；大小写/缩写/常见别名视为命中）
- OpenAI, DeepMind, Google, Meta/FAIR, Microsoft, NVIDIA, Amazon/AWS, Apple, IBM, Anthropic, xAI, Hugging Face, AI2
- 清华, 北大, 上交, 浙大, 复旦, 南大, 中科院, 上智院, 智源, 之江, 华为, 阿里, 腾讯, 百度, 字节
- 牛津, 剑桥, MIT, Stanford, CMU, 伯克利, 苏黎世联邦理工, 洛桑联邦理工, UIUC 等（如前两页明确出现）

B. 启发式补充（未命中白名单时使用；满足“至少两条”才可判 true；否则判 false）
- 机构名包含明显研究实体关键词：Research / Labs / Laboratory / Institute / Academy / National Lab / AI Lab 等（或等价中文：研究院/研究所/实验室/国家重点实验室等）
- 邮箱域名或主页域名显示为知名大机构/顶尖高校/国家级科研单位（例如 openai.com, google.com, meta.com, microsoft.com, nvidia.com, amazon.com, *.edu, *.ac, cas.cn 等）
- 作者单位中出现多个机构且至少一个机构为国际知名企业研究部门/国家级科研机构/顶尖大学（需从文本中可直接识别，不可猜测）
- 文本中明确自述来自“公司研究院/研究部门/国家实验室/国家级研究院”等

C. 不确定处理
- 若信息不足以满足 A 或 B，则 is_large=false（不要为了“看起来像大机构”而猜 true）。

【abstract 规则：一句话】
- 用一句话概括论文： “提出/使用了什么方法，用于什么任务/问题，带来了什么改进/结论”。
- 只能依据前两页可见内容；如果没有明确的提升幅度/数值，严禁编造数字或百分比，可写“提升性能（幅度未在前两页给出）”。
- 如果前两页没有摘要或关键信息不足，abstract 仍输出一句话，但要明确“不足以确定细节”。

只返回 JSON，例如：
{"instution": "...", "is_large": true/false, "abstract": "..."}
"""

paper_assets_system_prompt = """
你是一个“论文结构化抽取器（Paper Block Extractor）”。你的任务是把给定的一篇论文摘要/笔记文本抽取并整理为固定的 8 个结构块，**只输出下面这个 JSON 对象**。

# 核心思维
**你不是在写摘要，你是在构建数据库。**
请想象你正在为以后的“论文横向对比系统”填充数据，因此你的提取必须：
1. **原子化**：将复杂的逻辑拆解为独立的要点。
2. **标准化**：尽可能使用学术界通用的标准术语（Key-Value 形式）。
3. **证据主义**：原文有的才写，原文未提及的字段填空，绝对不要幻觉。

# 目标
- 输入：一篇论文的中文摘要/笔记文本。
- 输出：**只输出一个 JSON 对象**，严格遵循下方 Schema。

# 输出 JSON Schema
{
  "background":  { "text": "<string>", "bullets": ["<string>", "..."] },
  "objective":   { "text": "<string>", "bullets": ["<string>", "..."] },
  "method":      { "text": "<string>", "bullets": ["<string>", "..."] },
  "data":        { "text": "<string>", "bullets": ["<string>", "..."] },
  "experiment":  { "text": "<string>", "bullets": ["<string>", "..."] },
  "metrics":     { "text": "<string>", "bullets": ["<string>", "..."] },
  "results":     { "text": "<string>", "bullets": ["<string>", "..."] },
  "limitations": { "text": "<string>", "bullets": ["<string>", "..."] }
}

# 各块定义与抽取标准（Strict Instructions）

1. **background (背景)**
   - Text: 简述研究背景和现有痛点。
   - Bullets: **强制包含** `【痛点】：...` 或 `【现状】：...`。

2. **objective (目标)**
   - Text: 论文的核心贡献。
   - Bullets: 必须包含明确的任务类型，例如 `【任务】：代码生成` 或 `【核心贡献】：提出了一种无训练的迁移方法`。

3. **method (方法) —— *最重要，需结构化***
   - Text: "输入→处理→输出"的完整链路描述。
   - Bullets: **必须**包含以下维度的键值对（若文中未提及，根据常识推断或填未知）：
     - `【输入】：...`
     - `【架构】：...` (如 Transformer, Diffusion, Agent)
     - `【关键机制】：...` (如 RAG, CoT, LoRA, 剪枝)
     - `【是否训练】：...` (**必须明确**：是/否。例如 "否 (无需参数更新)" 或 "是 (LoRA微调)")
     - `【创新点】：...`

4. **data (数据)**
   - Text: 数据集描述。
   - Bullets: **必须列出具体数据集名称**。格式示例：`【数据集】：GSM8K (数学)`、`【来源】：GitHub Repos`。

5. **experiment (实验设置)**
   - Text: 实验环境与基线。
   - Bullets: 关注对比对象。格式示例：`【基线模型】：GPT-4, Llama-2`、`【消融实验】：去除模块A的效果`。

6. **metrics (评价指标)**
   - Text: 评估协议。
   - Bullets: **只写英文标准指标名**。格式示例：`Pass@1`、`Exact Match (EM)`、`Win Rate`。不要翻译成“准确率”除非原文只有中文。

7. **results (结果) —— *必须与 Data 对应***
   - Text: 核心结论概括。
   - Bullets: **必须包含数值**。格式建议：`【任务名】：指标 = 数值 (对比提升)`。
     - 例如：`GSM8K：EM = 78.5% (+12% vs Llama2)`

8. **limitations (局限)**
   - Text: 总结不足。
   - Bullets: 分类描述。如 `【假设强】：依赖...`、`【开销大】：推理速度慢...`。

# 质量控制 (Quality Assurance)
- **JSON 格式**：确保是合法的 JSON，无多余逗号，无 Markdown 标记（不要 ```json）。
- **空值处理**：若原文完全未提及某块，保留该键，值为 text="" 和 bullets=[]。
- **语言**：Text 使用流畅中文；专有名词（数据集、模型名、指标）**保留英文**。

现在开始处理用户提供的论文文本。
"""


"""
四、字数上限

"""
# [Controller/summary_limit.py] 四个正文区块字数上限（按去空白字符计，超则调用模型压短）
summary_limit_section_limit_intro = 170
summary_limit_section_limit_method = 270
summary_limit_section_limit_findings = 270
summary_limit_section_limit_opinion = 150
# [Controller/summary_limit.py] 首行（机构：一句话）字数上限（按去空白字符计）
summary_limit_headline_limit = 18



"""
以下为可选项：
"""
