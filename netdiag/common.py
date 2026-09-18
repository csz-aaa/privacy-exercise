# -*- coding: utf-8 -*-
"""公共工具函数：安全执行外部命令、统一状态、格式辅助。"""

from __future__ import annotations

import platform
import locale
import subprocess
import time
from typing import Any, Dict, List

# 三级检测状态，报告、菜单和自动诊断共用
STATUS_OK = "正常"
STATUS_WARN = "警告"
STATUS_FAIL = "异常"

# Windows 下隐藏外部命令弹出的黑色控制台窗口
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_command(
    args: List[str], timeout: float = 10.0
) -> Dict[str, Any]:
    """安全运行外部命令并返回结构化结果。

    这里统一使用 subprocess.run，严格禁止 os.system，以避免命令注入和
    弹出无关窗口。返回的字典包含执行结果、返回码、标准输出和错误信息。

    参数:
        args: 命令参数列表，例如 ["ping", "-n", "1", "8.8.8.8"]。
        timeout: 整个命令允许执行的最长时间（秒）。

    返回:
        {
            "ok": 是否成功执行并正常结束,
            "returncode": 进程返回码,
            "stdout": 标准输出文本,
            "stderr": 标准错误文本,
            "elapsed_ms": 命令耗时（毫秒）,
            "error": 命令不存在、超时或权限不足时的友好说明
        }
    """
    start = time.monotonic()
    result: Dict[str, Any] = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "elapsed_ms": 0.0,
        "error": "",
    }

    try:
        kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": False,
            "shell": False,
        }
        if CREATE_NO_WINDOW:
            kwargs["creationflags"] = CREATE_NO_WINDOW

        completed = subprocess.run(args, timeout=timeout, **kwargs)
        result.update(
            {
                "ok": True,
                "returncode": completed.returncode,
                "stdout": _decode_command_output(completed.stdout),
                "stderr": _decode_command_output(completed.stderr),
                "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            }
        )
    except FileNotFoundError:
        result["error"] = f"找不到命令：{args[0]}，请先安装或检查系统 PATH。"
    except PermissionError:
        result["error"] = "权限不足，无法执行该命令，请尝试以管理员身份运行。"
    except subprocess.TimeoutExpired:
        result["error"] = f"命令执行超时（超过 {timeout:.0f} 秒）：{' '.join(args)}"
    except OSError as exc:
        result["error"] = f"命令执行失败：{exc}"

    result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
    return result


def _decode_command_output(raw_bytes: bytes | None) -> str:
    """把外部命令输出解码为文本。

    Windows 中文版系统里的 ping/ipconfig 输出通常使用本地 ANSI 编码
    （如 GBK），不能假设一定是 UTF-8，所以先按系统本地编码解码，
    失败时再退回 UTF-8。
    """
    if not raw_bytes:
        return ""

    preferred = locale.getpreferredencoding(False)
    candidates = [
        preferred,
        "utf-8",
        "gbk",      # 中文版 Windows 的本地 ANSI 编码
        "cp1252",   # 部分西文 Windows 的本地 ANSI 编码
    ]
    encodings: List[str] = []
    for item in candidates:
        if item and item.lower() not in [existing.lower() for existing in encodings]:
            encodings.append(item)

    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def status_from_ping(loss_rate: float, avg_latency_ms: float) -> str:
    """根据丢包率和平均延迟给出“正常/警告/异常”三级状态。"""
    if loss_rate >= 100:
        return STATUS_FAIL
    if loss_rate > 0 or avg_latency_ms >= 200:
        return STATUS_WARN
    return STATUS_OK


def format_speed_mbps(byte_count: float, elapsed_seconds: float) -> float:
    """把下载字节数和耗时换算成 Mbps（兆比特每秒）。"""
    if elapsed_seconds <= 0:
        return 0.0
    return round(byte_count * 8 / elapsed_seconds / 1_000_000, 2)


def friendly_os_name() -> str:
    """返回便于用户阅读的操作系统名称。"""
    return platform.platform()
