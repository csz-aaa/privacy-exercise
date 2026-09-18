# -*- coding: utf-8 -*-
"""无线网络、热点连接与 VPN/代理环境检测。"""

from __future__ import annotations

import os
import platform
import re
from typing import Any, Dict, List

from .common import run_command
from .network_info import collect_basic_network_info

VPN_KEYWORDS = (
    "vpn", "tap", "tun", "wireguard", "tailscale", "zerotier",
    "openvpn", "nordvpn", "expressvpn", "softether",
    "clash", "surge", "shadowsocks", "ssr", "sing-box", "mihomo",
)


def _field_value(line: str) -> str:
    """把 netsh 输出行按冒号拆成字段值。"""
    match = re.search(r"[:：]\s*(.*)$", line.strip())
    return match.group(1).strip() if match else ""


def _percent(value: str) -> int | None:
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return int(float(match.group(0)))
    except ValueError:
        return None


def _find_field(lines: List[str], keyword: str) -> str:
    for raw_line in lines:
        if keyword in raw_line:
            return _field_value(raw_line)
    return ""


def get_wireless_status() -> Dict[str, Any]:
    """读取当前无线网卡的连接信息（Windows 优先）。"""
    system = platform.system().lower()
    if "windows" not in system:
        return {
            "supported": False,
            "connected": False,
            "summary": "当前系统不支持通过 netsh wlan 读取无线状态。",
        }

    raw = run_command(["netsh", "wlan", "show", "interfaces"], timeout=10)
    if not (raw["ok"] and raw["returncode"] == 0):
        return {
            "supported": True,
            "connected": False,
            "summary": "未读取到无线网卡状态，可能没有 WiFi 网卡或无线服务未启动。",
            "error": raw["error"] or raw["stderr"] or raw["stdout"],
        }

    output = raw["stdout"]
    lines = [item.strip() for item in output.splitlines() if item.strip()]
    ssid_raw = _find_field(lines, "SSID")
    ssid = ssid_raw.strip("\"“”") if ssid_raw else ""
    signal_text = _find_field(lines, "信号") or _find_field(lines, "Signal")
    state_text = _find_field(lines, "状态") or _find_field(lines, "State")
    connected = ("已连接" in state_text) or ("connected" in state_text.lower())

    receive = _find_field(lines, "接收速率") or _find_field(lines, "Receive rate")
    transmit = _find_field(lines, "传输速率") or _find_field(lines, "Transmit rate")
    radio = _find_field(lines, "无线电类型") or _find_field(lines, "Radio type")
    channel = _find_field(lines, "通道") or _find_field(lines, "Channel")
    auth = _find_field(lines, "身份验证") or _find_field(lines, "Authentication")
    interface = _find_field(lines, "名称") or _find_field(lines, "Name")

    signal_percent = _percent(signal_text)
    summary = "已连接无线网络" if connected else "当前未连接 WiFi"
    if ssid:
        summary += f"：{ssid}"
    if signal_percent is not None:
        summary += f"，信号约 {signal_percent}%"

    return {
        "supported": True,
        "connected": connected,
        "interface": interface,
        "ssid": ssid,
        "signal_percent": signal_percent,
        "signal_text": signal_text,
        "radio_type": radio,
        "channel": channel,
        "auth": auth,
        "receive_rate_mbps": receive,
        "transmit_rate_mbps": transmit,
        "state": state_text,
        "summary": summary,
    }


def _env_proxy_urls() -> List[str]:
    """读取命令行代理环境变量。"""
    urls: List[str] = []
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(name, "").strip()
        if value and value not in urls:
            urls.append(f"{name}={value}")
    return urls


def _windows_proxy_settings() -> Dict[str, str]:
    """读取 Windows 系统代理设置，不修改任何内容。"""
    result = {
        "enabled": False,
        "server": "",
        "note": "",
    }
    if platform.system().lower() != "windows":
        return result
    base_key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    enabled_raw = run_command(
        ["reg", "query", base_key, "/v", "ProxyEnable"], timeout=5
    )
    if enabled_raw["ok"] and enabled_raw["returncode"] == 0:
        match = re.search(r"ProxyEnable\s+REG_DWORD\s+0x([0-9a-fA-F]+)", enabled_raw["stdout"])
        result["enabled"] = bool(match and int(match.group(1), 16))
    server_raw = run_command(
        ["reg", "query", base_key, "/v", "ProxyServer"], timeout=5
    )
    if server_raw["ok"] and server_raw["returncode"] == 0:
        match = re.search(r"ProxyServer\s+REG_SZ\s+(.+?)\s*$", server_raw["stdout"], re.M)
        result["server"] = match.group(1).strip() if match else ""
    if result["enabled"] and not result["server"]:
        result["note"] = "已开启系统代理，但未读取到代理服务器地址。"
    return result


