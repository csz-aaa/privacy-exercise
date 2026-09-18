# -*- coding: utf-8 -*-
"""连通性检测模块：通过 ping 检测内网、公网 IP 和域名。"""

from __future__ import annotations

import platform
import re
import time
from typing import Any, Dict, List, Optional

from .common import run_command, status_from_ping
from .config import DEFAULT_DOMAIN, DEFAULT_PUBLIC_IP, PING_COUNT, PING_TIMEOUT
from .network_info import collect_basic_network_info


def _ping_once(host: str, timeout: float = PING_TIMEOUT) -> Dict[str, Any]:
    """使用系统 ping 命令发送一次 ICMP 请求。

    返回:
        {
            "reachable": 是否收到回应,
            "latency_ms": 本次延迟（毫秒），没有解析到则为 None,
            "raw": 原始命令输出,
            "error": 执行失败时的说明
        }
    """
    system = platform.system().lower()
    if "windows" in system:
        command = ["ping", "-n", "1", "-w", str(max(1, int(timeout * 1000))), host]
    elif "darwin" in system:
        # macOS 的 -W 参数单位是毫秒
        command = ["ping", "-n", "1", "-W", str(max(1, int(timeout * 1000))), host]
    else:
        # Linux 的 -W 参数单位是秒
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]

    start = time.monotonic()
    raw = run_command(command, timeout=timeout + 1.5)
    elapsed = (time.monotonic() - start) * 1000

    if not raw["ok"]:
        return {
            "reachable": False,
            "latency_ms": None,
            "raw": "",
            "error": raw["error"],
        }
    if raw["returncode"] != 0:
        return {
            "reachable": False,
            "latency_ms": None,
            "raw": raw["stdout"] + raw["stderr"],
            "error": "ping 未收到回复",
        }

    output = raw["stdout"]
    latency = _extract_latency_ms(output, elapsed)
    return {
        "reachable": True,
        "latency_ms": latency,
        "raw": output,
        "error": "",
    }


def _extract_latency_ms(output: str, fallback_ms: float) -> Optional[float]:
    """从 ping 输出中提取延迟，兼容中文/英文以及“<1ms”格式。"""
    match = re.search(
        r"(?:time|时间)\s*[=:<：]\s*<?\s*([0-9]+(?:\.[0-9]+)?)\s*ms",
        output,
        re.I,
    )
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return round(fallback_ms, 2) if fallback_ms else None


def ping_target(
    host: str,
    count: int = PING_COUNT,
    timeout: float = PING_TIMEOUT,
    target_type: str = "其他",
) -> Dict[str, Any]:
    """对目标执行多次 ping，并统计丢包率与平均延迟。

    参数:
        host: 目标主机（网关、公网 IP 或域名）。
        count: ping 次数，默认 4 次。
        timeout: 单次 ping 超时时间，默认 2 秒。
        target_type: 目标类型说明，例如“网关/公网IP/域名”。

    返回:
        包含是否可达、丢包率、平均延迟等字段的结构化字典。
    """
    latencies: List[float] = []
    failures = 0
    errors: List[str] = []

    for attempt in range(count):
        result = _ping_once(host, timeout=timeout)
        if result["reachable"]:
            if result["latency_ms"] is not None:
                latencies.append(result["latency_ms"])
        else:
            failures += 1
            if result.get("error"):
                errors.append(result["error"])
        if attempt < count - 1:
            time.sleep(0.1)

    loss_rate = round(failures * 100.0 / count, 2) if count else 0.0
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
    return {
        "target": host,
        "target_type": target_type,
        "count": count,
        "success_count": count - failures,
        "loss_rate": loss_rate,
        "avg_latency_ms": avg_latency,
        "min_latency_ms": round(min(latencies), 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "reachable": failures == 0,
        "status": status_from_ping(loss_rate, avg_latency or 0.0),
        "errors": errors[:3],
    }


def ping_gateway(count: int = PING_COUNT, timeout: float = PING_TIMEOUT) -> Dict[str, Any]:
    """ping 默认网关，用于判断内网/局域网是否连通。"""
    info = collect_basic_network_info()
    gateway = info.get("summary", {}).get("default_gateway", "")
    if not gateway:
        return {
            "target": "",
            "target_type": "网关",
            "count": 0,
            "success_count": 0,
            "loss_rate": 100.0,
            "avg_latency_ms": None,
            "reachable": False,
            "status": "异常",
            "error": "未能从系统网络信息中获取默认网关",
        }
    return ping_target(gateway, count=count, timeout=timeout, target_type="网关")


def ping_public_ip(
    ip: str = DEFAULT_PUBLIC_IP,
    count: int = PING_COUNT,
    timeout: float = PING_TIMEOUT,
) -> Dict[str, Any]:
    """ping 公网 IP，用于判断是否可以访问互联网。"""
    return ping_target(ip, count=count, timeout=timeout, target_type="公网IP")


def ping_domain(
    domain: str = DEFAULT_DOMAIN,
    count: int = PING_COUNT,
    timeout: float = PING_TIMEOUT,
) -> Dict[str, Any]:
    """ping 域名，用于判断 DNS 解析与网络访问是否正常。"""
    return ping_target(domain, count=count, timeout=timeout, target_type="域名")

