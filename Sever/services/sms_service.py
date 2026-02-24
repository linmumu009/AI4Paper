"""
sms_service.py - 阿里云短信验证码服务封装

从 Sever/config/sms_config.py 读取配置，提供：
- send_verify_code(phone) -> dict
- check_verify_code(phone, code) -> dict
并实现内存级频控（同一手机号 60 秒内只允许发送一次）。
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Optional

try:
    from config import sms_config1 as _cfg  # type: ignore[import]
except ImportError:
    _cfg = None  # type: ignore[assignment]


def _get_cfg(attr: str, default: Any = None) -> Any:
    return getattr(_cfg, attr, default) if _cfg is not None else default


# ---------------------------------------------------------------------------
# 内存频控：{phone: last_send_timestamp}
# ---------------------------------------------------------------------------
_send_lock = threading.Lock()
_last_send: dict[str, float] = {}


def _can_send(phone: str) -> tuple[bool, int]:
    """返回 (是否允许发送, 剩余等待秒数)"""
    interval = int(_get_cfg("INTERVAL", 60))
    with _send_lock:
        ts = _last_send.get(phone, 0.0)
        elapsed = time.time() - ts
        if elapsed < interval:
            return False, int(interval - elapsed)
        return True, 0


def _mark_sent(phone: str) -> None:
    with _send_lock:
        _last_send[phone] = time.time()


# ---------------------------------------------------------------------------
# 创建阿里云客户端
# ---------------------------------------------------------------------------
def _create_client():
    from alibabacloud_dypnsapi20170525.client import Client as DypnsClient
    from alibabacloud_tea_openapi import models as open_api_models

    ak = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or _get_cfg("ACCESS_KEY_ID")
    sk = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or _get_cfg("ACCESS_KEY_SECRET")
    if not ak or not sk:
        raise RuntimeError(
            "缺少阿里云 AK/SK：请设置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID / "
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET，或在 sms_config.py 中填写"
        )
    config = open_api_models.Config(access_key_id=ak, access_key_secret=sk)
    config.endpoint = _get_cfg("ENDPOINT", "dypnsapi.aliyuncs.com")
    return DypnsClient(config)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def send_verify_code(phone: str) -> dict:
    """
    发送短信验证码。

    返回:
        {
          "success": bool,
          "message": str,
          "biz_id": str | None,   # 阿里云流水号，可用于后续核验
          "out_id": str,          # 本次请求的外部流水号
          "wait_seconds": int,    # 频控剩余等待秒（success=False 且频控触发时 > 0）
        }
    """
    from alibabacloud_dypnsapi20170525 import models as dypns_models
    from alibabacloud_tea_util import models as util_models
    import json

    allowed, wait = _can_send(phone)
    if not allowed:
        return {
            "success": False,
            "message": f"发送过于频繁，请 {wait} 秒后再试",
            "biz_id": None,
            "out_id": "",
            "wait_seconds": wait,
        }

    sign_name: Optional[str] = _get_cfg("SIGN_NAME")
    template_code: Optional[str] = _get_cfg("TEMPLATE_CODE")
    if not sign_name or not template_code:
        return {
            "success": False,
            "message": "短信配置不完整，请检查 sms_config.py 中的 SIGN_NAME 和 TEMPLATE_CODE",
            "biz_id": None,
            "out_id": "",
            "wait_seconds": 0,
        }

    minutes: int = int(_get_cfg("MINUTES", 5))
    interval: int = int(_get_cfg("INTERVAL", 60))
    code_length: int = int(_get_cfg("CODE_LENGTH", 6))
    code_type: int = int(_get_cfg("CODE_TYPE", 1))
    country_code: str = str(_get_cfg("COUNTRY_CODE", "86"))
    scheme_name: Optional[str] = _get_cfg("SCHEME_NAME")
    code_param: str = str(_get_cfg("CODE_PARAM_NAME", "code"))
    min_param: str = str(_get_cfg("MIN_PARAM_NAME", "min"))
    valid_time_sec: int = minutes * 60

    out_id = str(uuid.uuid4())
    template_param = json.dumps({min_param: str(minutes), code_param: "##code##"}, ensure_ascii=False)

    try:
        client = _create_client()
        req = dypns_models.SendSmsVerifyCodeRequest(
            phone_number=phone,
            sign_name=sign_name,
            template_code=template_code,
            template_param=template_param,
            country_code=country_code,
            scheme_name=scheme_name,
            out_id=out_id,
            interval=interval,
            valid_time=valid_time_sec,
            code_length=code_length,
            code_type=code_type,
            return_verify_code=False,
        )
        runtime = util_models.RuntimeOptions()
        resp = client.send_sms_verify_code_with_options(req, runtime)
        body = getattr(resp, "body", None)
        success = bool(getattr(body, "success", False))
        code = getattr(body, "code", "")
        message = getattr(body, "message", "")
        biz_id: Optional[str] = None
        model = getattr(body, "model", None)
        if model is not None:
            biz_id = getattr(model, "biz_id", None)

        if success:
            _mark_sent(phone)
            return {"success": True, "message": "验证码已发送", "biz_id": biz_id, "out_id": out_id, "wait_seconds": 0}
        else:
            return {"success": False, "message": message or f"发送失败 ({code})", "biz_id": None, "out_id": out_id, "wait_seconds": 0}
    except Exception as exc:
        return {"success": False, "message": f"发送失败：{exc}", "biz_id": None, "out_id": "", "wait_seconds": 0}


def check_verify_code(phone: str, code: str) -> dict:
    """
    核验短信验证码。

    返回:
        {
          "success": bool,
          "message": str,
          "verify_result": str | None,  # "PASS" | "UNKNOWN" | None
        }
    """
    from alibabacloud_dypnsapi20170525 import models as dypns_models
    from alibabacloud_tea_util import models as util_models

    country_code: str = str(_get_cfg("COUNTRY_CODE", "86"))
    scheme_name: Optional[str] = _get_cfg("SCHEME_NAME")

    try:
        client = _create_client()
        req = dypns_models.CheckSmsVerifyCodeRequest(
            phone_number=phone,
            verify_code=code,
            country_code=country_code,
            scheme_name=scheme_name,
            case_auth_policy=2,
        )
        runtime = util_models.RuntimeOptions()
        resp = client.check_sms_verify_code_with_options(req, runtime)
        body = getattr(resp, "body", None)
        model = getattr(body, "model", None)
        verify_result: Optional[str] = getattr(model, "verify_result", None) if model else None

        if verify_result == "PASS":
            return {"success": True, "message": "验证成功", "verify_result": verify_result}
        else:
            return {"success": False, "message": "验证码错误或已过期", "verify_result": verify_result}
    except Exception as exc:
        # 尝试从异常中提取 code 字段，给出友好提示而不暴露 SDK 原始错误
        exc_str = str(exc)
        print(f"[SMS] check_verify_code error: {exc_str}", flush=True)
        code_hint = ""
        try:
            data = getattr(exc, "data", None) or {}
            code_hint = str(data.get("Code", "") or data.get("code", ""))
        except Exception:
            pass
        if not code_hint:
            # 从原始异常字符串中提取 code 字段（兜底）
            import re as _re
            m = _re.search(r"['\"]Code['\"]\s*:\s*['\"]([^'\"]+)['\"]", exc_str, _re.I)
            if m:
                code_hint = m.group(1)
        if code_hint and "validate" in code_hint.lower():
            msg = "验证码错误或已过期"
        else:
            msg = "验证码校验失败，请稍后重试"
        return {"success": False, "message": msg, "verify_result": None}
