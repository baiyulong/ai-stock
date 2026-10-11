"""基本面评分：从东方财富获取财务指标并计算评分"""
import requests
import time
from typing import Optional
from persistence import get_conn

# 内存缓存
_fund_cache: dict[str, dict] = {}


def _get_secid(code: str) -> str:
    """转换为东方财富secid"""
    if code.startswith(('6', '9')):
        return f"1.{code}"
    return f"0.{code}"


def _get_secucode(code: str) -> str:
    """转换为东方财富SECUCODE格式"""
    if code.startswith(('6', '9')):
        return f"{code}.SH"
    return f"{code}.SZ"


def fetch_quote_metrics(code: str) -> dict:
    """从行情接口获取 PE、PB、ROE 等估值指标（push2接口当前不可用，返回空）"""
    # TODO: push2.eastmoney.com 被封，后续换备用源
    return {}


def fetch_finance_metrics(code: str) -> dict:
    """从财务接口获取营收增速、净利润增速、资产负债率"""
    secucode = _get_secucode(code)
    url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get?"
        "reportName=RPT_F10_FINANCE_MAINFINADATA&columns=SECUCODE,REPORT_DATE,"
        "ROEJQ,TOTALOPERATEREVETZ,PARENTNETPROFITTZ,ZCFZL,XSMLL,ZZCJLL,EPSJB,BPS&"
        f"filter=(SECUCODE=\"{secucode}\")"
        "&pageNumber=1&pageSize=4&sortTypes=-1&sortColumns=REPORT_DATE"
    )
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://data.eastmoney.com/',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        result = resp.json().get("result")
        if not result or not result.get("data"):
            return {}
        rows = result["data"]
        latest = rows[0]
        # 取最近4期ROE计算趋势
        roes = [r.get("ROEJQ") for r in rows if r.get("ROEJQ") is not None]
        return {
            "roe_weighted": latest.get("ROEJQ"),                # 加权ROE %
            "rev_growth": latest.get("TOTALOPERATEREVETZ"),     # 营收同比增速 %
            "profit_growth": latest.get("PARENTNETPROFITTZ"),   # 净利润同比增速 %
            "debt_ratio": latest.get("ZCFZL"),                  # 资产负债率 %
            "gross_margin": latest.get("XSMLL"),                # 销售毛利率 %
            "roa": latest.get("ZZCJLL"),                        # 总资产净利率 %
            "eps": latest.get("EPSJB"),                         # 基本每股收益
            "bps": latest.get("BPS"),                           # 每股净资产
            "roe_trend": roes,                                  # 最近4期ROE
        }
    except Exception as e:
        print(f"获取财务指标失败 {code}: {e}")
        return {}


