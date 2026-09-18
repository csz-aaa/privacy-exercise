# -*- coding: utf-8 -*-
"""电脑网络问题自动检测与诊断工具 - 命令行入口。

运行方式：
    python main.py

本项目只需要 Python 3.10+ 标准库，不依赖任何第三方包。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from netdiag import diagnosis, report
from netdiag.config import DEFAULT_DOMAIN, DEFAULT_PUBLIC_IP


def _prepare_console() -> None:
    """尽量让控制台以 UTF-8 输出，避免中文报告乱码。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _show_and_save(
    title: str,
    sections: List[Dict[str, Any]],
    analysis: str = "",
    suggestions: List[str] | None = None,
) -> None:
    """把结果打印到屏幕并保存到 reports 文件夹。"""
    report.output_result(title, sections, analysis=analysis, suggestions=suggestions)


def _show_menu() -> None:
    """显示交互式主菜单。"""
    print("\n==============================================")
    print("电脑网络问题自动检测与诊断工具")
    print("==============================================")
    print(" 1. 采集基础网络信息")
    print(" 2. 连通性检测（网关 / 公网 IP / 域名）")
    print(" 3. DNS 解析诊断")
    print(" 4. 常用端口检测（80 / 443 / 53）")
    print(" 5. 自定义 IP 和端口检测")
    print(" 6. 路由追踪（最多 15 跳）")
    print(" 7. 下载测速（可选，约 1MB）")
    print(" 8. 一键综合诊断（不含测速）")
    print(" 9. 完整诊断（含测速）")
    print(" 0. 退出")
    print("----------------------------------------------")


def _ask_custom_port() -> None:
    """交互式输入主机与端口，执行自定义端口检测。"""
    host = input("请输入目标 IP 或域名（直接回车使用 8.8.8.8）：").strip()
    if not host:
        host = "8.8.8.8"
    port_text = input("请输入端口号（1-65535）：").strip()
    try:
        port = int(port_text)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        print("端口号格式不正确，已取消本次检测。")
        return
    section = diagnosis.custom_port_section(host, port)
    _show_and_save(f"自定义端口检测 {host}:{port}", [section])


def main() -> None:
    """程序主入口：显示菜单并循环处理用户选择。"""
    _prepare_console()
    print("提示：每次检测都会自动保存一份 network_report_时间戳.txt 到 reports 文件夹。")

    while True:
        _show_menu()
        choice = input("请输入数字选择功能：").strip()

        try:
            if choice == "1":
                _show_and_save("基础网络信息采集", [diagnosis.network_info_section()])
            elif choice == "2":
                _show_and_save("网络连通性检测", diagnosis.connectivity_sections())
            elif choice == "3":
                _show_and_save(
                    f"DNS 诊断（{DEFAULT_DOMAIN}）",
                    [diagnosis.dns_section(DEFAULT_DOMAIN)],
                )
            elif choice == "4":
                _show_and_save("常用端口检测", [diagnosis.port_section()])
            elif choice == "5":
                _ask_custom_port()
            elif choice == "6":
                _show_and_save(
                    f"路由追踪（{DEFAULT_DOMAIN}）",
                    [diagnosis.traceroute_section(DEFAULT_DOMAIN)],
                )
            elif choice == "7":
                _show_and_save("下载测速", [diagnosis.speed_section()])
            elif choice == "8":
                result = diagnosis.full_diagnose(
                    include_speed_test=False, include_traceroute=True
                )
                _show_and_save(
                    "一键综合诊断",
                    result["sections"],
                    analysis=result["analysis"],
                    suggestions=result["suggestions"],
                )
            elif choice == "9":
                result = diagnosis.full_diagnose(
                    include_speed_test=True, include_traceroute=True
                )
                _show_and_save(
                    "完整诊断（含测速）",
                    result["sections"],
                    analysis=result["analysis"],
                    suggestions=result["suggestions"],
                )
            elif choice == "0":
                print("已退出，欢迎再次使用。")
                break
            else:
                print("无效选择，请输入 0-9。")
        except KeyboardInterrupt:
            print("\n当前操作已取消。")
        except Exception as exc:  # 顶层兜底，避免普通用户看到难懂的回溯
            print(f"操作过程中出现错误：{exc}")
            print("请确认网络命令可用后重试；也可查看 reports 中的最近一次报告。")

        if choice != "0":
            input("\n按回车键返回主菜单...")


if __name__ == "__main__":
    main()

