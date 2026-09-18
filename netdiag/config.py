# -*- coding: utf-8 -*-
"""集中存放检测参数，便于统一修改和扩展。"""

# 通用检测参数
PING_COUNT = 4                 # ping 次数
PING_TIMEOUT = 2.0             # 每次 ping 超时时间（秒）
SOCKET_TIMEOUT = 2.0           # TCP 连接、DNS 查询等超时时间（秒）

# 默认检测目标
DEFAULT_PUBLIC_IP = "8.8.8.8"  # 默认公网 IP（谷歌公共 DNS）
DEFAULT_DOMAIN = "www.baidu.com"  # 默认测试域名

# DNS 诊断相关
SYSTEM_DNS_TIMEOUT = 2.5       # 系统 DNS 解析的超时上限（秒）
PUBLIC_DNS_SERVERS = ("114.114.114.114", "8.8.8.8")  # 公共 DNS 对比服务器
DNS_RETRY_TIMES = 2            # 向指定 DNS 服务器发送查询时的重试次数

# 常用端口检测：服务名 -> (默认目标主机, 端口)
COMMON_PORTS = {
    "HTTP": ("www.baidu.com", 80),
    "HTTPS": ("www.baidu.com", 443),
    "DNS": ("114.114.114.114", 53),
}

# 路由追踪参数
TRACEROUTE_MAX_HOPS = 15       # 最多追踪多少跳
TRACEROUTE_TIMEOUT = 2.0       # 单跳超时时间（秒）
HIGH_LATENCY_THRESHOLD_MS = 200.0  # 平均延迟达到该值即标为“高延迟”
TRACEROUTE_LOSS_THRESHOLD = 0.5    # 丢包率超过该比例即标为异常

# 网速测试参数
DEFAULT_SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=1048576"
SPEED_TEST_TARGET_BYTES = 1_048_576  # 目标下载量：1 MiB
SLOW_SPEED_THRESHOLD_MBPS = 10.0     # 低于该速度给出“带宽或线路质量”提醒

