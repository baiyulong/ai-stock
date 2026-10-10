"""策略配置"""
import os

# DuckDB 路径（相对于 web/ 目录的数据文件）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUCKDB_PATH = os.path.join(BASE_DIR, "web", "data", "duckdb", "market.duckdb")

# 服务端口
SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 18081

# ===== 策略阈值 =====

# 入池条件
POOL_WINDOW_RECENT = 60      # 近 N 日（结构双窗前窗）
POOL_WINDOW_PREV = 40        # 前 N 日（结构双窗前窗之前的窗口）
POOL_WINDOW_100 = 100        # 百日观察窗
POOL_NEW_HIGH_WINDOW = 20    # 新高确认窗口（最近 N 日内创 60 日新高）
POOL_AMPLITUDE_MIN = 0.25    # 波幅下限（25%）
POOL_AVG_AMOUNT_MIN = 2e8    # 百日日均成交额下限（2亿元）
POOL_LOOKBACK = 140          # 数据回溯天数（100+40）

# 分层条件
TIER_REBOUND_MIN = 15.0      # 距低点回升下限（%）
TIER_ROOM_MAX = 15.0         # 距高点空间上限（%）
TIER_AMOUNT_MIN = 2e8        # 近10日日均成交额下限（元）

# 逐票验证
DETAIL_SUPPORT_WINDOW = 20   # 支撑验证窗口（最近 N 日收盘不破前40日低点）
DETAIL_VOLUME_RATIO = 1.5    # 突破日量比下限
DETAIL_MA_WINDOW = 60        # 均线周期
DETAIL_MA_SLOPE_DAYS = 5     # 均线斜率观察天数
DETAIL_INVALIDATE_TOL = 0.01 # 证伪容差（1%）
