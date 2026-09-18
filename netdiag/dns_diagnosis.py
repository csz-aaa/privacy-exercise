# -*- coding: utf-8 -*-
"""DNS 诊断模块。

1. 使用 socket.gethostbyname_ex 获取系统 DNS 的解析结果。
2. 使用轻量 UDP DNS 查询对比公共 DNS（114.114.114.114、8.8.8.8）。
3. 判断是否存在解析失败、解析超时或疑似 DNS 污染。

为保持零第三方依赖，模块自带一个极简 DNS 报文编解码实现。
"""

from __future__ import annotations

import random
import socket
import struct
import threading
import time
from typing import Any, Dict, List, Tuple

from .config import (
    DEFAULT_DOMAIN,
    DNS_RETRY_TIMES,
    PUBLIC_DNS_SERVERS,
    SYSTEM_DNS_TIMEOUT,
)


def _encode_dns_name(domain: str) -> bytes:
    """把域名编码成 DNS 报文中的 QNAME 格式。"""
    domain = domain.rstrip(".")
    output = bytearray()
    for label in domain.split("."):
        raw = label.encode("ascii")
        if not raw or len(raw) > 63:
            raise ValueError(f"域名标签不合法：{label}")
        output.append(len(raw))
        output.extend(raw)
    output.append(0)
    return bytes(output)


def _read_dns_name(packet: bytes, offset: int) -> Tuple[str, int]:
    """解析 DNS 名称，支持压缩指针，返回（名称, 下一字段偏移）。"""
    labels: List[str] = []
    end_offset: int | None = None
    visited: set[int] = set()

    while True:
        if offset >= len(packet):
            raise ValueError("DNS 报文格式错误：名称越界")
        if offset in visited:
            raise ValueError("DNS 报文格式错误：压缩指针出现循环")
        visited.add(offset)

        length = packet[offset]
        if length & 0xC0 == 0xC0:
            # 压缩指针占用两个字节，指向报文中的另一处名称
            if offset + 1 >= len(packet):
                raise ValueError("DNS 报文格式错误：压缩指针越界")
            if end_offset is None:
                end_offset = offset + 2
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            offset = pointer
            continue

        if length == 0:
            offset += 1
            if end_offset is None:
                end_offset = offset
            break

        offset += 1
        if offset + length > len(packet):
            raise ValueError("DNS 报文格式错误：标签越界")
        try:
            labels.append(packet[offset : offset + length].decode("ascii"))
        except UnicodeDecodeError as exc:
            raise ValueError("DNS 报文包含非 ASCII 标签") from exc
        offset += length

    return ".".join(labels), end_offset if end_offset is not None else offset


def _query_dns_server(
    domain: str, server: str, timeout: float = 2.0
) -> Tuple[List[str], str]:
    """向指定 DNS 服务器发送 A 记录查询，返回（IP列表, 错误说明）。"""
    transaction_id = random.getrandbits(16)
    qname = _encode_dns_name(domain)
    query = (
        struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
        + qname
        + struct.pack("!HH", 1, 1)  # A 记录，IN 类
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query, (server, 53))
        packet, _ = sock.recvfrom(512)
    except socket.timeout:
        return [], "查询超时"
    except OSError as exc:
        return [], f"网络错误：{exc}"
    finally:
        sock.close()

    try:
        ips = _parse_dns_response(packet, transaction_id)
    except ValueError as exc:
        return [], str(exc)
    return ips, ""


def _parse_dns_response(packet: bytes, expected_id: int) -> List[str]:
    """解析 DNS 应答报文，返回其中全部 IPv4 A 记录。"""
    if len(packet) < 12:
        raise ValueError("DNS 应答报文过短")

    transaction_id, flags, question_count, answer_count, _, _ = struct.unpack(
        "!HHHHHH", packet[:12]
    )
    if transaction_id != expected_id:
        raise ValueError("DNS 应答事务 ID 不匹配")
    if not (flags & 0x8000):
        raise ValueError("该报文不是 DNS 应答")

    rcode = flags & 0x000F
    if rcode != 0:
        error_names = {
            1: "格式错误",
            2: "服务器故障",
            3: "域名不存在（NXDOMAIN）",
            4: "服务器不支持该查询类型",
            5: "服务器拒绝查询",
        }
        raise ValueError(error_names.get(rcode, f"DNS 返回错误码 {rcode}"))

    offset = 12
    # 跳过问题区
    for _ in range(question_count):
        _, offset = _read_dns_name(packet, offset)
        offset += 4  # QTYPE + QCLASS

    ips: List[str] = []
    # 读取回答区
    for _ in range(answer_count):
        _, offset = _read_dns_name(packet, offset)
        if offset + 10 > len(packet):
            raise ValueError("DNS 应答报文回答区越界")
        record_type, _, _, record_length = struct.unpack(
            "!HHIH", packet[offset : offset + 10]
        )
        offset += 10
        if offset + record_length > len(packet):
            raise ValueError("DNS 应答报文记录数据越界")
        if record_type == 1 and record_length == 4:
            ips.append(socket.inet_ntoa(packet[offset : offset + 4]))
        offset += record_length
    return ips