def calc_fundamental_score(metrics: dict) -> dict:
    """计算基本面评分（满分100）

    评分维度：
    - ROE质量（25分）：ROE > 15% 满分，< 5% 0分
    - 成长性（25分）：营收增速 + 净利润增速
    - 盈利稳定性（20分）：最近4期ROE趋势，稳定或上升得高分
    - 财务安全（15分）：资产负债率
    - 盈利质量（15分）：毛利率 + ROA

    Returns:
        {score, grade, details}
    """
    score = 0
    details = {}

    # 1. ROE质量（25分）
    roe = metrics.get("roe") or metrics.get("roe_weighted")
    if roe is not None:
        if roe >= 20:
            roe_score = 25
        elif roe >= 15:
            roe_score = 20
        elif roe >= 10:
            roe_score = 15
        elif roe >= 5:
            roe_score = 8
        else:
            roe_score = 0
        score += roe_score
        details["roe"] = round(roe, 2)
        details["roe_score"] = roe_score
    else:
        details["roe"] = None
        details["roe_score"] = 0

    # 2. 成长性（25分）
    rev_g = metrics.get("rev_growth")
    profit_g = metrics.get("profit_growth")
    growth_score = 0
    if rev_g is not None:
        if rev_g >= 30:
            growth_score += 13
        elif rev_g >= 20:
            growth_score += 10
        elif rev_g >= 10:
            growth_score += 7
        elif rev_g >= 0:
            growth_score += 3
        details["rev_growth"] = round(rev_g, 2)
    else:
        details["rev_growth"] = None
    if profit_g is not None:
        if profit_g >= 30:
            growth_score += 12
        elif profit_g >= 20:
            growth_score += 9
        elif profit_g >= 10:
            growth_score += 6
        elif profit_g >= 0:
            growth_score += 3
        details["profit_growth"] = round(profit_g, 2)
    else:
        details["profit_growth"] = None
    score += growth_score
    details["growth_score"] = growth_score

    # 3. 盈利稳定性（20分）：最近4期ROE趋势
    roe_trend = metrics.get("roe_trend") or []
    stability_score = 0
    if len(roe_trend) >= 2:
        # 最新一期 vs 最早一期
        roe_change = roe_trend[0] - roe_trend[-1]
        if roe_change > 3:
            stability_score = 20  # ROE显著上升
        elif roe_change > 0:
            stability_score = 16  # 小幅上升
        elif roe_change > -2:
            stability_score = 12  # 基本稳定
        elif roe_change > -5:
            stability_score = 6   # 小幅下滑
        else:
            stability_score = 0   # 大幅下滑
        # 波动率惩罚
        if len(roe_trend) >= 3:
            avg_roe = sum(roe_trend) / len(roe_trend)
            variance = sum((r - avg_roe) ** 2 for r in roe_trend) / len(roe_trend)
            if variance > 25:
                stability_score = max(0, stability_score - 5)
        details["roe_trend"] = [round(r, 2) for r in roe_trend]
    else:
        details["roe_trend"] = None
    score += stability_score
    details["stability_score"] = stability_score

    # 4. 财务安全（15分）：资产负债率越低越安全
    debt = metrics.get("debt_ratio")
    if debt is not None:
        if debt <= 30:
            debt_score = 15
        elif debt <= 50:
            debt_score = 12
        elif debt <= 65:
            debt_score = 8
        elif debt <= 80:
            debt_score = 4
        else:
            debt_score = 0
        details["debt_ratio"] = round(debt, 2)
    else:
        debt_score = 0
        details["debt_ratio"] = None
    score += debt_score
    details["debt_score"] = debt_score

    # 5. 盈利质量（15分）：毛利率 + ROA
    quality_score = 0
    gm = metrics.get("gross_margin")
    if gm is not None:
        if gm >= 50:
            quality_score += 8
        elif gm >= 30:
            quality_score += 6
        elif gm >= 15:
            quality_score += 4
        else:
            quality_score += 2
        details["gross_margin"] = round(gm, 2)
    else:
        details["gross_margin"] = None
    roa = metrics.get("roa")
    if roa is not None:
        if roa >= 10:
            quality_score += 7
        elif roa >= 5:
            quality_score += 5
        elif roa >= 2:
            quality_score += 3
        else:
            quality_score += 1
        details["roa"] = round(roa, 2)
    else:
        details["roa"] = None
    score += quality_score
    details["quality_score"] = quality_score

    # 评级
    if score >= 80:
        grade = "excellent"  # 优秀
    elif score >= 60:
        grade = "good"       # 良好
    elif score >= 40:
        grade = "fair"       # 一般
    else:
        grade = "poor"       # 较差

    return {
        "score": score,
        "grade": grade,
        "details": details,
    }


def get_fundamental(code: str, use_cache: bool = True) -> Optional[dict]:
    """获取单只股票的基本面评分

    优先级：内存缓存 → 数据库缓存 → API获取

    Args:
        code: 股票代码
        use_cache: 是否使用缓存

    Returns:
        {score, grade, pe_ttm, pb, roe, rev_growth, profit_growth, debt_ratio, ...}
    """
    # 1. 内存缓存
    if use_cache and code in _fund_cache:
        return _fund_cache[code]

    # 2. 数据库缓存
    if use_cache:
        try:
            db_data = load_fundamentals_from_db()
            if code in db_data:
                _fund_cache[code] = db_data[code]
                return db_data[code]
        except Exception:
            pass

    # 3. 从API获取
    metrics = {}
    metrics.update(fetch_quote_metrics(code))
    time.sleep(0.05)  # 避免限流
    metrics.update(fetch_finance_metrics(code))

    if not metrics:
        return None

    result = calc_fundamental_score(metrics)
    result.update({
        "pe_ttm": metrics.get("pe_ttm"),
        "pb": metrics.get("pb"),
        "total_mv": metrics.get("total_mv"),
    })

    # 4. 保存到内存和数据库
    _fund_cache[code] = result
    try:
        save_fundamentals_to_db({code: result})
    except Exception as e:
        print(f"保存基本面数据失败 {code}: {e}")

    return result


