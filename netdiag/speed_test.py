# -*- coding: utf-8 -*-
"""简化版网速测试模块：下载约 1MB 文件并计算平均速度。"""

from __future__ import annotations

import time
from typing import Any, Dict
from urllib import error as url_error
from urllib import request as url_request

from .common import format_speed_mbps
from .config import (
    DEFAULT_SPEED_TEST_URL,
    SLOW_SPEED_THRESHOLD_MBPS,
    SPEED_TEST_TARGET_BYTES,
)

CHUNK_SIZE = 64 * 1024
PROGRESS_INTERVAL = 0.2  # 实时速度至少每隔 0.2 秒刷新一次


def run_speed_test(
    url: str = DEFAULT_SPEED_TEST_URL,
    target_bytes: int = SPEED_TEST_TARGET_BYTES,
    connect_timeout: float = 8.0,
) -> Dict[str, Any]:
    """下载一个小文件并显示实时/平均下载速度（Mbps）。

    参数:
        url: 测试文件 URL，默认 Cloudflare 提供的 1MB 文件。
        target_bytes: 目标下载字节数。
        connect_timeout: 建立连接的超时时间（秒）。

    返回:
        包含下载结果和速度的结构化字典。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) network-detector",
    }
    req = url_request.Request(url, headers=headers)

    try:
        start_time = time.monotonic()
        last_print = 0.0
        total_bytes = 0
        with url_request.urlopen(req, timeout=connect_timeout) as response:
            print(f"正在从 {url} 下载测试文件，目标约 {target_bytes / 1024 / 1024:.1f} MiB ...")
            while total_bytes < target_bytes:
                block = response.read(CHUNK_SIZE)
                if not block:
                    break
                total_bytes += len(block)
                elapsed = time.monotonic() - start_time
                now = time.monotonic()
                if now - last_print >= PROGRESS_INTERVAL:
                    realtime_mbps = format_speed_mbps(total_bytes, elapsed)
                    print(
                        f"\r实时速度：{realtime_mbps:>7.2f} Mbps | "
                        f"已下载：{total_bytes / 1024 / 1024:.2f} MiB",
                        end="",
                        flush=True,
                    )
                    last_print = now
        elapsed = time.monotonic() - start_time
        print()
    except url_error.HTTPError as exc:
        return _error_result(
            f"测试服务器返回 HTTP 错误：{exc.code} {exc.reason}", url
        )
    except url_error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return _error_result(f"无法连接测试服务器：{reason}", url)
    except OSError as exc:
        return _error_result(f"下载过程中出现网络错误：{exc}", url)

    average_mbps = format_speed_mbps(total_bytes, elapsed)
    if total_bytes <= 0:
        return _error_result("未能下载到任何数据。", url)

    if average_mbps >= SLOW_SPEED_THRESHOLD_MBPS:
        status = "正常"
        suggestion = "下载速度正常，当前网络带宽足以满足日常网页与视频使用。"
    else:
        status = "警告"
        suggestion = (
            "网络连通，但下载速度偏低。可先重启路由器，再用有线网线直连光猫/路由"
            "重测；若仍慢，请联系宽带运营商确认带宽和线路质量。"
        )

    return {
        "status": status,
        "url": url,
        "downloaded_bytes": total_bytes,
        "downloaded_mib": round(total_bytes / 1024 / 1024, 2),
        "elapsed_seconds": round(elapsed, 2),
        "average_mbps": average_mbps,
        "summary": (
            f"下载 {total_bytes / 1024 / 1024:.2f} MiB 用了 {elapsed:.2f} 秒，"
            f"平均速度 {average_mbps:.2f} Mbps。"
        ),
        "suggestions": [suggestion],
    }


def _error_result(error_text: str, url: str) -> Dict[str, Any]:
    """构造测速失败的统一返回结构。"""
    return {
        "status": "异常",
        "url": url,
        "downloaded_bytes": 0,
        "downloaded_mib": 0.0,
        "elapsed_seconds": 0.0,
        "average_mbps": 0.0,
        "summary": f"网速测试失败：{error_text}",
        "suggestions": [
            "测速失败并不一定代表断网，请先确认当前设备能否打开网页。",
            "检查防火墙、代理软件或路由器的上网限制设置。",
            "如系统提示需要登录认证（如酒店/校园网），请先完成网页认证。",
        ],
    }
