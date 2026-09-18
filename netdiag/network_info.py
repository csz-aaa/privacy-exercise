# -*- coding: utf-8 -*-
"""基础网络信息采集模块。

功能：
1. 获取本机 IP、子网掩码、默认网关、DNS 服务器。
2. 获取网卡名称、MAC 地址、连接状态。
3. 返回结构化字典，供诊断模块和报告模块直接使用。

Windows 使用 ipconfig /all；Linux 使用 ip 命令；macOS 使用 ifconfig。
所有外部命令都通过 subprocess 执行。
"""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import run_command


def _valid_ipv4(value: str) -> bool:
    """判断字符串是否是合法的 IPv4 地址。"""
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def _ipv4_addresses(value: str) -> List[str]:
    """从 ipconfig 返回值中提取全部 IPv4 地址。"""
    result: List[str] = []
    for match in re.finditer(r"(?<!\d)(\d{1,3}\.){3}\d{1,3}(?!\d)", value):
        candidate = match.group(0)
        if _valid_ipv4(candidate) and candidate not in result:
            result.append(candidate)
    return result


def _clean_field_value(value: str) -> str:
    """去掉 ipconfig 字段值中的“(首选)”等说明文字。"""
    cleaned = re.split(r"\s*[（(][^）)]*[)）]", value)[0]
    return cleaned.strip()


def _find_field(chunk: List[str], *key_groups: str) -> str:
    """在 ipconfig 区块中按中英文关键字查找单个字段值。"""
    for raw_line in chunk:
        line = raw_line.strip()
        lower_line = line.lower()
        for key in key_groups:
            if key.lower() in lower_line:
                index = max(line.find(":"), line.find("："))
                if index >= 0:
                    return _clean_field_value(line[index + 1 :])
    return ""


def _find_all_fields(chunk: List[str], *key_groups: str) -> List[str]:
    """在 ipconfig 区块中查找可能重复出现的字段（如 DNS 服务器）。"""
    values: List[str] = []
    for raw_line in chunk:
        line = raw_line.strip()
        lower_line = line.lower()
        for key in key_groups:
            if key.lower() in lower_line:
                index = max(line.find(":"), line.find("："))
                if index >= 0:
                    value = _clean_field_value(line[index + 1 :])
                    if value and value not in values:
                        values.append(value)
    return values


def _windows_adapter_chunks(text: str) -> List[Dict[str, Any]]:
    """把 ipconfig /all 输出切分成“一个网卡一个区块”。"""
    header_regex = re.compile(
        r"(?mi)^[^\r\n]*(?:adapter|适配器)[^\r\n]*[:：]\s*$"
    )
    matches = list(header_regex.finditer(text))
    chunks: List[Dict[str, Any]] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        header = match.group(0).strip().rstrip(":：").strip()
        body_lines = [item for item in body.splitlines() if item.strip()]

        # ipv4、物理地址等字段都允许出现多行，但每个网卡取首次有效值
        ipv4_values: List[str] = []
        for value in _find_all_fields(body_lines, "ipv4 地址", "ipv4 address"):
            for candidate in _ipv4_addresses(value):
                if candidate not in ipv4_values:
                    ipv4_values.append(candidate)

        mac_value = _find_field(body_lines, "物理地址", "physical address").strip()
        media_value = _find_field(body_lines, "媒体状态", "media state").lower()
        is_disconnected = (
            "disconnected" in media_value
            or "未连接" in media_value
            or "断开" in media_value
        )
        is_connected = (
            "connected" in media_value
            or "已连接" in media_value
            or "连接" in media_value
            and "断开" not in media_value
        )

        if media_value:
            status = "已断开" if is_disconnected else "已连接"
        else:
            status = "已连接" if ipv4_values else "已断开"

        if ipv4_values and is_disconnected:
            status = "已断开"
        if is_connected:
            status = "已连接"

        gateway_value = _find_field(
            body_lines, "默认网关", "default gateway"
        ).strip()
        dns_values = [
            item
            for value in _find_all_fields(body_lines, "dns 服务器", "dns servers")
            for item in _ipv4_addresses(value)
        ]
        dns_unique: List[str] = []
        for item in dns_values:
            if item not in dns_unique:
                dns_unique.append(item)

        # 去掉常见前缀得到网卡名称，例如“以太网适配器 以太网” -> “以太网”
        name = _clean_adapter_name(header)
        chunks.append(
            {
                "name": name,
                "mac_address": mac_value or "",
                "status": status,
                "ipv4_addresses": ipv4_values,
                "subnet_mask": _find_field(
                    body_lines, "子网掩码", "subnet mask"
                ).strip(),
                "default_gateway": gateway_value,
                "dns_servers": dns_unique,
            }
        )
    return chunks


