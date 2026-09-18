# -*- coding: utf-8 -*-
"""网络问题检测助手：面向普通用户的图形界面前端。

只使用 Python 自带标准库（tkinter + netdiag），功能仅限检测与建议。
"""

from __future__ import annotations

import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

from netdiag import diagnosis, environment, report


class _NullWriter(io.TextIOBase):
    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


class NetworkDetectorApp(tk.Tk):
    """图形界面主窗口。"""

    BG = "#f4f6fb"
    PANEL_BG = "#ffffff"
    HEADER_BG = "#eef2fa"
    ACCENT = "#2456a6"
    TEXT = "#1f2933"
    MUTED = "#5b6472"

    def __init__(self) -> None:
        super().__init__()
        self.title("网络问题检测助手")
        self.geometry("1020x700")
        self.minsize(880, 620)
        self.configure(bg=self.BG)

        self.task_queue: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False
        self.scenario_var = tk.StringVar(value="current")
        self.vpn_manual_var = tk.BooleanVar(value=False)
        self.action_buttons: list[tk.Button] = []

        self._configure_fonts()
        self._build_layout()
        self.after(100, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_fonts(self) -> None:
        try:
            self.title_font = ("Microsoft YaHei UI", 17, "bold")
            self.sub_font = ("Microsoft YaHei UI", 9)
            self.button_font = ("Microsoft YaHei UI", 10)
            self.text_font = ("Microsoft YaHei UI", 10)
        except tk.TclError:
            self.title_font = ("Segoe UI", 16, "bold")
            self.sub_font = ("Segoe UI", 9)
            self.button_font = ("Segoe UI", 10)
            self.text_font = ("Consolas", 10)

    def _build_layout(self) -> None:
        self._build_header()
        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self._build_result_area(body)
        self._build_statusbar()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=self.HEADER_BG, height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = tk.Label(
            header,
            text="网络问题检测助手",
            bg=self.HEADER_BG,
            fg=self.ACCENT,
            font=self.title_font,
        )
        title.pack(anchor="w", padx=22, pady=(10, 0))
        subtitle = tk.Label(
            header,
            text="适合排查手机热点、学校 WiFi、VPN 等场景下的网络问题",
            bg=self.HEADER_BG,
            fg=self.MUTED,
            font=self.sub_font,
        )
        subtitle.pack(anchor="w", padx=24)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        panel = tk.Frame(
            parent,
            bg=self.PANEL_BG,
            width=230,
            highlightbackground="#d9deea",
            highlightthickness=1,
        )
        panel.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)

        self._panel_label(panel, "使用场景").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6)
        )

        scenarios = [
            ("current", "当前网络不稳定"),
            ("hotspot", "手机热点很差/无网络"),
            ("school", "学校 WiFi 很差"),
            ("vpn", "使用 VPN 后异常"),
        ]
        for index, (value, text) in enumerate(scenarios, start=1):
            rb = tk.Radiobutton(
                panel,
                text=text,
                value=value,
                variable=self.scenario_var,
                anchor="w",
                bg=self.PANEL_BG,
                fg=self.TEXT,
                font=self.button_font,
                selectcolor=self.PANEL_BG,
                activebackground=self.PANEL_BG,
                highlightthickness=0,
                bd=0,
            )
            rb.grid(row=index, column=0, sticky="ew", padx=12, pady=2)

        vpn_check = tk.Checkbutton(
            panel,
            text="我正在使用 VPN/代理",
            variable=self.vpn_manual_var,
            bg=self.PANEL_BG,
            fg=self.TEXT,
            font=self.button_font,
            activebackground=self.PANEL_BG,
            selectcolor=self.PANEL_BG,
            highlightthickness=0,
            bd=0,
        )
        vpn_check.grid(row=5, column=0, sticky="w", padx=16, pady=(8, 2))

        tk.Frame(panel, bg="#d9deea", height=1).grid(
            row=6, column=0, sticky="ew", padx=12, pady=12
        )

        actions = [
            ("无线 / VPN 环境", self._run_environment, "①"),
            ("连通性检查", self._run_connectivity, "②"),
            ("DNS / 端口", self._run_dns_ports, "③"),
            ("路由 / 测速", self._run_route_speed, "④"),
            ("完整诊断", self._run_full_diagnosis, "★"),
        ]
        row = 7
        for text, command, marker in actions:
            btn = tk.Button(
                panel,
                text=f"{marker} {text}",
                command=command,
                bg=self.ACCENT,
                fg="#ffffff",
                activebackground="#1d488f",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=10,
                pady=8,
                font=self.button_font,
                cursor="hand2",
            )
            btn.grid(row=row, column=0, sticky="ew", padx=14, pady=4)
            self.action_buttons.append(btn)
            row += 1

        open_btn = tk.Button(
            panel,
            text="打开报告文件夹",
            command=self._open_reports,
            bg="#e8edf7",
            fg=self.ACCENT,
            activebackground="#dce5f3",
            activeforeground=self.ACCENT,
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            font=self.button_font,
            cursor="hand2",
        )
        open_btn.grid(row=row + 1, column=0, sticky="ew", padx=14, pady=(14, 10))

        note = tk.Label(
            panel,
            text="本工具只检测和给建议，不会修改系统设置。",
            bg=self.PANEL_BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 8),
            justify="left",
            wraplength=190,
        )
        note.grid(row=row + 2, column=0, sticky="ew", padx=14, pady=(0, 10))

    def _panel_label(self, parent: tk.Frame, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=self.PANEL_BG,
            fg=self.ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
        )

    def _build_result_area(self, parent: tk.Frame) -> None:
        wrapper = tk.Frame(parent, bg=self.BG)
        wrapper.grid(row=0, column=1, sticky="nsew")
        wrapper.grid_rowconfigure(1, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        toolbar = tk.Frame(wrapper, bg=self.BG)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.result_title = tk.Label(
            toolbar,
            text="检测结果",
            bg=self.BG,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.result_title.pack(side="left")
        copy_btn = tk.Button(
            toolbar,
            text="复制结果",
            command=self._copy_result,
            bg=self.PANEL_BG,
            fg=self.ACCENT,
            relief="flat",
            bd=0,
            font=self.button_font,
            cursor="hand2",
        )
        copy_btn.pack(side="right")

        self.text = scrolledtext.ScrolledText(
            wrapper,
            wrap="word",
            font=self.text_font,
            bg="#ffffff",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            padx=14,
            pady=12,
            height=20,
        )
        self.text.grid(row=1, column=0, sticky="nsew")
        self._configure_tags()

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg="#e6eaf2", height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_label = tk.Label(
            bar,
            text="就绪",
            bg="#e6eaf2",
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=14)

    def _configure_tags(self) -> None:
        self.text.tag_configure("heading", font=("Microsoft YaHei UI", 11, "bold"), foreground=self.ACCENT)
        self.text.tag_configure("section", font=("Microsoft YaHei UI", 10, "bold"), foreground=self.TEXT)
        self.text.tag_configure("ok", foreground="#147d4f")
        self.text.tag_configure("warn", foreground="#a05a00")
        self.text.tag_configure("fail", foreground="#b42318")
        self.text.tag_configure("info", foreground=self.MUTED)
        self.text.tag_configure("suggestion", foreground="#3a4a63")
        self.text.tag_configure("path", foreground="#2456a6")

    # ------- 用户操作 -------

    def _run_environment(self) -> None:
        self._start_job(
            "无线 / 热点与 VPN 环境",
            lambda: ([environment.environment_section()], "", []),
        )

    def _run_connectivity(self) -> None:
        def build():
            env = environment.environment_section()
            sections = [env, diagnosis.network_info_section()]
            sections.extend(diagnosis.connectivity_sections())
            extra = self._scenario_suggestions(env)
            return sections, "", extra

        self._start_job("连通性检查", build)

    def _run_dns_ports(self) -> None:
        def build():
            env = environment.environment_section()
            sections = [env, diagnosis.dns_section(), diagnosis.port_section()]
            return sections, "", self._scenario_suggestions(env)

        self._start_job("DNS 与端口检查", build)

    def _run_route_speed(self) -> None:
        def build():
            env = environment.environment_section()
            sections = [env, diagnosis.traceroute_section()]
            try:
                sections.append(diagnosis.speed_section())
            except Exception as exc:
                sections.append(
                    {
                        "key": "speed",
                        "title": "下载测速",
                        "status": "异常",
                        "summary": f"测速失败：{exc}",
                        "data": {},
                        "suggestions": ["测速失败不一定代表断网，可稍后重试或换网络再测。"],
                    }
                )
            return sections, "", self._scenario_suggestions(env)

        self._start_job("路由与测速", build)

    def _run_full_diagnosis(self) -> None:
        def build():
            env = environment.environment_section()
            result = diagnosis.full_diagnose(include_speed_test=False)
            sections = [env] + result["sections"]
            suggestions = result["suggestions"]
            suggestions.extend(self._scenario_suggestions(env))
            return sections, result["analysis"], suggestions

        self._start_job("完整诊断", build)

    def _scenario_suggestions(self, env: dict) -> list[str]:
        """按用户选择的场景补充不会执行任何修改的建议。"""
        scenario = getattr(self, "_run_scenario", "current")
        suggestions: list[str] = []
        vpn_used = bool(getattr(self, "_run_vpn", False)) or bool(
            env.get("data", {}).get("vpn_proxy", {}).get("detected")
        )

        if scenario == "hotspot":
            wifi = env.get("data", {}).get("wireless", {})
            if wifi.get("connected"):
                suggestions.append("确认手机处于信号较好的位置，避免把手机放在电脑旁或金属遮挡处。")
                suggestions.append("检查手机热点设置：是否限制连接设备、是否开启了省电或自动断开。")
                suggestions.append("确认手机流量还有剩余且未被运营商限速，必要时用另一台手机交叉测试。")
            else:
                suggestions.append("电脑还没有连上热点，请先在手机端开启个人热点，再在电脑 WiFi 列表中选择连接。")
        elif scenario == "school":
            suggestions.append("学校 WiFi 通常需要网页认证：连接后先打开任意网页完成登录，再回来重新检测。")
            suggestions.append("晚间或上课高峰期学校网络可能拥塞，可稍后再测或换一个无线接入点。")
            suggestions.append("如果信号弱，尽量靠近教室或走廊里的无线接入点，避免隔墙使用。")
        elif scenario == "vpn":
            suggestions.append("建议分别测一次“关闭 VPN”和“开启 VPN”，两次结果一对比就能判断是 VPN 还是本地网络问题。")
            suggestions.append("VPN 节点拥挤时网络会明显变慢，可以切换到其他地区或协议的节点重试。")
            suggestions.append("部分学校或运营商网络会限制 VPN，请确认使用的是允许的协议和端口。")

        if vpn_used and scenario != "vpn":
            suggestions.append("你正在使用 VPN/代理，检测结果可能经过代理服务器；建议关闭 VPN 后再测一次。")
        if not suggestions:
            suggestions.append("如果检测结果仍不理想，可运行“完整诊断”查看更多网络细节。")
        return suggestions

    # ------- 后台任务与界面刷新 -------

    def _start_job(self, title: str, builder) -> None:
        if self.busy:
            return
        self._run_scenario = self.scenario_var.get()
        self._run_vpn = self.vpn_manual_var.get()
        self.busy = True
        for button in self.action_buttons:
            button.configure(state="disabled")
        self.result_title.configure(text=title)
        self._append_line(f"\n正在检测：{title}\n", "info")
        self._set_status("检测中，请稍候...")
        worker = threading.Thread(
            target=self._worker,
            args=(title, builder),
            daemon=True,
        )
        worker.start()

    def _worker(self, title: str, builder) -> None:
        try:
            sections, analysis, suggestions = builder()
            saved = report.save_report(
                report.make_report(title, sections, analysis=analysis, suggestions=suggestions)
            )
            self.task_queue.put(
                ("done", title, sections, analysis, suggestions, str(saved))
            )
        except Exception as exc:
            import traceback

            self.task_queue.put(
                ("error", title, f"{exc}\n{traceback.format_exc()}")
            )

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.task_queue.get_nowait()
                if message[0] == "done":
                    self._show_result(*message[1:])
                elif message[0] == "error":
                    self._show_error(message[1], message[2])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _show_result(self, title, sections, analysis, suggestions, path) -> None:
        self.result_title.configure(text=title)
        self._append_line("\n" + "=" * 58 + "\n", "info")
        self._append_line(f"  {title}\n", "heading")
        self._append_line("=" * 58 + "\n\n", "info")
        for section in sections:
            self._render_section(section)
        if analysis:
            self._append_line("\n综合判断\n", "section")
            self._append_line(analysis + "\n", "info")
        if suggestions:
            self._append_line("\n给你的建议\n", "section")
            for index, item in enumerate(dict.fromkeys(suggestions), start=1):
                self._append_line(f"{index}. {item}\n", "suggestion")
        self._append_line(f"\n报告已保存：{path}\n", "path")
        self._append_line("-" * 58 + "\n", "info")
        self._set_status("检测完成")
        self._finish_task()

    def _show_error(self, title, detail) -> None:
        self._append_line(f"\n{title} 执行失败\n", "fail")
        self._append_line(detail + "\n", "fail")
        self._set_status("检测失败")
        self._finish_task()

    def _render_section(self, section) -> None:
        status = section.get("status", "未知")
        if status == "正常":
            tag = "ok"
        elif status == "警告":
            tag = "warn"
        else:
            tag = "fail"
        title = section.get("title", "检测项")
        summary = section.get("summary", "")
        self._append_line(f"[{title}]  状态：", "section")
        self._append_line(status + "\n", tag)
        self._append_line(summary + "\n", "info")
        for index, item in enumerate(section.get("suggestions", []), start=1):
            self._append_line(f"  建议 {index}：{item}\n", "suggestion")
        self._append_line("\n", "info")

    def _append_line(self, text: str, tag: str = "info") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", text, tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def _finish_task(self) -> None:
        self.busy = False
        for button in self.action_buttons:
            button.configure(state="normal")

    def _copy_result(self) -> None:
        content = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self._set_status("结果已复制")

    def _open_reports(self) -> None:
        target = str(Path(__file__).resolve().parent / "reports")
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            self._set_status(f"无法打开报告文件夹：{exc}")

    def _on_close(self) -> None:
        self.destroy()


def main() -> None:
    try:
        if sys.stdout is None:
            sys.stdout = _NullWriter()
        if sys.stderr is None:
            sys.stderr = _NullWriter()
        app = NetworkDetectorApp()
        app.mainloop()
    except Exception as exc:
        import datetime
        import traceback

        log_path = Path(__file__).resolve().with_name("gui_error.log")
        try:
            log_path.write_text(
                f"启动失败时间：{datetime.datetime.now()}\n"
                f"错误：{exc}\n\n{traceback.format_exc()}",
                encoding="utf-8",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
