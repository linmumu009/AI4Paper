"""
系统配置服务层。

从 config.py 读取所有配置项，支持通过 JSON 文件覆盖配置值。
配置修改保存到 database/config.json，应用启动时自动加载。
"""

import inspect
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Add parent directory to path to import config
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE_DIR)

# Import config module to inspect its attributes
import config.config as config_module

_CONFIG_JSON_PATH = os.path.join(_BASE_DIR, "database", "config.json")

# 配置项分组定义（基于 config.py 的注释结构）
_CONFIG_GROUPS = {
    "数据与流程基础配置": [
        "API_URL",
        "SEARCH_CATEGORIES",
        "USER_AGENT",
        "OUTPUT_DIR",
        "ARXIV_JSON_DIR",
        "FILENAME_FMT",
        "JSON_FILENAME_FMT",
        "MANIFEST_FILENAME",
        "LLM_SELECT_THEME_DIR",
        "PAPER_THEME_FILTER_DIR",
        "PAPER_DEDUP_DIR",
        "PDF_OUTPUT_DIR",
        "PDF_PREVIEW_DIR",
        "PREVIEW_MINERU_DIR",
        "SELECTED_MINERU_DIR",
        "FILE_COLLECT_DIR",
        "PAGE_SIZE_DEFAULT",
        "MAX_PAPERS_DEFAULT",
        "SLEEP_DEFAULT",
        "USE_PROXY_DEFAULT",
        "RETRY_COUNT",
        "PROGRESS_SINGLE_LINE",
        "RETRY_TOTAL",
        "RETRY_BACKOFF",
        "REQUESTS_UA",
        "PROXIES",
        "RESPECT_ENV_PROXIES",
    ],
    "大模型调用配置": [
        "minerU_Token",
        "qwen_api_key",
        "nvidia_api_key",
        "theme_select_base_url",
        "theme_select_model",
        "theme_select_max_tokens",
        "theme_select_temperature",
        "theme_select_concurrency",
        "org_base_url",
        "org_model",
        "org_max_tokens",
        "org_temperature",
        "pdf_info_concurrency",
        "summary_base_url",
        "summary_model",
        "summary_max_tokens",
        "summary_temperature",
        "summary_input_hard_limit",
        "summary_input_safety_margin",
        "summary_concurrency",
        "summary_base_url_2",
        "summary_gptgod_apikey",
        "summary_model_2",
        "summary_base_url_3",
        "summary_apikey_3",
        "summary_model_3",
        "SLLM",
        "summary_limit_base_url",
        "summary_limit_model",
        "summary_limit_max_tokens",
        "summary_limit_temperature",
        "summary_limit_concurrency",
        "summary_limit_input_hard_limit",
        "summary_limit_input_safety_margin",
        "summary_limit_url_2",
        "summary_limit_gptgod_apikey",
        "summary_limit_model_2",
        "summary_limit_url_3",
        "summary_limit_apikey_3",
        "summary_limit_model_3",
        "summary_batch_base_url",
        "summary_batch_api_key",
        "summary_batch_model",
        "summary_batch_temperature",
        "summary_batch_completion_window",
        "summary_batch_endpoint",
        "summary_batch_out_root",
        "summary_batch_jsonl_root",
    ],
    "提示词配置": [
        "theme_select_system_prompt",
        "summary_example",
        "system_prompt",
        "summary_limit_prompt_intro",
        "summary_limit_prompt_method",
        "summary_limit_prompt_findings",
        "summary_limit_prompt_opinion",
        "summary_limit_prompt_structure_check",
        "summary_limit_prompt_structure_rewrite",
        "summary_limit_prompt_headline",
        "summary_batch_system_prompt",
        "pdf_info_system_prompt",
        "paper_assets_system_prompt",
    ],
    "字数上限配置": [
        "summary_limit_section_limit_intro",
        "summary_limit_section_limit_method",
        "summary_limit_section_limit_findings",
        "summary_limit_section_limit_opinion",
        "summary_limit_headline_limit",
    ],
}


def _get_all_config_items() -> Dict[str, Any]:
    """从 config 模块获取所有配置项（排除私有变量和模块级变量）。"""
    items = {}
    for name, value in inspect.getmembers(config_module):
        # 排除私有变量、函数、模块等
        if (
            not name.startswith("_")
            and not inspect.ismodule(value)
            and not inspect.isfunction(value)
            and not inspect.isclass(value)
            and not inspect.ismethod(value)
        ):
            items[name] = value
    return items


def _load_config_json() -> Dict[str, Any]:
    """从 JSON 文件加载用户配置。"""
    if os.path.isfile(_CONFIG_JSON_PATH):
        try:
            with open(_CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"警告: 无法加载配置文件 {_CONFIG_JSON_PATH}: {e}")
            return {}
    return {}


def _save_config_json(config_dict: Dict[str, Any]) -> None:
    """保存配置到 JSON 文件。"""
    os.makedirs(os.path.dirname(_CONFIG_JSON_PATH), exist_ok=True)
    with open(_CONFIG_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, ensure_ascii=False, indent=2)


def _apply_config_to_module(config_dict: Dict[str, Any]) -> None:
    """将配置字典应用到 config 模块。"""
    for key, value in config_dict.items():
        if hasattr(config_module, key):
            setattr(config_module, key, value)


