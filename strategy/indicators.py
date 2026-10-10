"""技术指标计算（pandas 向量化）"""
import pandas as pd
import numpy as np


def add_rolling_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为 DataFrame 添加滚动窗口指标

    输入要求: 按 code, date 排序，包含 code, date, open, high, low, close, volume, amount
    输出: 添加以下列:
        - low_60: 近60日最低价
        - low_prev40: 前40日最低价（60日之前的40日）
        - high_20: 近20日最高价
        - high_60: 近60日最高价
        - high_100: 近100日最高价
        - low_100: 近100日最低价
        - avg_amount_10: 近10日日均成交额
        - avg_amount_100: 近100日日均成交额
        - ma60: 60日均线
        - ma60_slope_5: MA60 5日斜率
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    g = df.groupby("code", group_keys=False)

    # 最低价窗口
    df["low_60"] = g["low"].transform(lambda x: x.rolling(60, min_periods=60).min())
    # 前40日最低价：shift(60) 后 rolling(40).min()
    df["low_prev40"] = g["low"].transform(
        lambda x: x.shift(60).rolling(40, min_periods=40).min()
    )

    # 最高价窗口
    df["high_20"] = g["high"].transform(lambda x: x.rolling(20, min_periods=20).max())
    df["high_60"] = g["high"].transform(lambda x: x.rolling(60, min_periods=60).max())
    df["high_100"] = g["high"].transform(lambda x: x.rolling(100, min_periods=100).max())
    df["low_100"] = g["low"].transform(lambda x: x.rolling(100, min_periods=100).min())

    # 成交额均线
    df["avg_amount_10"] = g["amount"].transform(lambda x: x.rolling(10, min_periods=10).mean())
    df["avg_amount_100"] = g["amount"].transform(lambda x: x.rolling(100, min_periods=100).mean())

    # 均线
    df["ma60"] = g["close"].transform(lambda x: x.rolling(60, min_periods=60).mean())
    df["ma60_slope_5"] = g["ma60"].transform(lambda x: x.diff(5))

    # 成交量均线（用于放量突破判断）
    df["avg_volume_20"] = g["volume"].transform(lambda x: x.rolling(20, min_periods=20).mean())

    return df


def get_latest_per_stock(df: pd.DataFrame) -> pd.DataFrame:
    """取每只股票最新一天的数据（含所有指标）"""
    return df.groupby("code").last().reset_index()


def get_second_low_dates(df: pd.DataFrame, codes: list) -> dict:
    """计算指定股票近60日最低价出现的日期

    Args:
        df: 原始K线数据（按 code, date 排序）
        codes: 股票代码列表

    Returns:
        {code: 'YYYY-MM-DD'} 第二个低点日期映射
    """
    result = {}
    for code in codes:
        code = str(code).zfill(6)
        stock_df = df[df["code"] == code].sort_values("date")
        if len(stock_df) < 60:
            continue
        # 取最近60日
        recent = stock_df.tail(60)
        min_idx = recent["low"].idxmin()
        result[code] = str(recent.loc[min_idx, "date"])
    return result


def days_since_date(date_str: str) -> int:
    """计算给定日期距今多少个自然日"""
    from datetime import datetime
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return (datetime.now() - d).days
    except Exception:
        return 999


def calc_tier_indicators(latest: pd.DataFrame) -> pd.DataFrame:
    """计算分层指标

    添加列:
        - low_raise_pct: 低点抬升幅度 (%)
        - rebound_pct: 距低点回升 (%)
        - room_pct: 距高点空间 (%)
        - tier: complete / partial / pool_only
    """
    df = latest.copy()

    # 低点抬升幅度 = (近60日低点 - 前40日低点) / 前40日低点 * 100
    df["low_raise_pct"] = (df["low_60"] - df["low_prev40"]) / df["low_prev40"] * 100

    # 距低点回升 = (现价 - 百日低点) / 百日低点 * 100
    df["rebound_pct"] = (df["close"] - df["low_100"]) / df["low_100"] * 100

    # 距高点空间 = (百日高点 - 现价) / 百日高点 * 100
    df["room_pct"] = (df["high_100"] - df["close"]) / df["high_100"] * 100

    # 分层判断
    def classify(row):
        conditions = 0
        if row["rebound_pct"] >= 15.0:
            conditions += 1
        if row["room_pct"] <= 15.0:
            conditions += 1
        if row["avg_amount_10"] > 2e8:
            conditions += 1
        if conditions == 3:
            return "complete"
        elif conditions >= 1:
            return "partial"
        return "pool_only"

    df["tier"] = df.apply(classify, axis=1)
    return df


def find_breakout_day(stock_df: pd.DataFrame) -> dict:
    """找到百日高点突破日，返回突破信息

    返回: {date, volume, avg_volume_before, volume_ratio, high}
    """
    if len(stock_df) < 100:
        return {}

    # 找到百日高点出现的位置
    high_100 = stock_df["high"].rolling(100).max()
    max_idx = high_100.idxmax()
    if pd.isna(max_idx):
        return {}

    breakout_row = stock_df.loc[max_idx]
    # 突破前20日均量
    before = stock_df.loc[:max_idx].tail(21).head(20)
    avg_vol_before = before["volume"].mean() if len(before) > 0 else 0

    return {
        "date": breakout_row["date"],
        "volume": float(breakout_row["volume"]),
        "avg_volume_before": float(avg_vol_before),
        "volume_ratio": float(breakout_row["volume"] / avg_vol_before) if avg_vol_before > 0 else 0,
        "high": float(breakout_row["high"]),
    }
