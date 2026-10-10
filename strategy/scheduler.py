"""定时任务：收盘后自动同步+选股+证伪监控，交易时段自动监控持仓/待买"""
import time
import threading
import logging
import requests
from datetime import datetime

from screener import run_screener
from detail import analyze_stock
from db import get_screen_result, get_latest_run_id
from portfolio import run_portfolio_check, get_unread_count
import persistence

logger = logging.getLogger(__name__)

GO_SERVICE_URL = "http://127.0.0.1:18080"

# 证伪监控结果（内存中）
invalidation_alerts = []

# Webhook
_webhook_url = None
_webhook_enabled = False


def set_webhook(url: str, enabled: bool = True):
    global _webhook_url, _webhook_enabled
    _webhook_url = url
    _webhook_enabled = enabled


def _send_webhook(alerts: list, alert_type: str = "invalidation"):
    """发送告警 Webhook（通用 POST JSON 格式，兼容企业微信/钉钉/Server酱等）"""
    if not _webhook_enabled or not _webhook_url or not alerts:
        return
    try:
        # 构造消息内容
        lines = []
        for a in alerts:
            if alert_type == "invalidation":
                lines.append(f"破位: {a.get('name','')}({a.get('code','')}) 收盘{a.get('current_close','')} 跌破{a.get('invalidate_price','')}")
            else:
                lines.append(f"{a.get('title','')}: {a.get('message','')}")

        title = f"【交易提醒】{len(alerts)} 条告警"
        content = "\n".join(lines)

        # 通用 JSON 格式（企业微信机器人/钉钉兼容）
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"{title}\n{content}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }

        # 尝试 POST JSON
        resp = requests.post(_webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            # 尝试 GET 方式（Server酱兼容）
            params = {"text": title, "desp": content}
            requests.get(_webhook_url, params=params, timeout=10)

        logger.info(f"Webhook 已发送: {len(alerts)} 条 {alert_type} 告警")
    except Exception as e:
        logger.error(f"Webhook 发送失败: {e}")


def trigger_sync():
    """触发 Go 服务增量同步"""
    try:
        resp = requests.post(
            f"{GO_SERVICE_URL}/api/screener/sync",
            json={"concurrency": 8, "lookback": 140, "incremental": True},
            timeout=10,
        )
        data = resp.json()
        logger.info(f"同步任务已触发: {data.get('message', '')}")
        return True
    except Exception as e:
        logger.error(f"触发同步失败: {e}")
        return False


def wait_for_sync(timeout: int = 600):
    """等待同步完成"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{GO_SERVICE_URL}/api/screener/sync-status", timeout=5)
            data = resp.json().get("data", {})
            status = data.get("status", "idle")
            if status in ("success", "partial", "failed"):
                logger.info(f"同步完成: status={status}, done={data.get('done')}, failed={data.get('failed')}")
                return True
            time.sleep(10)
        except Exception as e:
            logger.error(f"查询同步状态失败: {e}")
            time.sleep(10)
    logger.warning("同步超时")
    return False


def run_invalidation_check():
    """证伪监控：检查 complete 层股票是否跌破生死线"""
    global invalidation_alerts
    invalidation_alerts = []

    df = get_screen_result()
    if df.empty:
        logger.info("无选股结果，跳过证伪监控")
        return

    run_id = get_latest_run_id() or ""

    # 只检查 complete 层
    if "tier" in df.columns:
        complete_df = df[df["tier"] == "complete"]
    else:
        complete_df = df

    logger.info(f"证伪监控: 检查 {len(complete_df)} 只 complete 层股票")

    for _, row in complete_df.iterrows():
        code = str(row["code"]).zfill(6)
        name = row.get("name", code)
        try:
            detail = analyze_stock(code)
            if "error" in detail:
                continue

            inv = detail.get("invalidation", {})
            if inv.get("invalidated", False):
                alert = {
                    "code": code,
                    "name": name,
                    "current_close": inv.get("current_close"),
                    "invalidate_price": inv.get("invalidate_price"),
                    "critical_line": inv.get("critical_line"),
                    "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                invalidation_alerts.append(alert)
                # 持久化
                persistence.mark_invalidated(run_id, code)
                persistence.save_invalidation_log(
                    run_id, code, name,
                    inv.get("current_close", 0),
                    inv.get("invalidate_price", 0),
                    inv.get("critical_line", 0),
                )
                logger.warning(f"证伪触发: {code} {name} 收盘价 {inv.get('current_close')} 跌破生死线 {inv.get('invalidate_price')}")
        except Exception as e:
            logger.error(f"证伪检查失败 {code}: {e}")

    # 发送 Webhook
    if invalidation_alerts:
        _send_webhook(invalidation_alerts)

    logger.info(f"证伪监控完成: {len(invalidation_alerts)} 只触发证伪")


def run_portfolio_monitor():
    """交易时段监控：检查待买买入信号和持仓止损/止盈信号"""
    try:
        before_count = get_unread_count()
        result = run_portfolio_check()
        after_count = get_unread_count()
        new_alerts = after_count - before_count

        if new_alerts > 0:
            logger.info(f"持仓监控: 新增 {new_alerts} 条告警 (买入{result.get('buy_alert_count',0)} 卖出{result.get('sell_alert_count',0)})")
            # 推送 Webhook
            from persistence import list_alerts
            alerts = list_alerts(unread_only=True, limit=new_alerts)
            if alerts:
                _send_webhook(alerts, alert_type="portfolio")
        else:
            logger.info(f"持仓监控: 无新告警 (待买{len(result.get('watch_buy',[]))} 持仓{len(result.get('positions',[]))})")
    except Exception as e:
        logger.error(f"持仓监控失败: {e}")


def is_trading_time() -> bool:
    """判断当前是否为 A 股交易时段"""
    now = datetime.now()
    # 周末不交易
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    # 9:30-11:30, 13:00-15:00
    return (570 <= t <= 690) or (780 <= t <= 900)


def scheduled_job():
    """收盘后定时任务：同步 → 选股 → 证伪监控"""
    logger.info("=== 定时任务开始 ===")

    # 1. 触发同步
    if not trigger_sync():
        logger.error("同步触发失败，任务终止")
        return

    # 2. 等待同步完成
    if not wait_for_sync(timeout=600):
        logger.warning("同步未完成，继续执行选股（可能数据不完整）")

    # 3. 执行选股
    try:
        result = run_screener()
        logger.info(f"选股完成: 入池 {result.get('pool_count', 0)} 只")
    except Exception as e:
        logger.error(f"选股失败: {e}")
        return

    # 4. 证伪监控
    try:
        run_invalidation_check()
    except Exception as e:
        logger.error(f"证伪监控失败: {e}")

    # 5. 持仓/待买监控
    try:
        run_portfolio_monitor()
    except Exception as e:
        logger.error(f"持仓监控失败: {e}")

    logger.info("=== 定时任务完成 ===")


def start_scheduler():
    """启动定时任务调度器（后台线程）"""
    import schedule

    # 每个交易日 15:30 执行（周一到周五）
    schedule.every().monday.at("15:30").do(scheduled_job)
    schedule.every().tuesday.at("15:30").do(scheduled_job)
    schedule.every().wednesday.at("15:30").do(scheduled_job)
    schedule.every().thursday.at("15:30").do(scheduled_job)
    schedule.every().friday.at("15:30").do(scheduled_job)

    # 交易时段每5分钟检查持仓/待买
    schedule.every(5).minutes.do(_trading_time_check)

    def run_thread():
        while True:
            schedule.run_pending()
            time.sleep(30)

    thread = threading.Thread(target=run_thread, daemon=True)
    thread.start()
    logger.info("定时任务调度器已启动（交易日 15:30 同步+选股+证伪，交易时段每5分钟持仓监控）")


def _trading_time_check():
    """交易时段检查：仅在交易时段执行持仓监控"""
    if is_trading_time():
        run_portfolio_monitor()


def get_invalidation_alerts():
    """获取证伪告警列表"""
    return invalidation_alerts
