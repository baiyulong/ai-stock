"""实时监控模块：批量扫描选股结果，生成出入场提示

监控维度：
  1. 价格位置：相对 B/L1/L2/T 的位置
  2. 买入信号：接近买入区、回踩确认、放量突破
  3. 止损信号：跌破 L1（减半）、跌破 L2（清仓）
  4. 止盈信号：接近目标 T、突破 T
"""
import pandas as pd
from typing import List, Dict
from db import get_screen_result, load_day_klines
from trading import calc_anchors, calc_buy_price, calc_trading_params, calc_price_position, _to_native
from persistence import get_monitor_ignore_codes


# 内存中保存最新监控结果
_monitor_results: List[Dict] = []
_monitor_time: str = ""


def run_monitor(capital: float = 100000, risk_budget: float = 0.01) -> List[Dict]:
    """对选股结果中的股票执行实时监控

    Returns:
        每只股票的监控结果列表，按紧急程度排序
    """
    global _monitor_results, _monitor_time
    from datetime import datetime
    _monitor_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df = get_screen_result()
    if df.empty:
        _monitor_results = []
        return []

    # 过滤掉监控忽略名单中的股票
    ignore_codes = get_monitor_ignore_codes()
    df = df[~df["code"].astype(str).str.zfill(6).isin(ignore_codes)]
    if df.empty:
        _monitor_results = []
        return []

    # 加载全部K线
    all_klines = load_day_klines(lookback=140)

    results = []
    for _, row in df.iterrows():
        code = str(row["code"]).zfill(6)
        name = row.get("name", code)
        tier = row.get("tier", "pool_only")

        # 取该股票的K线
        stock_df = all_klines[all_klines["code"] == code].sort_values("date")
        if len(stock_df) < 60:
            continue

        try:
            anchors = calc_anchors(stock_df)
            if not anchors:
                continue

            buy_info = calc_buy_price(anchors, mode="auto")
            params = calc_trading_params(anchors, buy_info, capital, risk_budget)
            position = calc_price_position(anchors, params)

            # 第二个低点日期
            low_60_date = row.get("low_60_date", "") if hasattr(row, "get") else ""

            # 紧急程度排序
            urgency = 0
            if position["zone"] == "below_L2":
                urgency = 5  # 最高：清仓
            elif position["zone"] == "L2_L1":
                urgency = 4  # 减半
            elif position["zone"] == "B_T" and position["action"] == "可建仓":
                urgency = 3  # 买入
            elif position["zone"] == "L1_B" and "挂单" in position["action"]:
                urgency = 2  # 接近买入
            elif position["zone"] == "above_T":
                urgency = 1  # 止盈

            results.append({
                "code": code,
                "name": name,
                "tier": tier,
                "urgency": urgency,
                "current_price": anchors["current_price"],
                "B": params["B"],
                "L1": params["L1"],
                "L2": params["L2"],
                "T": params["T"],
                "RR": params["RR"],
                "can_open": params["can_open"],
                "zone": position["zone"],
                "action": position["action"],
                "signals": position["signals"],
                "shares": params["shares"],
                "position_pct": params["position_pct"],
                "low_60_date": str(low_60_date) if low_60_date else "",
            })
        except Exception as e:
            continue

    # 按紧急程度降序
    results.sort(key=lambda x: x["urgency"], reverse=True)
    _monitor_results = _to_native(results)

    # 持久化到数据库
    from persistence import save_monitor_results
    save_monitor_results(_monitor_results)

    return _monitor_results


def get_monitor_results() -> Dict:
    """获取最新监控结果"""
    return {
        "time": _monitor_time,
        "count": len(_monitor_results),
        "alerts": [r for r in _monitor_results if r["urgency"] >= 3],
        "watch": [r for r in _monitor_results if r["urgency"] < 3],
        "all": _monitor_results,
    }


def get_alerts() -> List[Dict]:
    """获取需要立即操作的告警（urgency >= 3）"""
    return [r for r in _monitor_results if r["urgency"] >= 3]