def _clean_adapter_name(raw_name: str) -> str:
    """去掉 ipconfig 适配器标题中的固定前缀。"""
    prefixes = [
        "以太网适配器",
        "无线局域网适配器",
        "蓝牙网络连接适配器",
        "隧道适配器",
        "局域网连接",
        "Ethernet adapter",
        "Wireless LAN adapter",
        "Bluetooth Network Connection",
        "Tunnel adapter",
        "Unknown adapter",
    ]
    lowered = raw_name.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            remainder = raw_name[len(prefix) :].strip(" :：\t")
            return remainder or raw_name
    return raw_name


def _collect_windows() -> Dict[str, Any]:
    """采集 Windows 网络信息。"""
    raw = run_command(["ipconfig", "/all"], timeout=10)
    adapters: List[Dict[str, Any]] = []
    if raw["ok"] and raw["returncode"] == 0:
        adapters = _windows_adapter_chunks(raw["stdout"])

    if not adapters:
        # ipconfig 解析失败时仍提供最小可用信息，不让整个流程中断
        adapters = [
            {
                "name": "未知网卡",
                "mac_address": "",
                "status": "未知",
                "ipv4_addresses": [],
                "subnet_mask": "",
                "default_gateway": "",
                "dns_servers": [],
            }
        ]
        if raw["error"]:
            adapters[0]["error"] = raw["error"]

    return {
        "platform": "windows",
        "hostname": socket.gethostname(),
        "adapters": adapters,
    }


def _parse_linux_adapters() -> Dict[str, Any]:
    """解析 Linux 的 ip 命令输出，返回网卡列表与默认网关。"""
    addr_result = run_command(["ip", "-o", "-4", "addr", "show"], timeout=5)
    link_result = run_command(["ip", "-o", "link", "show"], timeout=5)
    route_result = run_command(["ip", "route", "show", "default"], timeout=5)

    # 默认网关对应关系：接口名 -> 网关地址
    gateway_map: Dict[str, str] = {}
    if route_result["ok"]:
        for line in route_result["stdout"].splitlines():
            match = re.match(r"^default\s+via\s+([0-9.]+)\s+dev\s+(\S+)", line)
            if match:
                gateway_map[match.group(2)] = match.group(1)

    # 网卡名称 -> 子网前缀（由 IP/掩码位数得到）
    prefix_map: Dict[str, List[Dict[str, Any]]] = {}
    if addr_result["ok"]:
        for line in addr_result["stdout"].splitlines():
            match = re.search(
                r"^\s*\d+:\s+([^@\s]+).*?inet\s+([0-9.]+)/(\d+)\s*", line
            )
            if match:
                interface, ip_text, prefix_text = match.groups()
                try:
                    network = ipaddress.ip_interface(f"{ip_text}/{prefix_text}")
                    prefix_map.setdefault(interface, []).append(
                        {
                            "ipv4": ip_text,
                            "subnet_mask": str(network.netmask),
                        }
                    )
                except ValueError:
                    continue

    link_state: Dict[str, str] = {}
    link_mac: Dict[str, str] = {}
    if link_result["ok"]:
        for line in link_result["stdout"].splitlines():
            name_match = re.match(r"^\s*\d+:\s+([^@:\s]+):?", line)
            state_match = re.search(r"state\s+(UP|DOWN|UNKNOWN)", line)
            mac_match = re.search(r"link/ether\s+([0-9a-f:]+)", line)
            if name_match:
                interface = name_match.group(1)
                if state_match:
                    link_state[interface] = state_match.group(1)
                if mac_match:
                    link_mac[interface] = mac_match.group(1)

    adapters: List[Dict[str, Any]] = []
    all_interfaces = sorted(set(list(prefix_map.keys()) + list(link_state.keys())))
    for interface in all_interfaces:
        ipv4s = [item["ipv4"] for item in prefix_map.get(interface, [])]
        mask = (
            prefix_map[interface][0]["subnet_mask"]
            if prefix_map.get(interface)
            else ""
        )
        state = link_state.get(interface, "DOWN")
        adapters.append(
            {
                "name": interface,
                "mac_address": link_mac.get(interface, ""),
                "status": "已连接" if state == "UP" else "已断开",
                "ipv4_addresses": ipv4s,
                "subnet_mask": mask,
                "default_gateway": gateway_map.get(interface, ""),
                "dns_servers": _read_resolv_conf(),
            }
        )

    if not adapters and (addr_result["error"] or link_result["error"]):
        raise RuntimeError(
            addr_result["error"] or link_result["error"]
        )
    return {
        "platform": "linux",
        "hostname": socket.gethostname(),
        "adapters": adapters,
    }


