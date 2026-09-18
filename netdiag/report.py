# -*- coding: utf-8 -*-
"""报告生成与保存模块：把结构化检测结果输出到屏幕并写入文本文件。"""

from __future__ import annotations

import pprint
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from . import common
from .config import PING_TIMEOUT

# 项目根目录下的 reports 文件夹用于存放检测报告
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "reports"


def _line(char: str = "=", width: int = 72) -> str:
    """生成分隔线。"""
    return char * width


def make_report(
    title: str,
    sections: List[Dict[str, Any]],
    analysis: str = "",
    suggestions: List[str] | None = None,
) -> Dict[str, Any]:
    """把多个检测段落包装成一份完整报告字典。"""
    now = datetime.now()
    return {
        "title": title,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": now.strftime("%Y%m%d_%H%M%S"),
        "hostname": socket.gethostname(),
        "os": common.friendly_os_name(),
        "python_version": __import__("platform").python_version(),
        "sections": sections,
        "analysis": analysis,
        "suggestions": suggestions or [],
    }


def _data_text(data: Any, indent: str = "  ") -> str:
    """把结构化数据转成缩进文本，便于非技术用户阅读。"""
    if data is None:
        return ""
    return pprint.pformat(data, width=100, sort_dicts=False, indent=1)


def render_report(report: Dict[str, Any]) -> str:
    """把报告字典渲染成可打印、可保存的文本。"""
    lines: List[str] = []
    lines.append(_line())
    lines.append(f"  {report['title']}")
    lines.append(_line())
    lines.append(f"生成时间：{report['created_at']}")
    lines.append(f"主机名：{report['hostname']}")
    lines.append(f"操作系统：{report['os']}")
    lines.append(f"Python：{report['python_version']}")
    lines.append("")

    for index, section in enumerate(report["sections"], start=1):
        lines.append(_line("-"))
        lines.append(
            f"[{index}] {section.get('title', '未命名检测项')}  "
            f"状态：{section.get('status', common.STATUS_WARN)}"
        )
        lines.append(f"摘要：{section.get('summary', '')}")
        suggestions = section.get("suggestions") or []
        if suggestions:
            lines.append("修复建议：")
            for i, suggestion in enumerate(suggestions, start=1):
                lines.append(f"  {i}. {suggestion}")
        data = section.get("data")
        if data:
            lines.append("详细数据：")
            lines.append(_data_text(data))
        lines.append("")

    lines.append(_line("="))
    if report.get("analysis"):
        lines.append("综合判断：")
        lines.append(f"  {report['analysis']}")
    if report.get("suggestions"):
        lines.append("总体修复建议：")
        for i, suggestion in enumerate(report["suggestions"], start=1):
            lines.append(f"  {i}. {suggestion}")
    lines.append(_line("="))
    lines.append(f"检测完成，本次使用的单次超时时间为 {PING_TIMEOUT} 秒。")
    return "\n".join(lines)


def print_report(report: Dict[str, Any]) -> None:
    """把报告文本打印到屏幕。"""
    print(render_report(report))


def save_report(report: Dict[str, Any], output_dir: Path | None = None) -> Path:
    """把报告保存为 network_report_时间戳.txt，返回保存路径。"""
    target_dir = output_dir or REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = target_dir / f"network_report_{report['timestamp']}.txt"
    filename.write_text(render_report(report) + "\n", encoding="utf-8")
    return filename


def output_result(
    title: str,
    sections: List[Dict[str, Any]],
    analysis: str = "",
    suggestions: List[str] | None = None,
    output_dir: Path | None = None,
) -> Dict[str, Any]:
    """一次完成：生成报告、打印到屏幕并保存到本地文本文件。"""
    report = make_report(title, sections, analysis, suggestions)
    print_report(report)
    path = save_report(report, output_dir)
    print(f"\n报告已保存：{path}")
    return report