def load_config() -> None:
    """应用启动时调用：从 JSON 文件加载配置并更新 config 模块。"""
    user_config = _load_config_json()
    if user_config:
        _apply_config_to_module(user_config)
        print(f"已从 {_CONFIG_JSON_PATH} 加载 {len(user_config)} 个配置项")


def get_config_with_groups() -> Dict[str, Any]:
    """
    获取所有配置项，按分组组织。
    
    返回格式：
    {
        "groups": [
            {
                "name": "数据与流程基础配置",
                "items": [
                    {
                        "key": "API_URL",
                        "value": "...",
                        "type": "str",
                        "description": "..."
                    },
                    ...
                ]
            },
            ...
        ],
        "defaults": {...}  # 所有默认值
    }
    """
    # 获取所有配置项的默认值
    defaults = _get_all_config_items()
    
    # 获取用户配置
    user_config = _load_config_json()
    
    # 合并：用户配置覆盖默认值
    current_values = {**defaults, **user_config}
    
    # 按分组组织
    groups = []
    all_keys = set()
    
    for group_name, keys in _CONFIG_GROUPS.items():
        items = []
        for key in keys:
            if key in defaults:
                all_keys.add(key)
                value = current_values.get(key, defaults[key])
                value_type = type(value).__name__
                
                # 生成描述（基于注释，这里简化处理）
                description = _get_config_description(key)
                
                items.append({
                    "key": key,
                    "value": value,
                    "type": value_type,
                    "description": description,
                    "is_sensitive": _is_sensitive_key(key),
                })
        
        if items:
            groups.append({
                "name": group_name,
                "items": items,
            })
    
    # 添加未分组的配置项
    ungrouped = []
    for key, value in defaults.items():
        if key not in all_keys:
            value_type = type(value).__name__
            ungrouped.append({
                "key": key,
                "value": current_values.get(key, value),
                "type": value_type,
                "description": _get_config_description(key),
                "is_sensitive": _is_sensitive_key(key),
            })
    
    if ungrouped:
        groups.append({
            "name": "其他配置",
            "items": ungrouped,
        })
    
    return {
        "groups": groups,
        "defaults": defaults,
    }


def _get_config_description(key: str) -> str:
    """获取配置项的描述（基于 config.py 中的注释）。"""
    descriptions = {
        "API_URL": "arXiv API 基础地址",
        "SEARCH_CATEGORIES": "检索学科分类（arXiv 分类代码）",
        "USER_AGENT": "请求 User-Agent",
        "PAGE_SIZE_DEFAULT": "分页大小默认值",
        "MAX_PAPERS_DEFAULT": "最大论文数默认值",
        "SLEEP_DEFAULT": "请求间隔时间（秒）",
        "USE_PROXY_DEFAULT": "是否使用代理",
        "RETRY_COUNT": "重试次数",
        "RETRY_TOTAL": "总重试次数",
        "RETRY_BACKOFF": "重试退避系数",
        "minerU_Token": "minerU Token（请从环境变量 MINERU_TOKEN 读取）",
        "qwen_api_key": "Qwen API Key（请从环境变量 QWEN_API_KEY 读取）",
        "nvidia_api_key": "NVIDIA API Key（请从环境变量 NVIDIA_API_KEY 读取）",
        "theme_select_model": "主题相关性评分模型",
        "org_model": "机构判别模型",
        "summary_model": "摘要生成模型",
        "SLLM": "摘要生成模型选择（1=Qwen, 2=GPTGod Claude, 3=VectorEngine Claude）",
    }
    return descriptions.get(key, "")


def _is_sensitive_key(key: str) -> bool:
    """判断配置项是否包含敏感信息（如 API keys）。"""
    sensitive_patterns = ["_key", "_token", "_apikey", "password", "secret"]
    return any(pattern in key.lower() for pattern in sensitive_patterns)


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新配置项。
    
    Args:
        updates: 要更新的配置项字典
        
    Returns:
        更新后的完整配置字典
    """
    # 加载当前配置
    current_config = _load_config_json()
    
    # 获取所有默认值用于验证
    defaults = _get_all_config_items()
    
    # 验证并更新
    for key, value in updates.items():
        if key not in defaults:
            raise ValueError(f"未知的配置项: {key}")
        
        # 类型验证（简化版）
        default_type = type(defaults[key])
        if not isinstance(value, default_type):
            # 尝试类型转换
            try:
                if default_type == bool:
                    value = str(value).lower() in ("true", "1", "yes", "on")
                elif default_type == int:
                    value = int(value)
                elif default_type == float:
                    value = float(value)
                elif default_type == list:
                    if isinstance(value, str):
                        # 尝试解析 JSON 或逗号分隔的字符串
                        if value.strip().startswith("["):
                            value = json.loads(value)
                        else:
                            value = [item.strip() for item in value.split(",") if item.strip()]
                    else:
                        value = list(value)
                else:
                    value = str(value)
            except (ValueError, json.JSONDecodeError) as e:
                raise ValueError(f"配置项 {key} 的值类型不匹配: {e}")
        
        current_config[key] = value
    
    # 保存到文件
    _save_config_json(current_config)
    
    # 应用到模块
    _apply_config_to_module(current_config)
    
    return current_config


def reset_config() -> None:
    """重置所有配置为默认值（删除 JSON 文件）。"""
    if os.path.isfile(_CONFIG_JSON_PATH):
        os.remove(_CONFIG_JSON_PATH)
    
    # 重新加载默认配置
    defaults = _get_all_config_items()
    _apply_config_to_module(defaults)