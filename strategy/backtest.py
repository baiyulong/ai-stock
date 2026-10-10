"""策略回测模块：用历史数据验证选股策略胜率"""
import pandas as pd
import numpy as np
from typing import Optional
from db import load_day_klines, load_stock_info
from indicators import add_rolling_indicators, get_latest_per_stock, calc_tier_indicators


def run_backtest(as_of_days_ago: int = 20, hold_days: int = 20) -> dict:
    """回测：以 as_of_days_ago 天前为选股日，持有 hold_days 天

    注意：选股日之前需要至少 100 个交易日数据才能计算百日窗口指标
    """
    # 加载全量数据
    df = load_day_klines(lookback=140)
    if df.empty:
        return {"error": "无数据"}

    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # 确定选股日期
    all_dates = sorted(df["date"].unique())
    total_days = len(all_dates)

    # 选股日索引：从末尾往前数 as_of_days_ago + hold_days
    as_of_idx = total_days - as_of_days_ago - hold_days
    if as_of_idx < 100:
        return {
            "error": f"数据不足：选股日前需要至少100个交易日，当前只有 {as_of_idx} 天",
            "suggestion": f"请减小 as_of_days_ago（建议 <= {total_days - 120}）或 hold_days",
        }

    as_of_date = all_dates[as_of_idx]
    # 持有期结束日
    end_idx = min(as_of_idx + hold_days, total_days - 1)
    end_date = all_dates[end_idx]

    # 截取选股日及之前的数据用于选股
    df_hist = df[df["date"] <= as_of_date].copy()

    # 计算指标
    df_hist = add_rolling_indicators(df_hist)
    latest = get_latest_per_stock(df_hist)

    # 入池条件
    stock_info = load_stock_info()
    st_codes = set()
    if not stock_info.empty and "code" in stock_info.columns:
        if "is_st" in stock_info.columns:
            st_codes = set(stock_info[stock_info["is_st"]]["code"].tolist())

    cond_structure = latest["low_60"] > latest["low_prev40"]
    cond_new_high = latest["high_20"] >= latest["high_60"]
    cond_amplitude = (latest["high_100"] - latest["low_100"]) / latest["low_100"] >= 0.25
    cond_liquidity = latest["avg_amount_100"] > 2e8
    cond_not_st = ~latest["code"].isin(st_codes)
    cond_complete = latest[["low_60", "low_prev40", "high_20", "high_60", "high_100", "low_100", "avg_amount_100"]].notna().all(axis=1)

    pool = latest[
        cond_structure & cond_new_high & cond_amplitude & cond_liquidity & cond_not_st & cond_complete
    ].copy()

    if pool.empty:
        return {"as_of_date": str(as_of_date)[:10], "pool_count": 0, "message": "选股日无入池股票"}

    # 分层
    pool = calc_tier_indicators(pool)

    # 计算持有期收益
    results = []
    for _, row in pool.iterrows():
        code = row["code"]
        entry_price = row["close"]

        # 持有期结束时的价格
        stock_future = df[(df["code"] == code) & (df["date"] > as_of_date)].head(hold_days)
        if stock_future.empty:
            continue

        exit_price = stock_future["close"].iloc[-1]
        max_price = stock_future["high"].max()
        min_price = stock_future["low"].min()

        return_pct = (exit_price - entry_price) / entry_price * 100
        max_return = (max_price - entry_price) / entry_price * 100
        max_drawdown = (min_price - entry_price) / entry_price * 100

        results.append({
            "code": code,
            "name": row.get("name", code),
            "tier": row["tier"],
            "entry_price": round(float(entry_price), 2),
            "exit_price": round(float(exit_price), 2),
            "return_pct": round(float(return_pct), 2),
            "max_return_pct": round(float(max_return), 2),
            "max_drawdown_pct": round(float(max_drawdown), 2),
            "low_raise_pct": round(float(row.get("low_raise_pct", 0)), 2),
        })

    if not results:
        return {"as_of_date": str(as_of_date)[:10], "pool_count": len(pool), "message": "无持有期数据"}

    result_df = pd.DataFrame(results)
    returns = result_df["return_pct"]

    complete_returns = result_df[result_df["tier"] == "complete"]["return_pct"]

    return {
        "as_of_date": str(as_of_date)[:10],
        "hold_days": hold_days,
        "pool_count": len(results),
        "complete_count": int((result_df["tier"] == "complete").sum()),
        "win_rate": round(float((returns > 0).mean() * 100), 2),
        "avg_return": round(float(returns.mean()), 2),
        "median_return": round(float(returns.median()), 2),
        "max_return": round(float(returns.max()), 2),
        "min_return": round(float(returns.min()), 2),
        "avg_complete_return": round(float(complete_returns.mean()), 2) if len(complete_returns) > 0 else None,
        "complete_win_rate": round(float((complete_returns > 0).mean() * 100), 2) if len(complete_returns) > 0 else None,
        "results": sorted(results, key=lambda x: x["return_pct"], reverse=True),
    }