def _adapter_hits() -> List[str]:
    """从网卡名称中判断是否存在 VPN/隧道类连接。"""
    hits: List[str] = []
    try:
        info = collect_basic_network_info()
    except Exception:
        return hits
    for adapter in info.get("adapters", []):
        name = adapter.get("name", "")
        lowered = name.lower()
        if adapter.get("status") != "已连接":
            continue
        if any(token in lowered for token in ("teredo", "isatap", "6to4", "pseudo-interface")):
            continue
        if any(keyword in lowered for keyword in VPN_KEYWORDS):
            status = adapter.get("status", "未知")
            hits.append(f"{name}（{status}）")
    return hits


def get_vpn_proxy_status() -> Dict[str, Any]:
    """只读取 VPN/代理相关状态，不做任何修改。"""
    proxy = _windows_proxy_settings()
    env_proxies = _env_proxy_urls()
    adapters = _adapter_hits()
    detected = bool(proxy["enabled"] or env_proxies or adapters)

    parts: List[str] = []
    if adapters:
        parts.append("检测到 VPN/虚拟网卡：" + "、".join(adapters))
    if proxy["enabled"]:
        server = proxy["server"] or "未知地址"
        parts.append(f"系统代理已开启（{server}）")
    if env_proxies:
        parts.append("检测到代理环境变量：" + "、".join(env_proxies))
    if not parts:
        parts.append("未检测到明显的 VPN 或代理设置")

    return {
        "detected": detected,
        "adapter_hits": adapters,
        "system_proxy_enabled": proxy["enabled"],
        "system_proxy_server": proxy["server"],
        "proxy_note": proxy["note"],
        "env_proxies": env_proxies,
        "summary": "；".join(parts),
    }


def get_connection_type() -> Dict[str, Any]:
    """识别当前主网卡属于无线还是有线，供报告界面展示。"""
    try:
        info = collect_basic_network_info()
    except Exception:
        return {"kind": "unknown", "summary": "无法识别当前连接类型"}
    primary = info.get("primary", {})
    name = (primary.get("name", "") or "").lower()
    if any(word in name for word in ("wlan", "wi-fi", "wifi", "wireless", "无线")):
        kind = "wifi"
    elif any(word in name for word in ("ethernet", "以太网", "本地连接")):
        kind = "ethernet"
    else:
        kind = "unknown"
    return {
        "kind": kind,
        "adapter_name": primary.get("name", ""),
        "ipv4": (primary.get("ipv4_addresses") or [""])[0],
        "gateway": primary.get("default_gateway", ""),
        "summary": f"当前主网卡：{primary.get('name', '未知')}",
    }


def environment_section() -> Dict[str, Any]:
    """汇总无线/热点、连接类型与 VPN/代理信息，供 GUI 和报告使用。"""
    wifi = get_wireless_status()
    vpn = get_vpn_proxy_status()
    conn = get_connection_type()
    data = {"wireless": wifi, "vpn_proxy": vpn, "connection": conn}

    summary_parts = [conn.get("summary", ""), wifi.get("summary", ""), vpn.get("summary", "")]
    summary = "；".join(item for item in summary_parts if item)
    suggestions: List[str] = []

    signal = wifi.get("signal_percent")
    if wifi.get("connected") and signal is not None and signal <= 40:
        suggestions.append("WiFi 信号较弱，建议靠近路由器/热点再测试，或改用 5GHz 频段。")
    if vpn.get("detected"):
        suggestions.append("检测到 VPN/代理环境，检测结果可能经过代理；建议先临时关闭 VPN 再对比一次。")
    if not wifi.get("connected") and conn.get("kind") == "unknown":
        suggestions.append("当前未识别到 WiFi 连接，可能正在使用有线网络、USB 共享网络或系统无线服务已关闭。")
    if not suggestions:
        suggestions.append("当前网络环境未发现明显异常，可继续运行连通性检测确认上网质量。")

    return {
        "key": "environment",
        "title": "无线/热点与 VPN 环境",
        "status": "正常" if not vpn.get("detected") and (signal is None or signal > 40) else "警告",
        "summary": summary,
        "data": data,
        "suggestions": suggestions,
    }
