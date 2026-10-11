"""股票行业信息获取：从东方财富公开API获取"""
import requests
import time
import io
import pandas as pd
from typing import Optional
from persistence import get_conn

GO_SERVICE_URL = "http://127.0.0.1:18080"

# 行业信息缓存（内存）
_industry_cache: dict[str, str] = {}


def _get_em_code(code: str) -> str:
    """转换股票代码为东方财富F10接口格式（SH600519 / SZ000001）"""
    if code.startswith(('6', '9')):
        return f"SH{code}"
    return f"SZ{code}"


def fetch_industry(code: str) -> Optional[str]:
    """从东方财富F10接口获取单只股票的所属行业

    Args:
        code: 纯数字股票代码，如 600000

    Returns:
        行业名称（如"食品饮料-饮料-白酒"），失败返回None
    """
    if code in _industry_cache:
        return _industry_cache[code]

    em_code = _get_em_code(code)
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={em_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://emweb.securities.eastmoney.com/',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        # jbzl 字段包含基本信息，EM2016 是东方财富行业分类
        if data.get("jbzl") and data["jbzl"]:
            industry = data["jbzl"][0].get("EM2016") or ""
            if industry:
                _industry_cache[code] = industry
                return industry
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
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT code, industry FROM stock_industry")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception:
        return {}
    finally:
        conn.close()


def save_industries_to_db(industries: dict[str, str]):
    """保存行业信息到SQLite"""
    conn = get_conn()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()


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


def preload_all_industries(delay: float = 0.15) -> dict:
    """预加载所有股票的行业信息到数据库

    从 Go 后端获取所有股票代码，批量获取行业信息并保存到 SQLite。
    行业信息基本不变，预加载后选股时直接从数据库读取。

    Args:
        delay: 请求间隔（秒）

    Returns:
        {total, success, failed, cached} 统计信息
    """
    # 1. 从 Go 后端获取所有股票代码
    try:
        url = f"{GO_SERVICE_URL}/api/screener/stock-info"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), dtype={"code": str})
        if df.empty:
            return {"total": 0, "success": 0, "failed": 0, "cached": 0, "error": "无股票数据"}
        df["code"] = df["code"].str.zfill(6)
        # 只处理个股（排除ETF）
        stocks = df[~df["is_etf"].astype(bool)]["code"].tolist()
    except Exception as e:
        return {"total": 0, "success": 0, "failed": 0, "cached": 0, "error": str(e)}

    # 2. 从数据库加载已缓存的
    cached = load_industries_from_db()
    cached_count = len([c for c in stocks if c in cached])

    # 3. 缺失的从API获取
    missing = [c for c in stocks if c not in cached]
    print(f"预加载行业信息：共 {len(stocks)} 只，已缓存 {cached_count} 只，待获取 {len(missing)} 只")

    success = 0
    failed = 0
    new_industries = {}
    for i, code in enumerate(missing):
        try:
            industry = fetch_industry(code)
            if industry:
                new_industries[code] = industry
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1

        # 每100只保存一次，避免内存占用过大
        if (i + 1) % 100 == 0 and new_industries:
            save_industries_to_db(new_industries)
            print(f"  已处理 {i+1}/{len(missing)}，成功 {success}，失败 {failed}")
            new_industries = {}

        time.sleep(delay)

    # 保存剩余的
    if new_industries:
        save_industries_to_db(new_industries)

    # 更新内存缓存
    _industry_cache.update(cached)
    _industry_cache.update({c: new_industries.get(c, "") for c in missing if c in new_industries})

    return {
        "total": len(stocks),
        "cached": cached_count,
        "success": success,
        "failed": failed,
    }
