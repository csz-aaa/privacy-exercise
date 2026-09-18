# -*- coding: utf-8 -*-
"""端口与服务检测模块：使用 TCP 连接判断指定主机端口是否开放。"""

from __future__ import annotations

import socket
import time
from typing import Any, Dict, List

from .config import COMMON_PORTS, SOCKET_TIMEOUT


def check_tcp_port(
    host: str, port: int, timeout: float = SOCKET_TIMEOUT
) -> Dict[str, Any]:
    """尝试与 (host, port) 建立 TCP 连接，判断端口是否开放。

    参数:
        host: 目标主机，可以是 IP 或域名。
        port: 目标端口。
        timeout: 连接超时时间（秒），默认 2 秒。

    返回:
        {"host", "port", "open", "elapsed_ms", "reason"}
    """
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = round((time.monotonic() - start) * 1000, 2)
            return {
                "host": host,
                "port": port,
                "open": True,
                "elapsed_ms": elapsed,
                "reason": "",
            }
    except socket.timeout:
        reason = f"连接超时（{timeout:.0f} 秒内无响应）"
    except ConnectionRefusedError:
        reason = "目标主动拒绝连接"
    except OSError as exc:
        reason = f"网络错误：{exc}"

    elapsed = round((time.monotonic() - start) * 1000, 2)
    return {
        "host": host,
        "port": port,
        "open": False,
        "elapsed_ms": elapsed,
        "reason": reason,
    }


def check_common_ports(timeout: float = SOCKET_TIMEOUT) -> Dict[str, Any]:
    """检测常用服务端口：80(HTTP)、443(HTTPS)、53(DNS)。

    80/443 默认检查 www.baidu.com，53 默认检查 114.114.114.114。
    每个端口的检测结果独立保存，便于用户看到具体哪一项失败。
    """
    results: List[Dict[str, Any]] = []
    for service, (host, port) in COMMON_PORTS.items():
        result = check_tcp_port(host, port, timeout=timeout)
        results.append(
            {
                "service": service,
                "host": host,
                **result,
            }
        )

    opened = sum(1 for item in results if item["open"])
    if opened == len(results):
        status = "正常"
    elif opened == 0:
        status = "异常"
    else:
        status = "警告"

    return {
        "status": status,
        "results": results,
        "summary": f"端口检测完成：{opened}/{len(results)} 个端口可以连接。",
    }


def check_custom_tcp_port(
    host: str, port: int, timeout: float = SOCKET_TIMEOUT
) -> Dict[str, Any]:
    """检测用户自定义的 IP/域名与端口，方便扩展更多服务检测。"""
    return check_tcp_port(host, port, timeout=timeout)

