"""持仓与待买监控模块

待买列表：监控是否进入买入区域（现价 <= B 且 RR >= 2）
持仓列表：监控是否达到止损（跌破L1/L2）或止盈（达到T）
"""
import pandas as pd
from typing import List, Dict
from db import load_day_klines
from trading import calc_anchors, calc_buy_price, calc_trading_params, _to_native
from persistence import (
    list_watch_buy, list_positions, add_alert,
    get_unread_alert_count, list_alerts, mark_alert_read, mark_all_alerts_read
)


def _get_latest_price(df: pd.DataFrame) -> float:
    """获取最新收盘价"""
    if df.empty:
        return 0
    return float(df.iloc[-1]["close"])


def check_watch_buy() -> List[Dict]:
    """检查待买列表，返回符合买入条件的股票

    条件：现价 <= B（买入价）且 RR >= 2
    """
    watch_list = list_watch_buy()
    if not watch_list:
        return []

    all_klines = load_day_klines(lookback=140)
    results = []

    for item in watch_list:
        code = str(item["code"]).zfill(6)
        name = item.get("name", "")
        target_price = item.get("target_buy_price", 0)

        df = all_klines.get(code)
        if df is None or df.empty or len(df) < 60:
            continue

        current_price = _get_latest_price(df)
        anchors = calc_anchors(df)
        if not anchors:
            continue

        buy_info = calc_buy_price(anchors, mode="auto")
        params = calc_trading_params(anchors, buy_info, capital=100000, risk_budget=0.01)

        B = params["B"]
        # 如果用户设置了目标买入价，优先用用户设置的
        if target_price and target_price > 0:
            B = target_price

        RR = params["RR"]
        can_buy = current_price <= B and RR >= 2

        result = {
            "code": code,
            "name": name,
            "current_price": round(current_price, 2),
            "B": round(B, 2),
            "L1": params["L1"],
            "L2": params["L2"],
            "T": params["T"],
            "RR": RR,
            "can_buy": can_buy,
            "distance_pct": round((B - current_price) / B * 100, 2) if B > 0 else 0,
            "signals": params.get("signals", []),
        }

        if can_buy:
            # 生成告警（避免重复：检查最近是否已有同类型未读告警）
            existing = list_alerts(unread_only=True, limit=100)
            already_alerted = any(
                a["code"] == code and a["alert_type"] == "buy" for a in existing
            )
            if not already_alerted:
                add_alert(
                    alert_type="buy",
                    code=code,
                    name=name,
                    title=f"买入信号：{name}",
                    message=f"现价 {current_price:.2f} 已进入买入区 B={B:.2f}，RR={RR:.2f}≥2.0，建议建仓",
                    current_price=current_price,
                    trigger_price=B,
                )

        results.append(result)

    return _to_native(results)


def check_positions() -> List[Dict]:
    """检查持仓列表，返回止损/止盈信号

    条件：
    - 现价 <= L2 → 清仓信号
    - 现价 <= L1 → 减半信号
    - 现价 >= T → 止盈信号
    """
    positions = list_positions()
    if not positions:
        return []

    all_klines = load_day_klines(lookback=140)
    results = []

    for item in positions:
        code = str(item["code"]).zfill(6)
        name = item.get("name", "")
        buy_price = item.get("buy_price", 0)
        shares = item.get("shares", 0)

        df = all_klines.get(code)
        if df is None or df.empty or len(df) < 60:
            continue

        current_price = _get_latest_price(df)
        anchors = calc_anchors(df)
        if not anchors:
            continue

        buy_info = calc_buy_price(anchors, mode="auto")
        params = calc_trading_params(anchors, buy_info, capital=100000, risk_budget=0.01)

        L1 = params["L1"]
        L2 = params["L2"]
        T = params["T"]
        profit_pct = (current_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
        market_value = current_price * shares

        # 判断信号
        signal_type = ""
        signal_level = 0  # 0=无, 1=止盈, 2=减半, 3=清仓
        if current_price <= L2:
            signal_type = "清仓"
            signal_level = 3
        elif current_price <= L1:
            signal_type = "减半仓"
            signal_level = 2
        elif current_price >= T:
            signal_type = "止盈"
            signal_level = 1

        result = {
            "code": code,
            "name": name,
            "buy_price": round(buy_price, 2),
            "shares": shares,
            "current_price": round(current_price, 2),
            "profit_pct": round(profit_pct, 2),
            "market_value": round(market_value, 2),
            "L1": L1,
            "L2": L2,
            "T": T,
            "signal_type": signal_type,
            "signal_level": signal_level,
            "has_signal": signal_level > 0,
        }

        if signal_level > 0:
            existing = list_alerts(unread_only=True, limit=100)
            already_alerted = any(
                a["code"] == code and a["alert_type"] == "sell" for a in existing
            )
            if not already_alerted:
                alert_title = f"{signal_type}信号：{name}"
                if signal_level == 3:
                    msg = f"现价 {current_price:.2f} 已跌破硬止损 L2={L2:.2f}，建议立即清仓"
                elif signal_level == 2:
                    msg = f"现价 {current_price:.2f} 已跌破先导止损 L1={L1:.2f}，建议减半仓"
                else:
                    msg = f"现价 {current_price:.2f} 已达到目标 T={T:.2f}，浮盈 {profit_pct:.1f}%，建议止盈"
                add_alert(
                    alert_type="sell",
                    code=code,
                    name=name,
                    title=alert_title,
                    message=msg,
                    current_price=current_price,
                    trigger_price=L2 if signal_level == 3 else (L1 if signal_level == 2 else T),
                )

        results.append(result)

    # 按信号级别降序
    results.sort(key=lambda x: x["signal_level"], reverse=True)
    return _to_native(results)


def run_portfolio_check() -> Dict:
    """执行一次完整的持仓+待买检查"""
    buy_signals = check_watch_buy()
    position_signals = check_positions()

    buy_alerts = [r for r in buy_signals if r["can_buy"]]
    sell_alerts = [r for r in position_signals if r["has_signal"]]

    return {
        "watch_buy": buy_signals,
        "positions": position_signals,
        "buy_alert_count": len(buy_alerts),
        "sell_alert_count": len(sell_alerts),
        "total_alerts": len(buy_alerts) + len(sell_alerts),
    }


def get_alerts(unread_only: bool = False, limit: int = 50) -> List[Dict]:
    """获取告警列表"""
    return list_alerts(unread_only=unread_only, limit=limit)


def get_unread_count() -> int:
    """获取未读告警数量"""
    return get_unread_alert_count()


def read_alert(alert_id: int):
    """标记单条告警已读"""
    mark_alert_read(alert_id)


def read_all_alerts():
    """标记所有告警已读"""
    mark_all_alerts_read()