def _read_resolv_conf() -> List[str]:
    """读取 Linux/macOS 的 /etc/resolv.conf 中的 DNS 服务器。"""
    servers: List[str] = []
    try:
        content = Path("/etc/resolv.conf").read_text(encoding="utf-8")
        for line in content.splitlines():
            match = re.match(r"^\s*nameserver\s+(\S+)", line, re.I)
            if match:
                servers.append(match.group(1))
    except (OSError, UnicodeDecodeError):
        return []
    return servers


def _parse_macos_adapters() -> Dict[str, Any]:
    """解析 macOS 的 ifconfig 输出，返回网卡列表与默认网关。"""
    raw = run_command(["ifconfig"], timeout=5)
    adapters: List[Dict[str, Any]] = []
    if not (raw["ok"] and raw["returncode"] == 0):
        return {
            "platform": "macos",
            "hostname": socket.gethostname(),
            "adapters": [],
            "error": raw["error"],
        }

    # ifconfig 的区块按“接口名: flags=...”切分
    block_pattern = re.compile(
        r"(?m)^([A-Za-z0-9_.-]+):\s+flags=.*?(?=^[A-Za-z0-9_.-]+:\s+flags=|\Z)"
    )
    for block_match in block_pattern.finditer(raw["stdout"]):
        interface = block_match.group(1)
        block = block_match.group(0)
        ip_match = re.search(r"inet\s+([0-9.]+)", block)
        mask_match = re.search(r"netmask\s+0x([0-9a-fA-F]+)", block)
        mac_match = re.search(r"\b(?:ether|lladdr)\s+([0-9a-f:]+)", block)
        status_match = re.search(r"status:\s*(\w+)", block)

        ipv4 = ip_match.group(1) if ip_match and _valid_ipv4(ip_match.group(1)) else ""
        mask_hex = mask_match.group(1) if mask_match else "0"
        try:
            subnet_mask = socket.inet_ntoa(struct.pack("!I", int(mask_hex, 16)))
        except (OverflowError, struct.error):
            subnet_mask = ""

        state = (status_match.group(1) if status_match else "").lower()
        connected = ipv4 != "" and state not in ("inactive", "down")
        adapters.append(
            {
                "name": interface,
                "mac_address": mac_match.group(1) if mac_match else "",
                "status": "已连接" if connected else "已断开",
                "ipv4_addresses": [ipv4] if ipv4 else [],
                "subnet_mask": subnet_mask,
                "default_gateway": "",
                "dns_servers": _read_resolv_conf(),
            }
        )

    route_result = run_command(["netstat", "-rn", "-f", "inet"], timeout=5)
    gateway = ""
    if route_result["ok"]:
        for line in route_result["stdout"].splitlines():
            match = re.match(r"^default\s+([0-9.]+)", line.strip())
            if match:
                gateway = match.group(1)
                break
    if gateway:
        for adapter in adapters:
            if adapter["status"] == "已连接" and adapter["ipv4_addresses"]:
                adapter["default_gateway"] = gateway
    return {
        "platform": "macos",
        "hostname": socket.gethostname(),
        "adapters": adapters,
    }


