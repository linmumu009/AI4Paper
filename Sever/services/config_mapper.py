"""
配置映射服务层。

将数据库中的模型配置和提示词配置映射到 config.py 中的变量。
基于命名约定自动映射。
"""

from typing import Any, Dict, Optional

from services import config_service


def map_llm_config_to_variables(config: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """根据前缀将模型配置映射到config.py变量。
    
    Args:
        config: 模型配置字典（来自数据库）
        prefix: 使用前缀（如 "theme_select", "org", "summary" 等）
        
    Returns:
        映射后的变量字典，可直接用于 config_service.update_config
    """
    updates = {}
    
    # 基础映射规则
    field_mapping = {
        "base_url": f"{prefix}_base_url",
        "model": f"{prefix}_model",
        "max_tokens": f"{prefix}_max_tokens",
        "temperature": f"{prefix}_temperature",
        "concurrency": f"{prefix}_concurrency",
        "input_hard_limit": f"{prefix}_input_hard_limit",
        "input_safety_margin": f"{prefix}_input_safety_margin",
    }
    
    # 特殊处理：api_key 的映射
    # 根据前缀决定使用哪个 api_key 变量
    api_key_mapping = {
        "theme_select": "qwen_api_key",
        "org": "qwen_api_key",
        "summary": "qwen_api_key",
        "summary_limit": "qwen_api_key",
        "summary_batch": "summary_batch_api_key",
    }
    
    # 应用基础映射
    for db_field, config_var in field_mapping.items():
        if db_field in config and config[db_field] is not None:
            updates[config_var] = config[db_field]
    
    # 处理 api_key
    if "api_key" in config and config["api_key"]:
        api_key_var = api_key_mapping.get(prefix)
        if api_key_var:
            updates[api_key_var] = config["api_key"]
    
    # 特殊字段映射（根据前缀）
    if prefix == "summary_batch":
        # summary_batch 有额外的字段
        if "endpoint" in config and config["endpoint"]:
            updates["summary_batch_endpoint"] = config["endpoint"]
        if "completion_window" in config and config["completion_window"]:
            updates["summary_batch_completion_window"] = config["completion_window"]
        if "out_root" in config and config["out_root"]:
            updates["summary_batch_out_root"] = config["out_root"]
        if "jsonl_root" in config and config["jsonl_root"]:
            updates["summary_batch_jsonl_root"] = config["jsonl_root"]
    
    # 特殊处理：org 前缀的 concurrency 字段名不同
    if prefix == "org" and "concurrency" in config and config["concurrency"] is not None:
        updates["pdf_info_concurrency"] = config["concurrency"]
        # 移除可能错误添加的 org_concurrency
        updates.pop(f"{prefix}_concurrency", None)
    
    return updates


def map_prompt_config_to_variable(config: Dict[str, Any], variable_name: str) -> Dict[str, Any]:
    """将提示词配置映射到指定的config.py变量。
    
    Args:
        config: 提示词配置字典（来自数据库）
        variable_name: 目标变量名（如 "theme_select_system_prompt", "system_prompt" 等）
        
    Returns:
        映射后的变量字典，可直接用于 config_service.update_config
    """
    if "prompt_content" not in config:
        raise ValueError("配置中缺少 prompt_content 字段")
    
    return {
        variable_name: config["prompt_content"]
    }


def apply_llm_config(config_id: int, usage_prefix: str) -> Dict[str, Any]:
    """应用模型配置到config.py。
    
    Args:
        config_id: 模型配置ID
        usage_prefix: 使用前缀（如 "theme_select", "org", "summary" 等）
        
    Returns:
        更新后的配置字典
    """
    from services import llm_config_service
    
    # 获取配置
    config = llm_config_service.get_config(config_id)
    if not config:
        raise ValueError(f"模型配置 {config_id} 不存在")
    
    # 映射到变量
    updates = map_llm_config_to_variables(config, usage_prefix)
    
    if not updates:
        raise ValueError(f"无法为前缀 '{usage_prefix}' 生成映射")
    
    # 应用更新
    return config_service.update_config(updates)


def apply_prompt_config(config_id: int, variable_name: str) -> Dict[str, Any]:
    """应用提示词配置到config.py。
    
    Args:
        config_id: 提示词配置ID
        variable_name: 目标变量名（如 "theme_select_system_prompt", "system_prompt" 等）
        
    Returns:
        更新后的配置字典
    """
    from services import prompt_config_service
    
    # 获取配置
    config = prompt_config_service.get_config(config_id)
    if not config:
        raise ValueError(f"提示词配置 {config_id} 不存在")
    
    # 映射到变量
    updates = map_prompt_config_to_variable(config, variable_name)
    
    # 应用更新
    return config_service.update_config(updates)
