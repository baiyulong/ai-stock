"""选股策略 FastAPI 服务"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from config import SERVICE_HOST, SERVICE_PORT
from screener import run_screener
from detail import analyze_stock
from db import get_screen_result, get_latest_run_id
from scheduler import start_scheduler, get_invalidation_alerts, run_invalidation_check
import scheduler
from backtest import run_backtest
from single_backtest import run_single_backtest
from monitor import run_monitor, get_monitor_results, get_alerts
from portfolio import (
    run_portfolio_check, check_watch_buy, check_positions,
    get_alerts as get_portfolio_alerts, get_unread_count, read_alert, read_all_alerts
)
import persistence

app = FastAPI(title="TDX 选股策略服务", version="1.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SyncRequest(BaseModel):
    codes: Optional[List[str]] = None
    concurrency: Optional[int] = 8
    lookback: Optional[int] = 130
    incremental: Optional[bool] = True


class WebhookConfig(BaseModel):
    url: str
    enabled: bool = True


class SingleBacktestRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 100000.0


# Webhook 配置（启动时从数据库加载）
_webhook_url: Optional[str] = persistence.get_config("webhook_url", "") or None
_webhook_enabled: bool = persistence.get_config("webhook_enabled", "false") == "true"


@app.get("/api/screener/health")
async def health():
    """健康检查"""
    return {"code": 0, "message": "success", "data": {"status": "ok"}}


@app.post("/api/screener/run")
async def run_strategy():
    """执行选股策略"""
    try:
        result = run_screener()
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/results")
async def get_results(run_id: Optional[str] = None):
    """获取选股结果"""
    try:
        df = get_screen_result(run_id)
        if df.empty:
            return {"code": 0, "message": "无选股结果", "data": {"run_id": run_id, "count": 0, "results": []}}

        results = []
        for _, row in df.iterrows():
            item = {}
            for col in df.columns:
                v = row[col]
                if hasattr(v, "item"):
                    v = v.item()
                elif hasattr(v, "isoformat"):
                    v = str(v)
                item[col] = v
            results.append(item)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "run_id": run_id or get_latest_run_id(),
                "count": len(results),
                "results": results,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/stock/{code}")
async def get_stock_detail(code: str):
    """获取单只股票详细诊断"""
    try:
        result = analyze_stock(code)
        if "error" in result:
            return {"code": -1, "message": result["error"], "data": None}
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/runs")
async def list_runs():
    """获取历史运行记录（SQLite 持久化）"""
    runs = persistence.list_runs(limit=20)
    return {"code": 0, "message": "success", "data": runs}


@app.get("/api/screener/invalidation")
async def get_invalidation():
    """获取证伪告警列表（当前运行）"""
    alerts = get_invalidation_alerts()
    return {"code": 0, "message": "success", "data": {"count": len(alerts), "alerts": alerts}}


@app.get("/api/screener/invalidation/history")
async def get_invalidation_history(days: int = 7):
    """获取证伪历史记录"""
    history = persistence.get_invalidation_history(days=days)
    return {"code": 0, "message": "success", "data": {"count": len(history), "history": history}}


@app.post("/api/screener/invalidation/check")
async def run_invalidation():
    """手动触发证伪监控"""
    run_invalidation_check()
    alerts = get_invalidation_alerts()
    return {"code": 0, "message": "证伪监控完成", "data": {"count": len(alerts), "alerts": alerts}}


@app.post("/api/screener/webhook")
async def set_webhook(config: WebhookConfig):
    """设置 Webhook（持久化）"""
    global _webhook_url, _webhook_enabled
    _webhook_url = config.url
    _webhook_enabled = config.enabled
    persistence.set_config("webhook_url", config.url)
    persistence.set_config("webhook_enabled", "true" if config.enabled else "false")
    scheduler.set_webhook(config.url, config.enabled)
    return {"code": 0, "message": "Webhook 已保存", "data": {"url": _webhook_url, "enabled": _webhook_enabled}}


@app.get("/api/screener/webhook")
async def get_webhook():
    """获取当前 Webhook 配置"""
    return {"code": 0, "message": "success", "data": {"url": _webhook_url, "enabled": _webhook_enabled}}


@app.post("/api/screener/webhook/test")
async def test_webhook():
    """测试 Webhook 推送"""
    if not _webhook_url:
        return {"code": -1, "message": "Webhook 未配置"}
    try:
        import requests
        from datetime import datetime
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"【交易提醒】Webhook 测试成功\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n配置正常，可以接收买入/卖出信号推送"
            }
        }
        resp = requests.post(_webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            return {"code": 0, "message": "测试消息已发送，请查看企业微信", "data": {"status": resp.status_code}}
        # 尝试 GET 方式（Server酱）
        params = {"text": "交易提醒 Webhook 测试", "desp": "配置正常，可以接收买入/卖出信号推送"}
        resp2 = requests.get(_webhook_url, params=params, timeout=10)
        return {"code": 0 if resp2.status_code == 200 else -1,
                "message": "测试消息已发送" if resp2.status_code == 200 else "发送失败",
                "data": {"status": resp2.status_code}}
    except Exception as e:
        return {"code": -1, "message": f"测试失败: {str(e)}"}


# ========== 时区设置 ==========

@app.get("/api/screener/timezone")
async def get_timezone():
    """获取当前时区配置"""
    tz = persistence.get_config("timezone", "Asia/Shanghai")
    from datetime import datetime
    return {
        "code": 0,
        "message": "success",
        "data": {
            "timezone": tz,
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    }


@app.post("/api/screener/timezone")
async def set_timezone(config: dict):
    """设置时区"""
    tz = config.get("timezone", "Asia/Shanghai")
    persistence.set_config("timezone", tz)
    return {"code": 0, "message": "时区已保存", "data": {"timezone": tz}}


@app.post("/api/screener/backtest")
async def run_backtest_endpoint(as_of_days_ago: int = 20, hold_days: int = 20):
    """执行策略回测"""
    try:
        result = run_backtest(as_of_days_ago=as_of_days_ago, hold_days=hold_days)
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/backtest/{code}")
async def run_single_backtest_endpoint(code: str, req: SingleBacktestRequest):
    """单票逐K线回测"""
    try:
        result = run_single_backtest(
            code=code,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/monitor")
async def run_monitor_endpoint(capital: float = 100000, risk_budget: float = 0.01):
    """执行实时监控（扫描选股结果，生成出入场提示）"""
    try:
        results = run_monitor(capital=capital, risk_budget=risk_budget)
        data = get_monitor_results()
        return {"code": 0, "message": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/screener/monitor")
async def get_monitor():
    """获取最新监控结果（优先从内存，其次从数据库）"""
    data = get_monitor_results()
    if data["count"] == 0:
        # 从数据库加载
        results, run_at = persistence.load_monitor_results()
        if results:
            data = {
                "time": run_at,
                "count": len(results),
                "alerts": [r for r in results if r["urgency"] >= 3],
                "watch": [r for r in results if r["urgency"] < 3],
                "all": results,
            }
    return {"code": 0, "message": "success", "data": data}


@app.get("/api/screener/monitor/alerts")
async def get_monitor_alerts():
    """获取需要立即操作的告警"""
    alerts = get_alerts()
    return {"code": 0, "message": "success", "data": {"count": len(alerts), "alerts": alerts}}


# ========== 监控忽略名单 ==========

class IgnoreRequest(BaseModel):
    code: str
    name: Optional[str] = ""
    reason: Optional[str] = ""


@app.get("/api/screener/monitor/ignore")
async def list_ignore():
    """获取监控忽略名单"""
    items = persistence.list_monitor_ignore()
    return {"code": 0, "message": "success", "data": items}


@app.post("/api/screener/monitor/ignore")
async def add_ignore(req: IgnoreRequest):
    """添加股票到监控忽略名单"""
    persistence.add_monitor_ignore(req.code, req.name or "", req.reason or "")
    return {"code": 0, "message": "success", "data": {"code": req.code, "ignored": True}}


@app.delete("/api/screener/monitor/ignore/{code}")
async def remove_ignore(code: str):
    """从监控忽略名单中移除股票"""
    persistence.remove_monitor_ignore(code)
    return {"code": 0, "message": "success", "data": {"code": code, "ignored": False}}


# ========== 待买列表 ==========

class WatchBuyRequest(BaseModel):
    code: str
    name: Optional[str] = ""
    target_buy_price: Optional[float] = 0
    notes: Optional[str] = ""


@app.get("/api/portfolio/watch-buy")
async def list_watch_buy():
    """获取待买列表"""
    items = persistence.list_watch_buy()
    return {"code": 0, "message": "success", "data": items}


@app.post("/api/portfolio/watch-buy")
async def add_watch_buy(req: WatchBuyRequest):
    """添加待买股票"""
    persistence.add_watch_buy(req.code, req.name or "", req.target_buy_price or 0, req.notes or "")
    return {"code": 0, "message": "success", "data": {"code": req.code}}


@app.delete("/api/portfolio/watch-buy/{code}")
async def remove_watch_buy(code: str):
    """移除待买股票"""
    persistence.remove_watch_buy(code)
    return {"code": 0, "message": "success", "data": {"code": code}}


@app.post("/api/portfolio/watch-buy/check")
async def check_watch_buy_endpoint():
    """检查待买列表的买入信号"""
    results = check_watch_buy()
    return {"code": 0, "message": "success", "data": results}


# ========== 持仓列表 ==========

class PositionRequest(BaseModel):
    code: str
    name: Optional[str] = ""
    buy_price: float
    shares: int
    buy_date: Optional[str] = ""
    notes: Optional[str] = ""


@app.get("/api/portfolio/positions")
async def list_positions():
    """获取持仓列表"""
    items = persistence.list_positions()
    return {"code": 0, "message": "success", "data": items}


@app.post("/api/portfolio/positions")
async def add_position(req: PositionRequest):
    """添加持仓股票"""
    persistence.add_position(req.code, req.name or "", req.buy_price, req.shares,
                             req.buy_date or "", req.notes or "")
    return {"code": 0, "message": "success", "data": {"code": req.code}}


@app.delete("/api/portfolio/positions/{code}")
async def remove_position(code: str):
    """移除持仓股票"""
    persistence.remove_position(code)
    return {"code": 0, "message": "success", "data": {"code": code}}


@app.post("/api/portfolio/positions/check")
async def check_positions_endpoint():
    """检查持仓列表的止损/止盈信号"""
    results = check_positions()
    return {"code": 0, "message": "success", "data": results}


# ========== 告警 ==========

@app.get("/api/portfolio/alerts")
async def get_alerts_endpoint(unread_only: bool = False, limit: int = 50):
    """获取告警列表"""
    alerts = get_portfolio_alerts(unread_only=unread_only, limit=limit)
    unread = get_unread_count()
    return {"code": 0, "message": "success", "data": {"alerts": alerts, "unread_count": unread}}


@app.post("/api/portfolio/alerts/{alert_id}/read")
async def read_alert_endpoint(alert_id: int):
    """标记单条告警已读"""
    read_alert(alert_id)
    return {"code": 0, "message": "success"}


@app.post("/api/portfolio/alerts/read-all")
async def read_all_alerts_endpoint():
    """标记所有告警已读"""
    read_all_alerts()
    return {"code": 0, "message": "success"}


@app.post("/api/portfolio/check")
async def portfolio_check_endpoint():
    """执行一次完整的持仓+待买检查（生成告警）"""
    result = run_portfolio_check()
    return {"code": 0, "message": "success", "data": result}


@app.on_event("startup")
async def startup_event():
    """服务启动时启动定时任务"""
    start_scheduler()
    # 同步 Webhook 配置到 scheduler
    if _webhook_url:
        scheduler.set_webhook(_webhook_url, _webhook_enabled)


if __name__ == "__main__":
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT)
