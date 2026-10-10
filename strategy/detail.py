"""单票详细分析：三点验证 + 证伪信号"""
import io
import requests
import pandas as pd
import numpy as np

from config import (
    DETAIL_SUPPORT_WINDOW,
    DETAIL_VOLUME_RATIO,
    DETAIL_MA_WINDOW,
    DETAIL_MA_SLOPE_DAYS,
    DETAIL_INVALIDATE_TOL,
)
from indicators import find_breakout_day
from trading import calc_full_trading_analysis

GO_SERVICE_URL = "http://127.0.0.1:18080"


def _load_stock_klines(code: str) -> pd.DataFrame:
    """从 Go 服务加载单只股票 K 线数据"""
    url = f"{GO_SERVICE_URL}/api/screener/export-kline?code={code}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), dtype={"code": str, "exchange": str})
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = df["code"].str.zfill(6)
    return df


def analyze_stock(code: str) -> dict:
    """单只股票的详细诊断

    返回:
        - basic: 基本信息（最新价、百日高低点等）
        - pool_checks: 入池条件逐条验证
        - tier_indicators: 分层指标
        - confirmations: 三点验证结果
        - invalidation: 证伪信号
        - klines: 近120日K线数据（供前端画图）
    """
    df = _load_stock_klines(code)

    if df.empty:
        return {"error": f"未找到 {code} 的K线数据"}

    df["date"] = pd.to_datetime(df["date"])

    # 计算指标
    from indicators import add_rolling_indicators
    df = add_rolling_indicators(df)
    latest = df.iloc[-1]

    # ===== 入池条件逐条验证 =====
    pool_checks = {
        "structure_double_window": bool(latest["low_60"] > latest["low_prev40"]) if pd.notna(latest["low_60"]) and pd.notna(latest["low_prev40"]) else False,
        "new_high_confirm": bool(latest["high_20"] >= latest["high_60"]) if pd.notna(latest["high_20"]) and pd.notna(latest["high_60"]) else False,
        "amplitude": bool((latest["high_100"] - latest["low_100"]) / latest["low_100"] >= 0.25) if pd.notna(latest["high_100"]) and pd.notna(latest["low_100"]) else False,
        "liquidity": bool(latest["avg_amount_100"] > 2e8) if pd.notna(latest["avg_amount_100"]) else False,
    }
    pool_checks["all_pass"] = all(pool_checks.values())

    # ===== 分层指标 =====
    low_raise_pct = float((latest["low_60"] - latest["low_prev40"]) / latest["low_prev40"] * 100) if pd.notna(latest["low_60"]) and pd.notna(latest["low_prev40"]) and latest["low_prev40"] > 0 else 0
    rebound_pct = float((latest["close"] - latest["low_100"]) / latest["low_100"] * 100) if pd.notna(latest["low_100"]) and latest["low_100"] > 0 else 0
    room_pct = float((latest["high_100"] - latest["close"]) / latest["high_100"] * 100) if pd.notna(latest["high_100"]) and latest["high_100"] > 0 else 0

    tier_indicators = {
        "low_raise_pct": round(low_raise_pct, 2),
        "rebound_pct": round(rebound_pct, 2),
        "room_pct": round(room_pct, 2),
        "avg_amount_10": float(latest["avg_amount_10"]) if pd.notna(latest["avg_amount_10"]) else 0,
        "rebound_pass": rebound_pct >= 15.0,
        "room_pass": room_pct <= 15.0,
        "volume_pass": bool(latest["avg_amount_10"] > 2e8) if pd.notna(latest["avg_amount_10"]) else False,
    }

    # ===== 三点验证 =====
    # ① 支撑验证：最近 N 日收盘价是否全部 > 前40日最低价（低点抬升线）
    recent = df.tail(DETAIL_SUPPORT_WINDOW)
    support_line = latest["low_prev40"]
    support_ok = bool((recent["close"] > support_line).all()) if pd.notna(support_line) else False

    # ② 放量突破：百日高点突破日量比 >= 1.5
    breakout = find_breakout_day(df)
    volume_breakout_ok = breakout.get("volume_ratio", 0) >= DETAIL_VOLUME_RATIO

    # ③ 均线拐头：MA60 最近 N 日斜率 > 0（由下行转上行或走平）
    ma_series = df["ma60"].dropna()
    if len(ma_series) >= DETAIL_MA_SLOPE_DAYS + 1:
        ma_slope = float(ma_series.iloc[-1] - ma_series.iloc[-(DETAIL_MA_SLOPE_DAYS + 1)])
        ma_turn_ok = ma_slope >= 0
    else:
        ma_slope = 0
        ma_turn_ok = False

    confirmations = {
        "support": {
            "pass": support_ok,
            "support_line": float(support_line) if pd.notna(support_line) else 0,
            "window": DETAIL_SUPPORT_WINDOW,
            "description": f"最近{DETAIL_SUPPORT_WINDOW}日收盘价全部高于前40日最低价 {support_line:.2f} 元" if support_ok else "存在收盘价跌破低点抬升线",
        },
        "volume_breakout": {
            "pass": volume_breakout_ok,
            "breakout_date": str(breakout.get("date", ""))[:10] if breakout.get("date") else "",
            "volume_ratio": round(breakout.get("volume_ratio", 0), 2),
            "threshold": DETAIL_VOLUME_RATIO,
            "description": f"突破日量比 {breakout.get('volume_ratio', 0):.2f}（阈值 {DETAIL_VOLUME_RATIO}）",
        },
        "ma_turn": {
            "pass": ma_turn_ok,
            "ma60_slope": round(ma_slope, 4),
            "window": DETAIL_MA_SLOPE_DAYS,
            "description": f"MA60 近{DETAIL_MA_SLOPE_DAYS}日斜率 {ma_slope:.4f}（>=0 为拐头向上）",
        },
        "all_pass": support_ok and volume_breakout_ok and ma_turn_ok,
    }

    # ===== 证伪信号 =====
    invalidate_price = support_line * (1 - DETAIL_INVALIDATE_TOL) if pd.notna(support_line) else 0
    invalidated = bool(latest["close"] < invalidate_price) if pd.notna(support_line) else False

    invalidation = {
        "invalidated": invalidated,
        "critical_line": float(support_line) if pd.notna(support_line) else 0,
        "invalidate_price": round(float(invalidate_price), 2),
        "current_close": float(latest["close"]),
        "tolerance": f"{DETAIL_INVALIDATE_TOL * 100:.0f}%",
        "description": f"收盘价 {latest['close']:.2f} {'已跌破' if invalidated else '未跌破'} 生死线 {invalidate_price:.2f}（前40日低点 {support_line:.2f} 的 {1 - DETAIL_INVALIDATE_TOL:.0%}）",
    }

    # ===== 基本信息 =====
    basic = {
        "code": code,
        "last_close": float(latest["close"]),
        "last_date": str(latest["date"])[:10],
        "high_100": float(latest["high_100"]) if pd.notna(latest["high_100"]) else 0,
        "low_100": float(latest["low_100"]) if pd.notna(latest["low_100"]) else 0,
        "low_60": float(latest["low_60"]) if pd.notna(latest["low_60"]) else 0,
        "low_prev40": float(latest["low_prev40"]) if pd.notna(latest["low_prev40"]) else 0,
        "ma60": float(latest["ma60"]) if pd.notna(latest["ma60"]) else 0,
    }

    # ===== 近120日K线（供前端画图） =====
    klines = []
    for _, row in df.tail(120).iterrows():
        klines.append({
            "date": str(row["date"])[:10],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "amount": float(row["amount"]),
        })

    # ===== 交易参数分析（三锚点 + 五个核心公式）=====
    trading = calc_full_trading_analysis(df, capital=100000, risk_budget=0.01)

    return {
        "basic": basic,
        "pool_checks": pool_checks,
        "tier_indicators": tier_indicators,
        "confirmations": confirmations,
        "invalidation": invalidation,
        "trading": trading,
        "klines": klines,
    }
