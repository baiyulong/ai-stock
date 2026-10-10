"""交易参数计算：三锚点价位体系 + 五个核心公式

锚点：
  A  = 结构低点（近60日最低价）
  H  = 百日高点（近100日最高价）
  MA20 = 20日均线

买入价 B（三档取一）：
  回踩档：B = max(MA20, 低点抬升线当前值)
  突破档：放量站上 T=H×1.03 后回踩买入
  等待档：锚点未到位时观察

止损：
  L1 = B × 0.92（先导止损，8%）
  L2 = A × 0.97（硬止损，收盘跌破清零）

目标：
  T = H × 1.03（第一目标，同时是突破触发价）

盈亏比门槛：
  RR = (T - B) / (B - L1) >= 2.0

仓位：
  Q = 资金 × 风险预算 / ((B-L1)/B)，单票上限 15%
"""
import pandas as pd
import numpy as np
from typing import Optional


def calc_anchors(df: pd.DataFrame) -> dict:
    """计算三个锚点

    Args:
        df: 单只股票的日K线 DataFrame，按日期升序

    Returns:
        {A, H, MA20, low_prev40, raise_line, current_price, current_date}
    """
    if len(df) < 60:
        return {}

    latest = df.iloc[-1]

    # 结构低点 A：近60日最低价
    A = float(df["low"].tail(60).min())

    # 百日高点 H
    H = float(df["high"].tail(100).max()) if len(df) >= 100 else float(df["high"].max())

    # MA20
    MA20 = float(df["close"].tail(20).mean())

    # 前40日低点（第一次低点）
    low_prev40 = float(df["low"].iloc[-100:-60].min()) if len(df) >= 100 else float(df["low"].iloc[:-60].min() if len(df) > 60 else A)

    # 低点抬升线：从 (前40日低点位置, low_prev40) 到 (近60日低点位置, A) 的连线
    # 简化：抬升线当前值 = A + (A - low_prev40) * (当前位置 - A的位置) / (A的位置 - 前40低点位置)
    # 更简化的近似：抬升线当前值 ≈ A + (A - low_prev40) * 0.3（假设从低点到现在约30%的时间）
    # 精确计算：找到近60日低点的位置和前40日低点的位置
    low_60_series = df["low"].tail(60)
    A_pos = len(df) - 60 + low_60_series.values.argmin()  # A 在 df 中的位置

    if len(df) >= 100:
        prev40_series = df["low"].iloc[-100:-60]
        prev40_pos = len(df) - 100 + prev40_series.values.argmin()
    else:
        prev40_pos = 0
        low_prev40 = float(df["low"].iloc[:max(0, len(df)-60)].min()) if len(df) > 60 else A

    # 抬升线斜率
    if A_pos > prev40_pos:
        slope = (A - low_prev40) / (A_pos - prev40_pos)
    else:
        slope = 0

    # 抬升线当前值（延伸到最新交易日）
    current_pos = len(df) - 1
    raise_line = low_prev40 + slope * (current_pos - prev40_pos)
    raise_line = max(raise_line, A)  # 抬升线不应低于结构低点A

    return {
        "A": round(A, 2),
        "H": round(H, 2),
        "MA20": round(MA20, 2),
        "low_prev40": round(low_prev40, 2),
        "raise_line": round(raise_line, 2),
        "current_price": round(float(latest["close"]), 2),
        "current_date": str(latest["date"])[:10],
        "A_pos": int(A_pos),
        "prev40_pos": int(prev40_pos),
    }


def calc_buy_price(anchors: dict, mode: str = "auto") -> dict:
    """计算买入价 B（三档取法）

    Args:
        anchors: calc_anchors 的返回值
        mode: "pullback"（回踩档）/ "breakout"（突破档）/ "auto"（自动判断）

    Returns:
        {B, mode, description}
    """
    if not anchors:
        return {}

    A = anchors["A"]
    H = anchors["H"]
    MA20 = anchors["MA20"]
    raise_line = anchors["raise_line"]
    current = anchors["current_price"]
    T = H * 1.03

    # 回踩档：B = max(MA20, 抬升线)
    B_pullback = max(MA20, raise_line)

    # 突破档：放量站上 T 后回踩，B 取突破位附近
    B_breakout = T * 0.98  # 突破后回踩 2%

    if mode == "pullback":
        B = B_pullback
        chosen = "回踩档"
    elif mode == "breakout":
        B = B_breakout
        chosen = "突破档"
    else:
        # auto：现价低于 T 用回踩档，已突破用突破档
        if current >= T:
            B = B_breakout
            chosen = "突破档（已突破百日高点）"
        else:
            B = B_pullback
            chosen = "回踩档"

    return {
        "B": round(B, 2),
        "mode": chosen,
        "B_pullback": round(B_pullback, 2),
        "B_breakout": round(B_breakout, 2),
        "description": f"买入价 {B:.2f}（{chosen}）",
    }