def _resolve_system(domain: str, timeout: float = SYSTEM_DNS_TIMEOUT) -> Dict[str, Any]:
    """调用系统 DNS 解析域名。

    socket.gethostbyname_ex 本身没有超时参数，这里放在守护线程中执行，
    由主线程控制等待时间，避免某个 DNS 服务器无响应时卡住整个工具。
    """
    result: Dict[str, Any] = {"ok": False, "ips": [], "error": ""}

    def worker() -> None:
        try:
            _, _, addresses = socket.gethostbyname_ex(domain)
            result["ips"] = addresses
            result["ok"] = bool(addresses)
            result["error"] = "" if addresses else "系统 DNS 未返回任何地址"
        except socket.gaierror as exc:
            result["error"] = f"系统 DNS 解析失败：{exc}"
        except OSError as exc:
            result["error"] = f"系统 DNS 解析出错：{exc}"

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        result["error"] = "系统 DNS 解析超时"
    return result


def resolve_with_server(
    domain: str,
    dns_server: str,
    timeout: float = 2.0,
    retries: int = DNS_RETRY_TIMES,
) -> Dict[str, Any]:
    """使用指定的公共 DNS 服务器解析域名。

    参数:
        domain: 要解析的域名。
        dns_server: DNS 服务器 IP。
        timeout: 单次 UDP 查询超时（秒）。
        retries: 失败时的重试次数。

    返回:
        {"server", "ok", "ips", "elapsed_ms", "error"}
    """
    start = time.monotonic()
    last_error = "未知错误"
    for _ in range(retries):
        try:
            ips, error = _query_dns_server(domain, dns_server, timeout)
            if not error:
                return {
                    "server": dns_server,
                    "ok": bool(ips),
                    "ips": ips,
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
                    "error": "" if ips else "服务器返回空结果",
                }
            last_error = error
        except ValueError as exc:
            last_error = str(exc)

    return {
        "server": dns_server,
        "ok": False,
        "ips": [],
        "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
        "error": last_error,
    }


def diagnose_dns(
    domain: str = DEFAULT_DOMAIN,
    public_servers: tuple[str, ...] = PUBLIC_DNS_SERVERS,
) -> Dict[str, Any]:
    """对比系统 DNS 与公共 DNS 的解析结果并给出诊断结论。

    判断规则：
    - 系统 DNS 都解析失败 => DNS 配置或解析链路异常。
    - 系统可解析、公共 DNS 无法访问 => 外网或 UDP 53 端口受限，给出警告。
    - 系统 IP 与公共 DNS 结果不一致 => 疑似 DNS 污染或本地缓存错误。
    - 结果一致或至少存在交集 => DNS 基本正常。
    """
    system_result = _resolve_system(domain)
    public_results = [
        resolve_with_server(domain, server) for server in public_servers
    ]
    verified_results = [item for item in public_results if item["ok"]]
    expected_ips: List[str] = []
    for item in verified_results:
        for ip in item["ips"]:
            if ip not in expected_ips:
                expected_ips.append(ip)

    data = {
        "domain": domain,
        "system": system_result,
        "public_dns": public_results,
        "expected_ips": expected_ips,
    }

    if not system_result["ok"]:
        return {
            **data,
            "status": "异常",
            "pollution_suspected": False,
            "summary": f"系统 DNS 无法解析 {domain}：{system_result['error']}",
            "suggestions": [
                "打开“控制面板 -> 网络和 Internet -> 网络连接”，右键当前网卡选“属性”。",
                "双击“Internet 协议版本 4 (TCP/IPv4)”，将 DNS 改为“使用下面的 DNS 服务器地址”。",
                "首选 DNS 填 114.114.114.114，备用 DNS 填 8.8.8.8，然后点击确定。",
                "如仍未恢复，执行“ipconfig /flushdns”清空 DNS 缓存并重启网卡。",
            ],
        }

    if not verified_results:
        return {
            **data,
            "status": "警告",
            "pollution_suspected": False,
            "summary": "系统 DNS 可以解析，但公共 DNS 均无法访问，可能外网或 UDP 53 端口受限。",
            "suggestions": [
                "先确认公网是否连通：ping 8.8.8.8。",
                "如果公网不通，请重启路由器或联系宽带运营商。",
                "如果公网正常，检查路由器或防火墙是否拦截了到公共 DNS 的 UDP 53 流量。",
            ],
        }

    system_ips = set(system_result["ips"])
    expected_set = set(expected_ips)
    if system_ips and not (system_ips & expected_set):
        return {
            **data,
            "status": "警告",
            "pollution_suspected": True,
            "summary": "系统 DNS 解析结果与多个公共 DNS 不一致，疑似 DNS 污染或本地 DNS 缓存错误。",
            "suggestions": [
                "在命令行执行：ipconfig /flushdns，清空本地 DNS 缓存后重试。",
                "把网卡 DNS 手动改成 114.114.114.114 和 8.8.8.8。",
                "如果仍然返回异常结果，可能是运营商 DNS 被污染，建议开启 DoH（DNS over HTTPS）。",
            ],
        }

    return {
        **data,
        "status": "正常",
        "pollution_suspected": False,
        "summary": f"{domain} 可正常解析，系统 DNS 与公共 DNS 结果一致或存在交集。",
        "suggestions": [
            "当前 DNS 配置基本正常，无需处理。",
            "若只是偶尔打不开网页，可先刷新 DNS 缓存并重启浏览器。",
        ],
    }

