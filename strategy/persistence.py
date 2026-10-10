"""选股结果持久化（SQLite，独立文件，避免与 Go 的 DuckDB 锁冲突）"""
import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener_results.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screen_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                run_at TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                tier TEXT,
                low_raise_pct REAL,
                rebound_pct REAL,
                room_pct REAL,
                last_close REAL,
                low_60 REAL,
                low_prev40 REAL,
                high_100 REAL,
                low_100 REAL,
                avg_amount_10 REAL,
                avg_amount_100 REAL,
                invalidated INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_id ON screen_result(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_code ON screen_result(code)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invalidation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                code TEXT NOT NULL,
                name TEXT,
                current_close REAL,
                invalidate_price REAL,
                critical_line REAL,
                checked_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_ignore (
                code TEXT PRIMARY KEY,
                name TEXT,
                added_at TEXT NOT NULL,
                reason TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                tier TEXT,
                urgency INTEGER,
                current_price REAL,
                buy_price REAL,
                stop_loss1 REAL,
                stop_loss2 REAL,
                target_price REAL,
                rr REAL,
                can_open INTEGER,
                zone TEXT,
                action TEXT,
                signals TEXT,
                shares INTEGER,
                position_pct REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_monitor_run_at ON monitor_result(run_at)")
        # 兼容旧表：添加 low_60_date 列
        try:
            conn.execute("ALTER TABLE monitor_result ADD COLUMN low_60_date TEXT DEFAULT ''")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_buy (
                code TEXT PRIMARY KEY,
                name TEXT,
                target_buy_price REAL,
                notes TEXT DEFAULT '',
                added_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS position (
                code TEXT PRIMARY KEY,
                name TEXT,
                buy_price REAL NOT NULL,
                shares INTEGER NOT NULL,
                buy_date TEXT,
                notes TEXT DEFAULT '',
                added_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                title TEXT,
                message TEXT,
                current_price REAL,
                trigger_price REAL,
                created_at TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_created ON alert(created_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def save_run_results(run_id: str, run_at: str, df: pd.DataFrame):
    """保存一次选股运行的全部结果"""
    conn = get_conn()
    try:
        # 删除同 run_id 的旧数据
        conn.execute("DELETE FROM screen_result WHERE run_id = ?", (run_id,))

        rows = []
        for _, r in df.iterrows():
            rows.append((
                run_id, run_at,
                str(r.get("code", "")),
                r.get("name"),
                r.get("tier"),
                r.get("low_raise_pct"),
                r.get("rebound_pct"),
                r.get("room_pct"),
                r.get("last_close"),
                r.get("low_60"),
                r.get("low_prev40"),
                r.get("high_100"),
                r.get("low_100"),
                r.get("avg_amount_10"),
                r.get("avg_amount_100"),
                0,
            ))

        conn.executemany("""
            INSERT INTO screen_result
            (run_id, run_at, code, name, tier, low_raise_pct, rebound_pct, room_pct,
             last_close, low_60, low_prev40, high_100, low_100, avg_amount_10, avg_amount_100, invalidated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
    finally:
        conn.close()


def load_run_results(run_id: Optional[str] = None) -> pd.DataFrame:
    """加载选股结果（默认最近一次）"""
    conn = get_conn()
    try:
        if run_id:
            df = pd.read_sql_query(
                "SELECT * FROM screen_result WHERE run_id = ? ORDER BY id ASC",
                conn, params=(run_id,)
            )
        else:
            # 取最近一次 run_id
            row = conn.execute(
                "SELECT run_id FROM screen_result ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return pd.DataFrame()
            df = pd.read_sql_query(
                "SELECT * FROM screen_result WHERE run_id = ? ORDER BY id ASC",
                conn, params=(row["run_id"],)
            )
        return df
    finally:
        conn.close()


def list_runs(limit: int = 20) -> list:
    """列出历史运行记录"""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT run_id, run_at,
                   COUNT(*) as count,
                   SUM(CASE WHEN tier='complete' THEN 1 ELSE 0 END) as complete_count,
                   SUM(CASE WHEN tier='partial' THEN 1 ELSE 0 END) as partial_count,
                   SUM(CASE WHEN invalidated=1 THEN 1 ELSE 0 END) as invalidated_count
            FROM screen_result
            GROUP BY run_id, run_at
            ORDER BY run_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_run_id() -> Optional[str]:
    """获取最近一次运行ID"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_id FROM screen_result ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["run_id"] if row else None
    finally:
        conn.close()


def mark_invalidated(run_id: str, code: str):
    """标记某只股票为已证伪"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE screen_result SET invalidated = 1 WHERE run_id = ? AND code = ?",
            (run_id, code)
        )
        conn.commit()
    finally:
        conn.close()


def save_invalidation_log(run_id: str, code: str, name: str,
                          current_close: float, invalidate_price: float, critical_line: float):
    """保存证伪日志"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO invalidation_log
            (run_id, code, name, current_close, invalidate_price, critical_line, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (run_id, code, name, current_close, invalidate_price, critical_line,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def get_invalidation_history(days: int = 7) -> list:
    """获取最近 N 天的证伪历史"""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM invalidation_log
            WHERE checked_at >= datetime('now', ?)
            ORDER BY checked_at DESC
        """, (f"-{days} days",)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ========== 监控忽略名单 ==========

def add_monitor_ignore(code: str, name: str = "", reason: str = ""):
    """添加股票到监控忽略名单"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO monitor_ignore (code, name, added_at, reason)
            VALUES (?, ?, ?, ?)
        """, (code, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason))
        conn.commit()
    finally:
        conn.close()


def remove_monitor_ignore(code: str):
    """从监控忽略名单中移除股票"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM monitor_ignore WHERE code = ?", (code,))
        conn.commit()
    finally:
        conn.close()


def list_monitor_ignore() -> list:
    """列出所有监控忽略名单中的股票"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM monitor_ignore ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_monitor_ignored(code: str) -> bool:
    """检查股票是否在监控忽略名单中"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM monitor_ignore WHERE code = ?", (code,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_monitor_ignore_codes() -> set:
    """获取忽略名单中的股票代码集合（用于批量过滤）"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT code FROM monitor_ignore").fetchall()
        return {r["code"] for r in rows}
    finally:
        conn.close()


# ========== 监控结果持久化 ==========

def save_monitor_results(results: list):
    """保存一次监控的全部结果"""
    if not results:
        return
    conn = get_conn()
    try:
        run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 清空旧数据（只保留最新一次）
        conn.execute("DELETE FROM monitor_result")
        rows = []
        for r in results:
            rows.append((
                run_at,
                str(r.get("code", "")),
                r.get("name", ""),
                r.get("tier", ""),
                int(r.get("urgency", 0)),
                r.get("current_price", 0),
                r.get("B", 0),
                r.get("L1", 0),
                r.get("L2", 0),
                r.get("T", 0),
                r.get("RR", 0),
                1 if r.get("can_open") else 0,
                r.get("zone", ""),
                r.get("action", ""),
                ",".join(r.get("signals", [])),
                int(r.get("shares", 0)),
                r.get("position_pct", 0),
                r.get("low_60_date", ""),
            ))
        conn.executemany("""
            INSERT INTO monitor_result
            (run_at, code, name, tier, urgency, current_price, buy_price, stop_loss1,
             stop_loss2, target_price, rr, can_open, zone, action, signals, shares, position_pct, low_60_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
    finally:
        conn.close()


def load_monitor_results() -> tuple:
    """加载最近一次监控结果

    Returns:
        (results_list, run_at_str)  无数据时返回 ([], "")
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_at FROM monitor_result ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return [], ""
        run_at = row["run_at"]
        rows = conn.execute(
            "SELECT * FROM monitor_result WHERE run_at = ? ORDER BY urgency DESC, id ASC",
            (run_at,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            results.append({
                "code": d["code"],
                "name": d["name"],
                "tier": d["tier"],
                "urgency": d["urgency"],
                "current_price": d["current_price"],
                "B": d["buy_price"],
                "L1": d["stop_loss1"],
                "L2": d["stop_loss2"],
                "T": d["target_price"],
                "RR": d["rr"],
                "can_open": bool(d["can_open"]),
                "zone": d["zone"],
                "action": d["action"],
                "signals": [s for s in (d["signals"] or "").split(",") if s],
                "shares": d["shares"],
                "position_pct": d["position_pct"],
                "low_60_date": d.get("low_60_date", ""),
            })
        return results, run_at
    finally:
        conn.close()


# ========== 待买列表 ==========

def add_watch_buy(code: str, name: str = "", target_buy_price: float = 0, notes: str = ""):
    """添加待买股票"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO watch_buy (code, name, target_buy_price, notes, added_at)
            VALUES (?, ?, ?, ?, ?)
        """, (code, name, target_buy_price, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def remove_watch_buy(code: str):
    """移除待买股票"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM watch_buy WHERE code = ?", (code,))
        conn.commit()
    finally:
        conn.close()


def list_watch_buy() -> list:
    """列出待买股票"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM watch_buy ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ========== 持仓列表 ==========

def add_position(code: str, name: str, buy_price: float, shares: int,
                 buy_date: str = "", notes: str = ""):
    """添加持仓股票"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO position (code, name, buy_price, shares, buy_date, notes, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (code, name, buy_price, shares, buy_date or datetime.now().strftime("%Y-%m-%d"),
              notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def remove_position(code: str):
    """移除持仓股票"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM position WHERE code = ?", (code,))
        conn.commit()
    finally:
        conn.close()


def list_positions() -> list:
    """列出持仓股票"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM position ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ========== 告警 ==========

def add_alert(alert_type: str, code: str, name: str, title: str, message: str,
              current_price: float = 0, trigger_price: float = 0):
    """添加告警"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO alert (alert_type, code, name, title, message, current_price, trigger_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_type, code, name, title, message, current_price, trigger_price,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def list_alerts(unread_only: bool = False, limit: int = 50) -> list:
    """列出告警"""
    conn = get_conn()
    try:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM alert WHERE is_read = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alert ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_alert_read(alert_id: int):
    """标记告警为已读"""
    conn = get_conn()
    try:
        conn.execute("UPDATE alert SET is_read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()


def mark_all_alerts_read():
    """标记所有告警为已读"""
    conn = get_conn()
    try:
        conn.execute("UPDATE alert SET is_read = 1 WHERE is_read = 0")
        conn.commit()
    finally:
        conn.close()


def get_unread_alert_count() -> int:
    """获取未读告警数量"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM alert WHERE is_read = 0").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# ========== 应用配置 ==========

def get_config(key: str, default: str = "") -> str:
    """获取配置项"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_config(key: str, value: str):
    """设置配置项"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO app_config (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def get_all_config() -> dict:
    """获取所有配置"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM app_config").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


# 初始化
init_db()
