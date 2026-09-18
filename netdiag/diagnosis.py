# -*- coding: utf-8 -*-
"""综合诊断模块：按顺序组合各项检测，自动推断原因并生成修复建议。"""

from __future__ import annotations

from typing import Any, Dict, List

from . import connectivity, dns_diagnosis, network_info, port_check, speed_test, traceroute
from .common import STATUS_FAIL, STATUS_OK, STATUS_WARN
from .config import DEFAULT_DOMAIN, DEFAULT_PUBLIC_IP


def _section(
    key: str,
    title: str,
    status: str,
    summary: str,
    data: Dict[str, Any] | None = None,
    suggestions: List[str] | None = None,
) -> Dict[str, Any]:
    """生成统一的检测段落结构。"""
    return {
        "key": key,
        "title": title,
        "status": status,
        "summary": summary,
        "data": data or {},
        "suggestions": suggestions or [],
    }


def network_info_section() -> Dict[str, Any]:
    """检测基础网络信息并给出该段状态。"""
    info = network_info.collect_basic_network_info()
    summary = info.get("summary", {})
    primary = info.get("primary", {})
    ipv4 = summary.get("ipv4", "")
    gateway = summary.get("default_gateway", "")
    adapter_status = summary.get("adapter_status", "")

    if not ipv4 or adapter_status != "已连接":
        status = STATUS_FAIL
        text = "本机当前没有可用的活动网卡/IP 地址，请先检查网线、WiFi 或飞行模式。"
        suggestions = [
            "如果使用 WiFi，请确认无线开关已打开并输入正确的 WiFi 密码。",
            "如果使用网线，请重新插拔网线，并观察路由器/网口指示灯是否亮起。",
            "检查键盘或系统设置中是否误开了飞行模式。",
            "打开“设备管理器”，确认网卡驱动没有黄色感叹号；必要时重装网卡驱动。",
        ]
    elif not gateway:
        status = STATUS_WARN
        text = "本机已获取 IP，但没有识别到默认网关，网络可能仍无法正常上网。"
        suggestions = [
            "右键任务栏网络图标，选择“网络和 Internet 设置”并运行网络疑难解答。",
            "打开命令行执行 ipconfig /release 后执行 ipconfig /renew，重新获取 IP。",
            "确认路由器 DHCP 服务已开启，并检查路由器是否断电或死机。",
        ]
    else:
        status = STATUS_OK
        text = (
            f"主网卡“{summary.get('adapter_name', '')}”已连接，"
            f"本机 IP {ipv4}，网关 {gateway}。"
        )
        suggestions = ["基础网络配置正常，无需处理。"]

    return _section(
        key="network_info",
        title="基础网络信息",
        status=status,
        summary=text,
        data=info,
        suggestions=suggestions,
    )


