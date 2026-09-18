# -*- coding: utf-8 -*-
"""简化版路由追踪模块。

Windows 调用系统 tracert；Linux/macOS 调用 traceroute。所有外部命令
都通过 subprocess 执行。最多追踪 15 跳，并标出高延迟或丢包的跳点。
"""

from __future__ import annotations

import platform
import re
import socket
from statistics import mean
from typing import Any, Dict, List, Optional

from .common import run_command
from .config import (
    DEFAULT_DOMAIN,
    HIGH_LATENCY_THRESHOLD_MS,
    TRACEROUTE_MAX_HOPS,
    TRACEROUTE_TIMEOUT,
)


def _build_command(
    destination: str, max_hops: int, timeout: float
) -> List[str]:
    """根据操作系统构造 tracert/traceroute 命令。"""
    system = platform.system().lower()
    if "windows" in system:
        return [
            "tracert",
            "-d",  # 不解析路由器主机名，避免 DNS 等待
            "-h",
            str(max_hops),
            "-w",
            str(max(1, int(timeout * 1000))),
            destination,
        ]
    # Linux/macOS：-n 不反查域名，-q 1 每跳只发一个探测包
    return [
        "traceroute",
        "-n",
        "-m",
        str(max_hops),
        "-q",
        "1",
        "-w",
        str(timeout),
        destination,
    ]


def _parse_hop_line(line: str) -> Optional[Dict[str, Any]]:
    """解析 tracert 输出中的一行，返回跳点信息或 None。"""
    stripped = line.strip()
    hop_match = re.match(r"^(\d+)\s+(.*)$", stripped)
    if not hop_match:
        return None

    hop_number = int(hop_match.group(1))
    rest = hop_match.group(2)
    if hop_number > 99:
        return None

    # 兼容英文 ms 与中文“毫秒”
    latency_tokens = re.findall(
        r"(?:(?:<1)|(?:\d+(?:\.\d+)?))\s*(?:ms|毫秒)", rest, re.I
    )
    latencies: List[Optional[float]] = []
    for token in latency_tokens:
        value = re.sub(r"\s*(?:ms|毫秒)$", "", token, flags=re.I)
        if value.startswith("<"):
            latencies.append(0.0)
        else:
            try:
                latencies.append(float(value))
            except ValueError:
                latencies.append(None)

    # Windows 的 tracert 每跳最多 3 个探测结果，缺失项用 * 表示
    lost_count = len(re.findall(r"(?<!\w)\*(?!\w)", rest))

    ip_match = re.search(r"(?<!\d)(\d{1,3}\.){3}\d{1,3}(?!\d)", rest)
    return {
        "hop": hop_number,
        "ip": ip_match.group(0) if ip_match else "",
        "latencies_ms": latencies,
        "lost_count": lost_count,
    }


def _annotate_hop(
    hop: Dict[str, Any], destination_ip: str
) -> Dict[str, Any]:
    """给单个跳点标注状态：正常、丢包、高延迟或到达目标。"""
    actual = [value for value in hop["latencies_ms"] if value is not None]
    avg = round(mean(actual), 2) if actual else None
    hop["avg_latency_ms"] = avg
    hop["loss_count"] = hop.pop("lost_count", 0)

    if hop["ip"] == destination_ip:
        hop["status"] = "到达目标"
    elif avg is None and hop["ip"] == "":
        hop["status"] = "丢包"
    elif avg is not None and avg >= HIGH_LATENCY_THRESHOLD_MS:
        hop["status"] = "高延迟"
    elif hop["loss_count"] > 0:
        hop["status"] = "部分丢包"
    else:
        hop["status"] = "正常"
    return hop


def run_traceroute(
    destination: str = DEFAULT_DOMAIN,
    max_hops: int = TRACEROUTE_MAX_HOPS,
    timeout: float = TRACEROUTE_TIMEOUT,
) -> Dict[str, Any]:
    """执行简化版路由追踪并解析结果。

    参数:
        destination: 目标域名或 IP。
        max_hops: 最多追踪跳数，默认 15。
        timeout: 每跳超时时间（秒），默认 2 秒。

    返回:
        {
            "destination", "destination_ip", "hops", "status",
            "summary", "completed", "error"
        }
    """
    # 先解析目标 IP，用于判断是否真正到达
    destination_ip = ""
    try:
        destination_ip = socket.gethostbyname(destination)
    except (socket.gaierror, OSError):
        destination_ip = ""

    command = _build_command(destination, max_hops, timeout)
    # Windows 每跳最多探测 3 次，因此预留较充裕的总超时时间
    command_timeout = max_hops * (timeout * 3 + 3) + 20
    raw = run_command(command, timeout=command_timeout)
    hops: List[Dict[str, Any]] = []
    completed = False
    error = raw.get("error", "")

    if raw["ok"]:
        output = raw["stdout"] or ""
        for line in output.splitlines():
            parsed = _parse_hop_line(line)
            if parsed:
                hops.append(_annotate_hop(parsed, destination_ip))
            lowered = line.lower()
            if (
                "trace complete" in lowered
                or "追踪完成" in lowered
                or "跟踪完成" in lowered
            ):
                completed = True
        # 最后一跳 IP 与目标 IP 相同也视为已到达
        if hops and destination_ip and hops[-1]["ip"] == destination_ip:
            completed = True

    if not raw["ok"]:
        status = "异常"
        summary = f"路由追踪命令执行失败：{error}"
    elif not hops:
        status = "异常"
        summary = "路由追踪未获取到任何跳点，目标可能不可达或网络完全断开。"
    elif not completed:
        status = "异常"
        summary = f"追踪 {destination} 时在 {max_hops} 跳内未能到达目标。"
    else:
        abnormal = [
            hop for hop in hops if hop["status"] in ("丢包", "高延迟", "部分丢包")
        ]
        if abnormal:
            status = "警告"
            marks = "、".join(f"第 {hop['hop']} 跳（{hop['status']}）" for hop in abnormal)
            summary = f"已到达目标，但出现异常跳点：{marks}。"
        else:
            status = "正常"
            summary = f"路由追踪完成，共 {len(hops)} 跳，各跳延迟正常。"

    return {
        "destination": destination,
        "destination_ip": destination_ip,
        "command": command,
        "hops": hops,
        "status": status,
        "summary": summary,
        "completed": completed,
        "error": error,
    }
