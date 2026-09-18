# 电脑网络问题自动检测与诊断工具

一个在 Windows 上优先使用的 Python 网络故障排查工具，也能在 Linux/macOS 上运行。工具会把每一项检测结果按“正常 / 警告 / 异常”标注，并把能直接照做的修复步骤写进报告。

## 推荐实现方案

本项目采用最简单的“CLI 交互菜单 + 功能分包”方案：

- 界面先用命令行菜单，不做 GUI，避免引入第三方界面库。
- 每个核心功能拆成独立模块、独立函数，之后做 GUI 时直接复用这些函数即可。
- 外部命令只通过 `subprocess` 调用，不允许 `os.system`。
- 第三方依赖为零，全部使用 Python 标准库。

如果你想做 GUI，推荐保留本项目的 `netdiag` 包，只替换或增加一个前端层（例如 `tkinter` 或 `PySide6`），不要重写检测逻辑。

## 项目文件结构

```text
network_detection/
├─ main.py                          # CLI 入口：菜单选择、调用各模块
├─ network_detection_gui.py         # 图形界面入口：适合普通用户
├─ start_gui.bat                    # Windows 双击启动图形界面
├─ start_network_detection.bat      # Windows 双击启动脚本
├─ requirements.txt                 # 依赖说明（无第三方依赖）
├─ README.md                        # 使用说明
├─ reports/                         # 运行时自动生成，保存网络报告
└─ netdiag/                         # 可复用核心功能包
   ├─ __init__.py
   ├─ config.py                     # 检测参数集中配置
   ├─ common.py                     # subprocess、状态、通用工具
   ├─ environment.py                # 无线/热点与 VPN/代理环境检测
   ├─ network_info.py               # 功能1：基础网络信息采集
   ├─ connectivity.py               # 功能2：ping 连通性检测
   ├─ dns_diagnosis.py              # 功能3：DNS 诊断与污染对比
   ├─ port_check.py                 # 功能4：端口与服务检测
   ├─ traceroute.py                 # 功能5：简化版路由追踪
   ├─ speed_test.py                 # 功能6：下载测速
   ├─ diagnosis.py                  # 功能7：综合诊断与自动分析
   └─ report.py                     # 屏幕输出与文本报告保存
```

## 安装与运行

### 1. 安装 Python

需要 Python 3.10 或更高版本。

安装时务必勾选 “Add Python to PATH”，否则 Windows 命令行无法直接找到 `python`。

### 2. 进入项目目录

在命令行中执行：

```bat
cd /d E:\network detection
```

### 3. 启动程序

推荐方式一，双击 `start_gui.bat`，使用图形界面。

图形界面支持选择“手机热点很差/无网络”“学校 WiFi 很差”“使用 VPN 后异常”等场景，只执行检测并给出建议，不会修改系统设置；报告仍会自动保存到 `reports` 文件夹。

推荐方式二，双击 `start_network_detection.bat`，使用命令行菜单。

也可以在命令行执行：

```bat
python main.py
```

如果电脑同时装有多个 Python 版本，也可以执行：

```bat
py -3 main.py
```

不需要安装任何第三方包，`requirements.txt` 只是依赖说明文件。

### 4. 查看报告

每次运行检测项后，程序会：

1. 在屏幕打印可读结果；
2. 自动把完整结果保存到 `reports\network_report_时间戳.txt`。

## 各检测项含义

| 菜单项 | 作用 | 常见结论 |
| --- | --- | --- |
| 基础网络信息 | 显示网卡、IP、掩码、网关、DNS、MAC | 判断本机是否拿到内网 IP |
| 连通性检测 | ping 网关、8.8.8.8、域名 | 区分内网、外网、DNS 故障 |
| DNS 诊断 | 对比系统 DNS 与公共 DNS | 判断是否 DNS 污染/解析失败 |
| 端口检测 | 检测 80/443/53 | 判断防火墙、代理或运营商限制 |
| 自定义端口 | 输入任意 IP 和端口 | 排查特定服务是否可达 |
| 路由追踪 | 最多 15 跳 | 找出高延迟/丢包发生在哪一段 |
| 下载测速 | 下载约 1MB | 判断带宽与线路质量 |
| 综合诊断 | 自动串联并分析 | 给出可操作的修复建议 |

## 对程序设计初学者的关键代码说明

### 1. 为什么用 subprocess 而不是 os.system

`os.system("ping ...")` 会把字符串直接交给系统命令解释器执行，如果拼接用户输入，存在命令注入风险，而且不方便读取输出。工具统一封装在 [common.py](netdiag/common.py) 的 `run_command()` 中：

```python
subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               text=True, shell=False)
```

这样能安全拿到命令的返回码、标准输出和错误信息，Windows 下也不会弹出黑色命令窗口。

### 2. 为什么检测逻辑要拆模块

网络问题可以分成“本机没网卡”“网关不通”“外网不通”“DNS 不通”等多种情况。每个模块只负责一种判断，例如 [network_info.py](netdiag/network_info.py) 只负责采集信息，[connectivity.py](netdiag/connectivity.py) 只负责 ping。综合诊断模块 [diagnosis.py](netdiag/diagnosis.py) 再按顺序组合它们并推断根因。以后写 GUI 时只需调用这些函数，不需要改动内部实现。

### 3. 系统 DNS 和指定 DNS 有什么区别

[dns_diagnosis.py](netdiag/dns_diagnosis.py) 用 `socket.gethostbyname_ex()` 问系统当前使用的 DNS，同时自带一个轻量 DNS 报文解析函数，直接向 `114.114.114.114` 和 `8.8.8.8` 查询同一个域名。两边结果不一致，就提示可能被污染或本地缓存错误。

### 4. 状态为什么用“正常/警告/异常”

普通用户不需要看原始 TTL 或丢包数，只需要知道“现在要不要处理、从哪里处理”。工具内部统一使用三级状态，然后由报告模块把它们转换成中文建议。

## Linux/macOS 注意事项

- Linux 需要系统安装 `ip` 命令（通常自带）；路由追踪需要 `traceroute`，可执行 `sudo apt install traceroute` 等安装。
- macOS 自带 `ping`、`ifconfig`、`traceroute`，无需额外安装。
- 自动保存的报告位置在项目目录下的 `reports/`。

## 后续扩展建议

1. 增加 HTTP 状态码检测（请求某个网站，观察返回码）。
2. 增加 WiFi 信号强度检测。
3. 增加历史报告对比，判断网络质量是否持续恶化。
4. 用 `tkinter`/`PySide6` 做 GUI，只替换主菜单，复用 `netdiag` 包。