def _fallback_info() -> Dict[str, Any]:
    """外部命令不可用时的兜底采集：只获取主机名和本机 IP。"""
    ipv4 = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # UDP connect 不会真正发包，只让内核选择本机出口地址
            sock.connect(("8.8.8.8", 80))
            ipv4 = sock.getsockname()[0]
    except OSError:
        ipv4 = ""
    return {
        "platform": platform.system().lower(),
        "hostname": socket.gethostname(),
        "adapters": [
            {
                "name": "未知网卡",
                "mac_address": "",
                "status": "已连接" if ipv4 else "未知",
                "ipv4_addresses": [ipv4] if ipv4 else [],
                "subnet_mask": "",
                "default_gateway": "",
                "dns_servers": _read_resolv_conf(),
                "error": "系统命令不可用，只采集到部分信息",
            }
        ],
    }


def _choose_primary_adapter(adapters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从网卡列表中选择“最可能正在上网”的主网卡。"""
    candidates: List[Dict[str, Any]] = []
    for adapter in adapters:
        if adapter.get("status") != "已连接":
            continue
        if not adapter.get("ipv4_addresses"):
            continue
        name = adapter.get("name", "").lower()
        if "loopback" in name or "回环" in name:
            continue
        if any(_valid_ipv4(ip) and ip.startswith("127.") for ip in adapter["ipv4_addresses"]):
            continue
        candidates.append(adapter)

    # 优先选有默认网关的网卡，其次选有 IPv4 的网卡
    with_gateway = [item for item in candidates if item.get("default_gateway")]
    return (with_gateway or candidates or [{}])[0]


def collect_basic_network_info() -> Dict[str, Any]:
    """采集本机基础网络信息并返回结构化字典。

    返回的字典结构：
    {
        "platform": 操作系统类型,
        "hostname": 主机名,
        "adapters": 所有网卡信息列表,
        "primary": 当前主网卡信息,
        "summary": 最常用的信息摘要（IP、掩码、网关、DNS 等）
    }

    该函数不依赖第三方库；解析失败时会使用兜底逻辑，保证调用方不崩溃。
    """
    system = platform.system().lower()
    info: Dict[str, Any] = {}
    try:
        if "windows" in system:
            info = _collect_windows()
        elif "linux" in system:
            info = _parse_linux_adapters()
        elif "darwin" in system:
            info = _parse_macos_adapters()
        else:
            info = _fallback_info()
    except (RuntimeError, OSError) as exc:
        info = _fallback_info()
        info["error"] = str(exc)

    primary = _choose_primary_adapter(info.get("adapters", []))
    info["primary"] = primary
    info["summary"] = {
        "hostname": info.get("hostname", ""),
        "adapter_name": primary.get("name", ""),
        "adapter_status": primary.get("status", "未知"),
        "mac_address": primary.get("mac_address", ""),
        "ipv4": (primary.get("ipv4_addresses") or [""])[0],
        "subnet_mask": primary.get("subnet_mask", ""),
        "default_gateway": primary.get("default_gateway", ""),
        "dns_servers": primary.get("dns_servers", []),
        "platform": info.get("platform", ""),
    }
    return info

