"""股票行业信息获取：从东方财富公开API获取"""
import requests
import time
from typing import Optional
from persistence import get_db, get_config, set_config

# 行业信息缓存（内存）
_industry_cache: dict[str, str] = {}


def _get_secid(code: str) -> str:
    """转换股票代码为东方财富secid格式"""
    if code.startswith(('6', '9')):
        return f"1.{code}"  # 沪市
    else:
        return f"0.{code}"  # 深市


def fetch_industry(code: str) -> Optional[str]:
    """从东方财富获取单只股票的所属行业

    Args:
        code: 纯数字股票代码，如 600000

    Returns:
        行业名称，失败返回None
    """
    if code in _industry_cache:
        return _industry_cache[code]

    secid = _get_secid(code)
    url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f127,f128"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("data"):
            industry = data["data"].get("f127") or ""
            _industry_cache[code] = industry
            return industry if industry else None
    except Exception as e:
        print(f"获取行业信息失败 {code}: {e}")
    return None


def fetch_industries_batch(codes: list[str], delay: float = 0.1) -> dict[str, str]:
    """批量获取股票行业信息

    Args:
        codes: 股票代码列表
        delay: 请求间隔（秒），避免被限流

    Returns:
        {code: industry} 字典
    """
    result = {}
    for code in codes:
        industry = fetch_industry(code)
        if industry:
            result[code] = industry
        time.sleep(delay)
    return result


def load_industries_from_db() -> dict[str, str]:
    """从SQLite加载已缓存的行业信息"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT code, industry FROM stock_industry")
    rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}


def save_industries_to_db(industries: dict[str, str]):
    """保存行业信息到SQLite"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_industry (
            code TEXT PRIMARY KEY,
            industry TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    for code, industry in industries.items():
        cursor.execute("""
            INSERT OR REPLACE INTO stock_industry (code, industry)
            VALUES (?, ?)
        """, (code, industry))
    db.commit()


def get_industries(codes: list[str]) -> dict[str, str]:
    """获取股票行业信息（优先从缓存/数据库，缺失时从API获取）

    Args:
        codes: 股票代码列表

    Returns:
        {code: industry} 字典
    """
    # 先从内存缓存
    result = {code: _industry_cache[code] for code in codes if code in _industry_cache}

    # 再从数据库
    try:
        db_industries = load_industries_from_db()
        for code in codes:
            if code not in result and code in db_industries:
                result[code] = db_industries[code]
                _industry_cache[code] = db_industries[code]
    except Exception:
        pass

    # 缺失的从API获取
    missing = [code for code in codes if code not in result]
    if missing:
        print(f"从API获取 {len(missing)} 只股票的行业信息...")
        api_industries = fetch_industries_batch(missing)
        result.update(api_industries)
        _industry_cache.update(api_industries)
        if api_industries:
            try:
                save_industries_to_db(api_industries)
            except Exception:
                pass

    return result
