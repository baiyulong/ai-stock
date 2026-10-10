"""数据加载与持久化（通过 Go 服务 HTTP API 获取数据，SQLite 保存选股结果）"""
import io
import pandas as pd
import requests
from typing import Optional

import persistence

# Go 服务地址
GO_SERVICE_URL = "http://127.0.0.1:18080"


def load_day_klines(lookback: int = 140) -> pd.DataFrame:
    """从 Go 服务加载日K线数据（CSV 格式）"""
    url = f"{GO_SERVICE_URL}/api/screener/export-kline?lookback={lookback}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), dtype={"code": str, "exchange": str})
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = df["code"].str.zfill(6)
    return df


def load_stock_info() -> pd.DataFrame:
    """从 Go 服务加载股票信息（代码+名称+是否ST）"""
    try:
        url = f"{GO_SERVICE_URL}/api/screener/stock-info"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), dtype={"code": str})
        if df.empty:
            return pd.DataFrame(columns=["code", "name", "exchange", "is_st", "is_etf", "decimal"])
        df["code"] = df["code"].str.zfill(6)
        df["is_st"] = df["is_st"].astype(bool)
        return df
    except Exception as e:
        print(f"加载股票信息失败: {e}")
        return pd.DataFrame(columns=["code", "name", "exchange", "is_st", "is_etf", "decimal"])


def save_screen_result(run_id: str, df: pd.DataFrame):
    """保存选股结果到 SQLite"""
    run_at = df["run_at"].iloc[0] if "run_at" in df.columns and len(df) > 0 else ""
    persistence.save_run_results(run_id, run_at, df)


def get_screen_result(run_id: Optional[str] = None) -> pd.DataFrame:
    """获取选股结果（从 SQLite 读取）"""
    return persistence.load_run_results(run_id)


def get_latest_run_id() -> Optional[str]:
    """获取最近一次运行ID"""
    return persistence.get_latest_run_id()