def _ping_section(key: str, title: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """把 ping 结果转换成报告段落，并补充针对性建议。"""
    target = result.get("target", "")
    target_type = result.get("target_type", "目标")
    loss = result.get("loss_rate", 0)
    avg = result.get("avg_latency_ms")
    latency_text = f"{avg:.1f} ms" if avg is not None else "无法统计"
    summary = (
        f"ping {target}（{target_type}）：成功 {result.get('success_count', 0)}/"
        f"{result.get('count', 0)} 次，丢包率 {loss:.0f}%，平均延迟 {latency_text}。"
    )
    status = result.get("status", STATUS_FAIL)
    suggestions: List[str] = []

    if status == STATUS_FAIL:
        suggestions = _ping_fail_suggestions(target_type)
    elif status == STATUS_WARN:
        suggestions = [
            f"对 {target_type} 的 ping 存在丢包或高延迟，线路质量可能不稳定。",
            "先重启路由器，再用有线方式测试；若仍异常，联系宽带运营商检查线路。",
        ]
    else:
        suggestions = [f"{target_type}连接正常。"]

    return _section(
        key=key,
        title=title,
        status=status,
        summary=summary,
        data=result,
        suggestions=suggestions,
    )


def _ping_fail_suggestions(target_type: str) -> List[str]:
    """针对不同 ping 目标给出用户看得懂的修复步骤。"""
    if target_type == "网关":
        return [
            "检查网线是否松动、水晶头是否插好；使用 WiFi 时确认是否连到了自家路由器。",
            "观察路由器电源灯、LAN/WAN 灯是否正常；先重启路由器，等待 2 分钟。",
            "如果系统显示“未识别的网络”，可执行 ipconfig /release 和 ipconfig /renew。",
            "以上操作无效时，打开“网络连接”右键网卡“禁用”再“启用”，或重装网卡驱动。",
        ]
    if target_type == "公网IP":
        return [
            "内网/路由器已经可达，但公网不通，常见原因是路由器没有拨号上网成功。",
            "登录路由器管理页（常见 192.168.1.1 或 192.168.0.1），查看 WAN 口是否获取到 IP。",
            "检查光猫指示灯：PON/LOS 灯闪烁或变红通常代表运营商线路或账号异常。",
            "重启光猫和路由器；仍不能上网时直接联系宽带运营商报障。",
        ]
    if target_type == "域名":
        return [
            "如果公网 IP 能 ping 通但域名不通，优先怀疑 DNS 配置错误。",
            "打开命令行执行 ipconfig /flushdns 清空 DNS 缓存。",
            "把网卡 DNS 改为 114.114.114.114（备用 8.8.8.8）后重新测试。",
            "如果只有个别网站打不开，可能是网站自身故障，可稍后重试或更换浏览器。",
        ]
    return [
        "检查当前网络连接状态和路由器是否正常。",
        "重启路由器或让系统重新获取 IP，然后重试。",
    ]


def connectivity_sections() -> List[Dict[str, Any]]:
    """检测网关、公网 IP 和域名三个 ping 目标。"""
    info = network_info.collect_basic_network_info()
    gateway = info.get("summary", {}).get("default_gateway", "")
    sections: List[Dict[str, Any]] = []

    if gateway:
        gateway_result = connectivity.ping_target(
            gateway, target_type="网关"
        )
    else:
        gateway_result = {
            "target": "（未检测到网关）",
            "target_type": "网关",
            "count": 0,
            "success_count": 0,
            "loss_rate": 100.0,
            "avg_latency_ms": None,
            "status": STATUS_FAIL,
            "reachable": False,
        }
    sections.append(
        _ping_section(
            "ping_gateway",
            "连通性检测：网关",
            gateway_result,
        )
    )

    public_result = connectivity.ping_public_ip(DEFAULT_PUBLIC_IP)
    sections.append(
        _ping_section(
            "ping_public_ip",
            "连通性检测：公网 IP",
            public_result,
        )
    )

    domain_result = connectivity.ping_domain(DEFAULT_DOMAIN)
    sections.append(
        _ping_section(
            "ping_domain",
            "连通性检测：域名",
            domain_result,
        )
    )
    return sections


def dns_section(domain: str = DEFAULT_DOMAIN) -> Dict[str, Any]:
    """执行 DNS 解析对比诊断。"""
    result = dns_diagnosis.diagnose_dns(domain)
    return _section(
        key="dns",
        title=f"DNS 诊断（{domain}）",
        status=result.get("status", STATUS_WARN),
        summary=result.get("summary", ""),
        data=result,
        suggestions=result.get("suggestions", []),
    )


def port_section() -> Dict[str, Any]:
    """检测 80/443/53 常用端口。"""
    result = port_check.check_common_ports()
    suggestions: List[str] = []
    failed = [item for item in result["results"] if not item["open"]]
    for item in failed:
        if item["service"] == "DNS":
            suggestions.append(
                f"{item['host']}:53 的 TCP 端口未开放；部分 DNS 服务器不支持 TCP 查询，"
                "可改用 UDP DNS 诊断结果判断是否真的异常。"
            )
        else:
            suggestions.append(
                f"{item['service']} 端口 {item['port']} 未开放：请检查本机防火墙、"
                "代理软件以及路由器/运营商是否拦截了该端口。"
            )
    if not failed:
        suggestions = ["常用端口检测全部通过，HTTP、HTTPS 和 DNS 端口可以正常连接。"]
    return _section(
        key="ports",
        title="端口与服务检测",
        status=result["status"],
        summary=result["summary"],
        data=result,
        suggestions=suggestions,
    )


def custom_port_section(host: str, port: int) -> Dict[str, Any]:
    """检测用户自定义的主机与端口，返回统一报告段落。"""
    result = port_check.check_custom_tcp_port(host, port)
    if result["open"]:
        status = STATUS_OK
        summary = f"{host}:{port} 可以连接，端口已开放。"
        suggestions = ["该端口开放正常。"]
    else:
        status = STATUS_FAIL
        summary = f"{host}:{port} 无法连接：{result['reason']}"
        suggestions = [
            f"目标 {host} 可能未开放端口 {port}，请先确认服务端程序已启动。",
            "检查本机防火墙是否拦截了对外连接，必要时临时关闭防火墙测试。",
            "如果目标在公网，确认路由器已做端口映射或 NAT 配置。",
        ]
    return _section(
        key="custom_port",
        title=f"自定义端口检测（{host}:{port}）",
        status=status,
        summary=summary,
        data=result,
        suggestions=suggestions,
    )


def traceroute_section(destination: str = DEFAULT_DOMAIN) -> Dict[str, Any]:
    """执行路由追踪。"""
    result = traceroute.run_traceroute(destination)
    suggestions: List[str] = []
    if result["status"] == STATUS_OK:
        suggestions = ["路由路径整体正常。"]
    elif result["status"] == STATUS_WARN:
        abnormal = [
            hop for hop in result["hops"] if hop["status"] in ("丢包", "高延迟", "部分丢包")
        ]
        first = abnormal[0]["hop"] if abnormal else 1
        suggestions = [
            f"异常从第 {first} 跳开始，说明问题位于该段链路或该跳路由器附近。",
            "第 1 跳异常通常与光猫/路由器连接有关，可重启光猫与路由器。",
            "公网中段出现丢包或高延迟多为运营商线路或骨干网波动，建议联系宽带运营商。",
            "若公司/校园网内跳点异常，请联系本单位网络管理员。",
        ]
    else:
        suggestions = [
            "路由无法到达目标，请先确认“公网 IP 检测”是否通过。",
            "检查路由器 WAN 口状态、运营商是否欠费或出现线路故障。",
            "若为公司/校园网络，可能有限制 traceroute 的安全策略，属于正常现象。",
        ]
    return _section(
        key="traceroute",
        title="路由追踪",
        status=result["status"],
        summary=result["summary"],
        data=result,
        suggestions=suggestions,
    )


def speed_section(url: str | None = None) -> Dict[str, Any]:
    """执行下载测速（耗时约几秒到十几秒）。"""
    result = speed_test.run_speed_test() if not url else speed_test.run_speed_test(url)
    return _section(
        key="speed",
        title="下载网速测试",
        status=result["status"],
        summary=result["summary"],
        data={
            "url": result["url"],
            "downloaded_mib": result["downloaded_mib"],
            "elapsed_seconds": result["elapsed_seconds"],
            "average_mbps": result["average_mbps"],
        },
        suggestions=result["suggestions"],
    )


def _analyze(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """根据所有检测段落自动推断问题原因，并汇总修复建议。"""
    by_key = {item["key"]: item for item in sections}
    suggestions: List[str] = []
    analysis_parts: List[str] = []

    info = by_key.get("network_info", {})
    gateway = by_key.get("ping_gateway", {})
    public = by_key.get("ping_public_ip", {})
    domain = by_key.get("ping_domain", {})
    dns = by_key.get("dns", {})
    ports = by_key.get("ports", {})
    trace = by_key.get("traceroute", {})
    speed = by_key.get("speed", {})

    # 按“内网 -> 公网 -> DNS -> 应用端口 -> 线路质量”的顺序推断根因
    if info.get("status") == STATUS_FAIL:
        analysis_parts.append("检测到本机没有可用的活动网卡或 IP 地址，属于本机网络接入问题。")
        suggestions.extend(info.get("suggestions", []))
    elif gateway.get("status") == STATUS_FAIL:
        analysis_parts.append("网关 ping 不通，初步判断为内网连接问题（网线/WiFi/路由器）。")
        suggestions.extend(gateway.get("suggestions", []))
    elif gateway.get("status") == STATUS_WARN:
        analysis_parts.append("网关通信不稳定，网络连接质量可能受网线、WiFi 信号或路由器影响。")
        suggestions.extend(gateway.get("suggestions", []))
    elif public.get("status") == STATUS_FAIL:
        analysis_parts.append("网关正常但公网 IP 不通，初步判断为路由器未联网或运营商线路故障。")
        suggestions.extend(public.get("suggestions", []))
    elif public.get("status") == STATUS_WARN:
        analysis_parts.append("公网通信存在丢包或高延迟，线路质量可能不稳定。")
        suggestions.extend(public.get("suggestions", []))
    elif domain.get("status") == STATUS_FAIL or dns.get("status") == STATUS_FAIL:
        analysis_parts.append("公网 IP 能通但域名不通，初步判断为 DNS 配置或解析问题。")
        for section in (domain, dns):
            suggestions.extend(section.get("suggestions", []))
    elif dns.get("status") == STATUS_WARN:
        analysis_parts.append("DNS 解析结果存在异常或与公共 DNS 不一致，可能存在 DNS 污染/缓存问题。")
        suggestions.extend(dns.get("suggestions", []))

    if ports.get("status") != STATUS_OK:
        analysis_parts.append("部分常用服务端口无法连接，可能与本机防火墙、代理或运营商限制有关。")
        suggestions.extend(ports.get("suggestions", []))
    if trace.get("status") == STATUS_WARN:
        analysis_parts.append("路由路径中存在丢包或高延迟跳点，线路质量可能已变差。")
        suggestions.extend(trace.get("suggestions", []))
    if trace.get("status") == STATUS_FAIL:
        analysis_parts.append("路由追踪未能到达目标，公网链路可能中断或受运营商策略限制。")
        suggestions.extend(trace.get("suggestions", []))
    if speed.get("status") == STATUS_WARN:
        analysis_parts.append("网络可以连通，但下载速度偏低，可能是带宽不足或线路质量问题。")
        suggestions.extend(speed.get("suggestions", []))

    # 去掉自动分析产生的重复建议，再补充最终兜底建议
    unique_suggestions: List[str] = []
    for suggestion in suggestions:
        if suggestion not in unique_suggestions:
            unique_suggestions.append(suggestion)

    if not analysis_parts:
        analysis = "所有基础检测项均通过，当前网络连接基本正常。"
        unique_suggestions = [
            "无需修复。若仍有网页/软件打不开，可尝试重启路由器或联系应用服务商。"
        ]
    else:
        analysis = "；".join(analysis_parts)

    return {
        "analysis": analysis,
        "suggestions": unique_suggestions,
    }


def full_diagnose(
    include_speed_test: bool = False,
    include_traceroute: bool = True,
) -> Dict[str, Any]:
    """一键综合诊断：按顺序执行各项检测并返回汇总结果。"""
    sections: List[Dict[str, Any]] = [network_info_section()]
    print("\n--- 正在检测网络连通性（每个目标 ping 4 次）---")
    sections.extend(connectivity_sections())

    print("\n--- 正在对比系统 DNS 与公共 DNS ---")
    sections.append(dns_section())

    print("\n--- 正在检测常用端口（80/443/53）---")
    sections.append(port_section())

    if include_traceroute:
        print("\n--- 正在执行路由追踪（最多 15 跳）---")
        sections.append(traceroute_section())

    if include_speed_test:
        print("\n--- 正在执行下载测速 ---")
        sections.append(speed_section())

    analysis = _analyze(sections)
    return {
        "sections": sections,
        "analysis": analysis["analysis"],
        "suggestions": analysis["suggestions"],
    }
