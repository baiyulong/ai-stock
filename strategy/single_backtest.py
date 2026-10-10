"""单票历史回测引擎：逐K线模拟底部抬高形态交易"""
import pandas as pd
import numpy as np
from typing import Optional
from db import load_day_klines


def _calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算单票技术指标"""
    df = df.copy()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["low_60"] = df["low"].rolling(60).min()
    df["high_60"] = df["high"].rolling(60).max()
    df["high_20"] = df["high"].rolling(20).max()
    df["high_100"] = df["high"].rolling(100).max()
    df["low_100"] = df["low"].rolling(100).min()
    df["avg_amount_10"] = df["amount"].rolling(10).mean()
    # 前40日最低（不含当前60日窗口）
    df["low_prev40"] = df["low"].shift(60).rolling(40).min()
    # 低点抬升线 = 前40日最低
    df["support_line"] = df["low_prev40"]
    return df


def _check_structure_formed(row: pd.Series) -> bool:
    """检查底部抬高结构是否形成"""
    if pd.isna(row.get("low_60")) or pd.isna(row.get("low_prev40")):
        return False
    if pd.isna(row.get("high_20")) or pd.isna(row.get("high_60")):
        return False
    if pd.isna(row.get("high_100")) or pd.isna(row.get("low_100")):
        return False
    # 结构双窗：近60日最低 > 前40日最低
    if row["low_60"] <= row["low_prev40"]:
        return False
    # 新高确认：20日内创60日新高
    if row["high_20"] < row["high_60"]:
        return False
    # 波幅证据：百日振幅 >= 25%
    amplitude = (row["high_100"] - row["low_100"]) / row["low_100"]
    if amplitude < 0.25:
        return False
    return True


def _calc_trade_params(row: pd.Series) -> dict:
    """计算三锚点五公式交易参数"""
    A = float(row["low_60"])  # 结构低点
    H = float(row["high_100"])  # 百日高点
    ma20 = float(row["ma20"]) if not pd.isna(row["ma20"]) else A
    support = float(row["support_line"]) if not pd.isna(row["support_line"]) else A

    # B 买入价：回踩 = max(MA20, 抬升线)
    B = max(ma20, support)
    L1 = B * 0.92  # 先导止损
    L2 = A * 0.97  # 硬止损
    T = H * 1.03  # 目标价
    RR = (T - B) / (B - L1) if (B - L1) > 0 else 0

    return {
        "A": round(A, 2),
        "H": round(H, 2),
        "B": round(B, 2),
        "L1": round(L1, 2),
        "L2": round(L2, 2),
        "T": round(T, 2),
        "RR": round(RR, 2),
        "ma20": round(ma20, 2),
        "support": round(support, 2),
    }


def run_single_backtest(
    code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000.0,
) -> dict:
    """单票逐K线回测

    Args:
        code: 股票代码
        start_date: 回测开始日期 YYYY-MM-DD
        end_date: 回测结束日期 YYYY-MM-DD
        initial_capital: 初始资金

    Returns:
        回测结果，包含交易记录、收益统计、K线数据（带买卖标记）
    """
    # 加载数据（多加载100天用于指标计算）
    df = load_day_klines(lookback=300)
    if df.empty:
        return {"error": "无数据"}

    df = df[df["code"] == code].copy()
    if df.empty:
        return {"error": f"股票 {code} 无数据"}

    df = df.sort_values("date").reset_index(drop=True)
    df = _calc_indicators(df)

    # 确定回测区间
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]

    if len(df) < 60:
        return {"error": f"回测区间数据不足（需要至少60个交易日，当前{len(df)}天）"}

    df = df.reset_index(drop=True)

    # 回测状态
    cash = initial_capital
    position = 0  # 持仓数量
    position_price = 0  # 持仓成本
    trades = []  # 交易记录
    structure_found = False  # 是否已发现底部结构
    trade_params = None  # 当前交易参数
    half_sold = False  # 是否已减半

    # 用于K线标注
    buy_signals = []  # [(date, price)]
    sell_signals = []  # [(date, price, reason)]
    structure_dates = []  # 结构形成日期

    for i in range(len(df)):
        row = df.iloc[i]
        date = str(row["date"])[:10]
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        # 空仓状态：寻找底部结构
        if position == 0:
            if _check_structure_formed(row):
                if not structure_found:
                    structure_found = True
                    structure_dates.append(date)
                    trade_params = _calc_trade_params(row)

                # 检查是否进入买入区：现价 <= B 且 RR >= 2
                if trade_params and close <= trade_params["B"] and trade_params["RR"] >= 2.0:
                    # 计算仓位：资金1%风险 / (B-L1)/B，上限15%
                    risk_per_share = trade_params["B"] - trade_params["L1"]
                    if risk_per_share > 0:
                        risk_amount = cash * 0.01
                        shares_by_risk = int(risk_amount / risk_per_share)
                        max_shares = int(cash * 0.15 / trade_params["B"])
                        shares = min(shares_by_risk, max_shares)
                        shares = max(shares, 100)  # 至少1手
                        shares = (shares // 100) * 100  # 整手

                        cost = shares * trade_params["B"]
                        if cost <= cash and shares > 0:
                            cash -= cost
                            position = shares
                            position_price = trade_params["B"]
                            half_sold = False
                            buy_signals.append((date, trade_params["B"]))
                            trades.append({
                                "type": "buy",
                                "date": date,
                                "price": trade_params["B"],
                                "shares": shares,
                                "amount": round(cost, 2),
                                "params": trade_params,
                            })

        # 持仓状态：监控止损止盈
        elif position > 0 and trade_params:
            # 硬止损：跌破 L2，清仓
            if low <= trade_params["L2"]:
                sell_price = trade_params["L2"]
                proceeds = position * sell_price
                profit = (sell_price - position_price) * position
                cash += proceeds
                sell_signals.append((date, sell_price, "硬止损清仓"))
                trades.append({
                    "type": "sell",
                    "date": date,
                    "price": sell_price,
                    "shares": position,
                    "amount": round(proceeds, 2),
                    "profit": round(profit, 2),
                    "reason": "硬止损清仓",
                })
                position = 0
                structure_found = False
                trade_params = None
                half_sold = False

            # 先导止损：跌破 L1，减半
            elif low <= trade_params["L1"] and not half_sold:
                sell_shares = position // 2
                sell_shares = (sell_shares // 100) * 100
                if sell_shares > 0:
                    sell_price = trade_params["L1"]
                    proceeds = sell_shares * sell_price
                    profit = (sell_price - position_price) * sell_shares
                    cash += proceeds
                    position -= sell_shares
                    half_sold = True
                    sell_signals.append((date, sell_price, "先导止损减半"))
                    trades.append({
                        "type": "sell",
                        "date": date,
                        "price": sell_price,
                        "shares": sell_shares,
                        "amount": round(proceeds, 2),
                        "profit": round(profit, 2),
                        "reason": "先导止损减半",
                    })

            # 止盈：达到 T，清仓
            elif high >= trade_params["T"]:
                sell_price = trade_params["T"]
                proceeds = position * sell_price
                profit = (sell_price - position_price) * position
                cash += proceeds
                sell_signals.append((date, sell_price, "止盈清仓"))
                trades.append({
                    "type": "sell",
                    "date": date,
                    "price": sell_price,
                    "shares": position,
                    "amount": round(proceeds, 2),
                    "profit": round(profit, 2),
                    "reason": "止盈清仓",
                })
                position = 0
                structure_found = False
                trade_params = None
                half_sold = False

    # 回测结束时如果还有持仓，按最后收盘价平仓
    if position > 0:
        last_close = float(df.iloc[-1]["close"])
        last_date = str(df.iloc[-1]["date"])[:10]
        proceeds = position * last_close
        profit = (last_close - position_price) * position
        cash += proceeds
        sell_signals.append((last_date, last_close, "回测结束平仓"))
        trades.append({
            "type": "sell",
            "date": last_date,
            "price": last_close,
            "shares": position,
            "amount": round(proceeds, 2),
            "profit": round(profit, 2),
            "reason": "回测结束平仓",
        })
        position = 0

    # 统计收益
    final_value = cash
    total_return = (final_value - initial_capital) / initial_capital * 100

    # 计算每笔完整交易的收益
    complete_trades = []
    buy_trades = [t for t in trades if t["type"] == "buy"]
    sell_trades = [t for t in trades if t["type"] == "sell"]

    # 简单统计
    sell_profits = [t["profit"] for t in sell_trades if "profit" in t]
    win_trades = [p for p in sell_profits if p > 0]
    loss_trades = [p for p in sell_profits if p <= 0]

    # 最大回撤计算
    equity_curve = []
    temp_cash = initial_capital
    temp_position = 0
    temp_price = 0
    for i in range(len(df)):
        row = df.iloc[i]
        close = float(row["close"])
        # 简化：用交易记录计算权益曲线
        pass

    # 构建K线数据（带买卖标记）
    klines = []
    for i in range(len(df)):
        row = df.iloc[i]
        date = str(row["date"])[:10]
        marker = None
        marker_type = None
        for d, p in buy_signals:
            if d == date:
                marker = p
                marker_type = "buy"
        for d, p, r in sell_signals:
            if d == date:
                marker = p
                marker_type = "sell"
        klines.append({
            "date": date,
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
            "marker": marker,
            "marker_type": marker_type,
        })

    return {
        "code": code,
        "start_date": str(df.iloc[0]["date"])[:10],
        "end_date": str(df.iloc[-1]["date"])[:10],
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return, 2),
        "total_trades": len(sell_trades),
        "win_count": len(win_trades),
        "loss_count": len(loss_trades),
        "win_rate": round(len(win_trades) / len(sell_trades) * 100, 2) if sell_trades else 0,
        "total_profit": round(sum(sell_profits), 2),
        "avg_profit": round(np.mean(sell_profits), 2) if sell_profits else 0,
        "max_profit": round(max(sell_profits), 2) if sell_profits else 0,
        "max_loss": round(min(sell_profits), 2) if sell_profits else 0,
        "structure_count": len(structure_dates),
        "trades": trades,
        "klines": klines,
    }
