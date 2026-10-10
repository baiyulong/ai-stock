"""选股主逻辑：入池筛选 + 分层 + 排序"""
import uuid
import time
import pandas as pd
import numpy as np

from config import (
    POOL_AMPLITUDE_MIN,
    POOL_AVG_AMOUNT_MIN,
    POOL_LOOKBACK,
)
from db import load_day_klines, load_stock_info, save_screen_result
from indicators import add_rolling_indicators, get_latest_per_stock, calc_tier_indicators, get_second_low_dates


def run_screener() -> dict:
    """执行完整选股流程，返回结果摘要"""
    run_id = str(uuid.uuid4())[:8]
    run_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # 1. 加载数据
    df = load_day_klines(lookback=POOL_LOOKBACK)
    if df.empty:
        return {"run_id": run_id, "run_at": run_at, "count": 0, "results": [], "error": "无数据"}

    stock_info = load_stock_info()
    st_codes = set()
    name_map = {}
    if not stock_info.empty and "code" in stock_info.columns:
        if "is_st" in stock_info.columns:
            st_codes = set(stock_info[stock_info["is_st"]]["code"].tolist())
        if "name" in stock_info.columns:
            name_map = dict(zip(stock_info["code"], stock_info["name"]))

    # 2. 计算滚动窗口指标
    df = add_rolling_indicators(df)

    # 3. 取每只股票最新一天
    latest = get_latest_per_stock(df)

    # 4. 入池条件筛选（向量化）
    # 条件1: 结构双窗 - 近60日最低价 > 前40日最低价
    cond_structure = latest["low_60"] > latest["low_prev40"]

    # 条件2: 新高确认 - 近20日高点 >= 60日高点（即60日新高出现在最近20日）
    cond_new_high = latest["high_20"] >= latest["high_60"]

    # 条件3: 波幅证据 - (百日高点 - 百日低点) / 百日低点 >= 25%
    cond_amplitude = (latest["high_100"] - latest["low_100"]) / latest["low_100"] >= POOL_AMPLITUDE_MIN

    # 条件4: 流动性 - 百日日均成交额 > 2亿
    cond_liquidity = latest["avg_amount_100"] > POOL_AVG_AMOUNT_MIN

    # 条件5: 非ST
    cond_not_st = ~latest["code"].isin(st_codes)

    # 条件6: 数据完整（所有窗口指标都有值）
    cond_complete = latest[["low_60", "low_prev40", "high_20", "high_60", "high_100", "low_100", "avg_amount_100"]].notna().all(axis=1)

    pool = latest[
        cond_structure & cond_new_high & cond_amplitude & cond_liquidity & cond_not_st & cond_complete
    ].copy()

    # 5. 分层指标
    pool = calc_tier_indicators(pool)

    # 5.5 计算第二个低点（近60日最低）出现日期
    second_low_dates = get_second_low_dates(df, pool["code"].tolist())
    pool["low_60_date"] = pool["code"].map(second_low_dates)

    # 6. 添加名称和运行信息
    pool["name"] = pool["code"].map(name_map).fillna(pool["code"])
    pool["run_id"] = run_id
    pool["run_at"] = run_at
    pool["last_close"] = pool["close"]
    pool["invalidated"] = False

    # 7. 排序: complete 优先 → 低点抬升降序 → 距高点空间升序
    tier_order = {"complete": 0, "partial": 1, "pool_only": 2}
    pool["tier_order"] = pool["tier"].map(tier_order)
    pool = pool.sort_values(["tier_order", "low_raise_pct", "room_pct"], ascending=[True, False, True])
    pool = pool.drop(columns=["tier_order"])

    # 8. 保存结果
    result_cols = [
        "run_id", "run_at", "code", "name",
        "low_60", "low_prev40", "low_raise_pct", "low_60_date",
        "high_100", "low_100", "last_close",
        "rebound_pct", "room_pct",
        "avg_amount_10", "avg_amount_100",
        "tier", "invalidated",
    ]
    # 补充详情列（留空，后续单票分析时填充）
    for col in ["ma60_slope", "breakout_vol_ratio", "support_ok", "volume_breakout_ok", "ma_turn_ok"]:
        if col not in pool.columns:
            pool[col] = None

    save_cols = result_cols + ["ma60_slope", "breakout_vol_ratio", "support_ok", "volume_breakout_ok", "ma_turn_ok"]
    save_cols = [c for c in save_cols if c in pool.columns]
    save_screen_result(run_id, pool[save_cols])

    # 9. 统计
    tier_counts = pool["tier"].value_counts().to_dict()

    return {
        "run_id": run_id,
        "run_at": run_at,
        "total_scanned": int(len(latest)),
        "pool_count": int(len(pool)),
        "tier_counts": tier_counts,
        "results": format_results(pool),
    }


def format_results(df: pd.DataFrame) -> list:
    """格式化结果为 JSON 友好的列表"""
    cols = [
        "code", "name", "tier",
        "low_raise_pct", "rebound_pct", "room_pct",
        "last_close", "low_60", "low_prev40", "low_60_date",
        "high_100", "low_100",
        "avg_amount_10", "avg_amount_100",
    ]
    result = []
    for _, row in df.iterrows():
        item = {}
        for c in cols:
            v = row.get(c)
            if isinstance(v, (np.floating, np.integer)):
                v = float(v)
            elif pd.isna(v):
                v = None
            item[c] = v
        result.append(item)
    return result