def calc_trading_params(anchors: dict, buy_info: dict,
                        capital: float = 100000,
                        risk_budget: float = 0.01) -> dict:
    """计算完整交易参数（五个核心公式）

    Args:
        anchors: 锚点
        buy_info: calc_buy_price 的返回值
        capital: 总资金
        risk_budget: 单票风险预算（默认 1%）

    Returns:
        {B, L1, L2, T, RR, position_pct, shares, risk_amount, can_open, reason}
    """
    if not anchors or not buy_info:
        return {}

    A = anchors["A"]
    H = anchors["H"]
    B = buy_info["B"]

    # L1 先导止损：B × 0.92
    L1 = B * 0.92

    # L2 硬止损：A × 0.97
    L2 = A * 0.97

    # T 目标：H × 1.03
    T = H * 1.03

    # 盈亏比 RR = (T - B) / (B - L1)
    risk_per_share = B - L1
    reward_per_share = T - B
    RR = reward_per_share / risk_per_share if risk_per_share > 0 else 0

    # 仓位 Q = 资金 × 风险预算 / ((B-L1)/B)
    risk_amount = capital * risk_budget
    loss_pct = risk_per_share / B if B > 0 else 0
    position_value = risk_amount / loss_pct if loss_pct > 0 else 0
    position_pct = position_value / capital * 100

    # 单票上限 15%
    if position_pct > 15:
        position_pct = 15
        position_value = capital * 0.15

    # 股数（取整到百股）
    shares = int(position_value / B / 100) * 100 if B > 0 else 0

    # 是否可开仓
    can_open = RR >= 2.0 and shares > 0
    reason = ""
    if RR < 2.0:
        reason = f"盈亏比 {RR:.2f} < 2.0，不满足开仓门槛"
    elif shares == 0:
        reason = "计算股数为0"
    else:
        reason = "满足开仓条件"

    return {
        "B": round(B, 2),
        "L1": round(L1, 2),
        "L2": round(L2, 2),
        "T": round(T, 2),
        "RR": round(RR, 2),
        "position_pct": round(position_pct, 2),
        "position_value": round(position_value, 2),
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "can_open": can_open,
        "reason": reason,
        "capital": capital,
        "risk_budget": risk_budget,
    }


def calc_price_position(anchors: dict, params: dict) -> dict:
    """判断当前价格相对交易参数的位置，生成出入场提示

    Returns:
        {zone, signals[], action}
        zone: "below_L2" / "L2_L1" / "L1_B" / "B_T" / "above_T"
    """
    if not anchors or not params:
        return {}

    current = anchors["current_price"]
    B = params["B"]
    L1 = params["L1"]
    L2 = params["L2"]
    T = params["T"]

    signals = []
    action = "观望"

    if current < L2:
        zone = "below_L2"
        signals.append(f"现价 {current:.2f} 已跌破硬止损 L2={L2:.2f}")
        action = "立即清仓"
    elif current < L1:
        zone = "L2_L1"
        signals.append(f"现价 {current:.2f} 跌破先导止损 L1={L1:.2f}")
        action = "减半仓"
    elif current < B:
        zone = "L1_B"
        dist_to_B = (B - current) / B * 100
        signals.append(f"现价 {current:.2f} 在买入区下方，距 B={B:.2f} 还有 {dist_to_B:.1f}%")
        if dist_to_B < 3:
            signals.append("接近买入区，可挂单等待")
            action = "挂单等待买入"
        else:
            action = "观望等待回踩"
    elif current < T:
        zone = "B_T"
        dist_to_T = (T - current) / T * 100
        signals.append(f"现价 {current:.2f} 在持仓区，距目标 T={T:.2f} 还有 {dist_to_T:.1f}%")
        # 检查是否刚买入
        if current <= B * 1.02:
            signals.append("刚进入买入区，可建仓")
            action = "可建仓"
        else:
            action = "持有"
    else:
        zone = "above_T"
        signals.append(f"现价 {current:.2f} 已突破目标 T={T:.2f}")
        action = "考虑止盈或加仓"

    return {
        "zone": zone,
        "current_price": current,
        "signals": signals,
        "action": action,
    }


def _to_native(obj):
    """递归将 numpy 类型转为 Python 原生类型"""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def calc_full_trading_analysis(df: pd.DataFrame,
                                capital: float = 100000,
                                risk_budget: float = 0.01) -> dict:
    """计算单只股票的完整交易分析

    Returns:
        {anchors, buy_info, params, position}
    """
    anchors = calc_anchors(df)
    if not anchors:
        return {"error": "数据不足"}

    buy_info = calc_buy_price(anchors, mode="auto")
    params = calc_trading_params(anchors, buy_info, capital, risk_budget)
    position = calc_price_position(anchors, params)

    return _to_native({
        "anchors": anchors,
        "buy_info": buy_info,
        "params": params,
        "position": position,
    })