def get_fundamentals_batch(codes: list[str], delay: float = 0.05) -> dict[str, dict]:
    """批量获取基本面评分（优先从数据库加载，缺失的从API获取）"""
    result = {}

    # 1. 先从数据库批量加载所有已缓存的
    try:
        db_data = load_fundamentals_from_db()
        for code in codes:
            if code in db_data:
                result[code] = db_data[code]
                _fund_cache[code] = db_data[code]
    except Exception:
        pass

    # 2. 缺失的从API获取
    missing = [code for code in codes if code not in result]
    if missing:
        print(f"从API获取 {len(missing)} 只股票的基本面数据...")
        new_data = {}
        for code in missing:
            try:
                fund = get_fundamental(code, use_cache=False)  # 跳过缓存，直接从API
                if fund:
                    result[code] = fund
                    new_data[code] = fund
            except Exception as e:
                print(f"获取 {code} 基本面失败: {e}")
            time.sleep(delay)
        # 批量保存新获取的数据
        if new_data:
            try:
                save_fundamentals_to_db(new_data)
            except Exception as e:
                print(f"批量保存基本面数据失败: {e}")

    return result


def load_fundamentals_from_db() -> dict[str, dict]:
    """从SQLite加载已缓存的基本面数据（含完整评分详情）"""
    import json
    conn = get_conn()
    cursor = conn.cursor()
    try:
        # 尝试查询 details 字段（旧表可能没有）
        try:
            cursor.execute("""
                SELECT code, score, grade, pe_ttm, pb, roe, rev_growth, profit_growth, debt_ratio, gross_margin, details
                FROM stock_fundamental
            """)
            has_details = True
        except Exception:
            cursor.execute("""
                SELECT code, score, grade, pe_ttm, pb, roe, rev_growth, profit_growth, debt_ratio, gross_margin
                FROM stock_fundamental
            """)
            has_details = False

        rows = cursor.fetchall()
        result = {}
        for row in rows:
            item = {
                "score": row[1],
                "grade": row[2],
                "pe_ttm": row[3],
                "pb": row[4],
                "roe": row[5],
                "rev_growth": row[6],
                "profit_growth": row[7],
                "debt_ratio": row[8],
                "gross_margin": row[9],
            }
            # 解析 details JSON
            if has_details and row[10]:
                try:
                    item["details"] = json.loads(row[10])
                except Exception:
                    item["details"] = {}
            else:
                # 旧数据，从字段重建 details
                item["details"] = {
                    "roe": row[5],
                    "rev_growth": row[6],
                    "profit_growth": row[7],
                    "debt_ratio": row[8],
                    "gross_margin": row[9],
                }
            result[row[0]] = item
        return result
    except Exception:
        return {}
    finally:
        conn.close()


def save_fundamentals_to_db(fundamentals: dict[str, dict]):
    """保存基本面数据到SQLite（含完整评分详情JSON）"""
    import json
    conn = get_conn()
    cursor = conn.cursor()
    # 建表（含 details 字段）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_fundamental (
            code TEXT PRIMARY KEY,
            score INTEGER,
            grade TEXT,
            pe_ttm REAL,
            pb REAL,
            roe REAL,
            rev_growth REAL,
            profit_growth REAL,
            debt_ratio REAL,
            gross_margin REAL,
            details TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # 旧表升级：增加 details 字段
    try:
        cursor.execute("ALTER TABLE stock_fundamental ADD COLUMN details TEXT")
    except Exception:
        pass  # 字段已存在

    for code, fund in fundamentals.items():
        details = fund.get("details", {})
        cursor.execute("""
            INSERT OR REPLACE INTO stock_fundamental
            (code, score, grade, pe_ttm, pb, roe, rev_growth, profit_growth, debt_ratio, gross_margin, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code,
            fund.get("score"),
            fund.get("grade"),
            fund.get("pe_ttm"),
            fund.get("pb"),
            details.get("roe"),
            details.get("rev_growth"),
            details.get("profit_growth"),
            details.get("debt_ratio"),
            details.get("gross_margin"),
            json.dumps(details, ensure_ascii=False),
        ))
    conn.commit()
    conn.close()
