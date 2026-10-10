import { isIndexCode, isETFCode, INDEX_LIST, type SearchResult, type QuoteData } from '@/constants';
export type { SearchResult, QuoteData };

// 搜索股票/指数/ETF
export async function searchStocks(keyword: string): Promise<SearchResult[]> {
  const kw = keyword.toUpperCase();

  // 1. 匹配本地指数
  const indexMatches: SearchResult[] = INDEX_LIST.filter(
    (idx) =>
      idx.name.includes(keyword) ||
      idx.code.toUpperCase().includes(kw) ||
      idx.code.replace(/^(sh|sz)/i, '').includes(keyword)
  ).map((idx) => ({ code: idx.code, name: idx.name, tag: '指数' }));

  // 2. 搜索个股/ETF
  let stockResults: SearchResult[] = [];
  try {
    const resp = await fetch(`/api/search?keyword=${encodeURIComponent(keyword)}`);
    const json = await resp.json();
    if (json.code === 0 && json.data?.length > 0) {
      stockResults = json.data.map((s: any) => ({
        code: s.code,
        name: s.name,
        type: s.type,
        tag: s.type === 'etf' ? 'ETF' : '',
      }));
    }
  } catch {
    /* ignore */
  }

  return [...indexMatches, ...stockResults].slice(0, 10);
}

// 获取个股/ETF 实时行情
export async function fetchStockQuote(code: string): Promise<QuoteData | null> {
  try {
    const resp = await fetch(`/api/quote?code=${encodeURIComponent(code)}`);
    const json = await resp.json();
    if (json.code !== 0 || !json.data?.[0]) return null;

    const q = json.data[0];
    const k = q.K || {};
    const isETF = isETFCode(code);
    const priceDiv = isETF ? 100 : 1000;
    const decimals = isETF ? 3 : 2;

    const last = k.Close / priceDiv;
    const prevClose = k.Last / priceDiv;
    const change = last - prevClose;

    return {
      code: q.Code || code,
      name: '',
      last,
      prevClose,
      change,
      changePct: prevClose ? (change / prevClose) * 100 : 0,
      up: change >= 0,
      open: k.Open / priceDiv,
      high: k.High / priceDiv,
      low: k.Low / priceDiv,
      volume: q.TotalHand || 0,
      amount: q.Amount || 0,
      insideDish: q.InsideDish || 0,
      outerDisc: q.OuterDisc || 0,
      decimals,
    };
  } catch {
    return null;
  }
}

// 获取指数行情（用最新2根日K线）
export async function fetchIndexQuote(code: string): Promise<QuoteData | null> {
  try {
    const resp = await fetch(`/api/index?code=${encodeURIComponent(code)}&type=day&limit=2`);
    const json = await resp.json();
    if (json.code !== 0 || !json.data?.List?.length) return null;

    const latest = json.data.List[0];
    const prev = json.data.List[1] || latest;
    const last = latest.Close / 1000;
    const prevClose = prev.Close / 1000;
    const change = last - prevClose;

    return {
      code,
      name: '',
      last,
      prevClose,
      change,
      changePct: prevClose ? (change / prevClose) * 100 : 0,
      up: change >= 0,
      open: latest.Open / 1000,
      high: latest.High / 1000,
      low: latest.Low / 1000,
      volume: latest.Volume || 0,
      amount: (latest.Amount || 0) / 1000,
      insideDish: 0,
      outerDisc: 0,
      decimals: 2,
    };
  } catch {
    return null;
  }
}

// 批量获取行情（自选列表用）
export async function fetchQuotes(codes: string[]): Promise<Map<string, QuoteData>> {
  const result = new Map<string, QuoteData>();
  const indexCodes = codes.filter(isIndexCode);
  const stockCodes = codes.filter((c) => !isIndexCode(c));

  // 个股/ETF 批量
  if (stockCodes.length > 0) {
    try {
      const resp = await fetch(`/api/quote?code=${encodeURIComponent(stockCodes.join(','))}`);
      const json = await resp.json();
      if (json.code === 0 && json.data) {
        for (const q of json.data) {
          const k = q.K || {};
          const isETF = isETFCode(q.Code);
          const priceDiv = isETF ? 100 : 1000;
          const last = k.Close / priceDiv;
          const prevClose = k.Last / priceDiv;
          const change = last - prevClose;
          result.set(q.Code, {
            code: q.Code,
            name: '',
            last,
            prevClose,
            change,
            changePct: prevClose ? (change / prevClose) * 100 : 0,
            up: change >= 0,
            open: k.Open / priceDiv,
            high: k.High / priceDiv,
            low: k.Low / priceDiv,
            volume: q.TotalHand || 0,
            amount: q.Amount || 0,
            insideDish: q.InsideDish || 0,
            outerDisc: q.OuterDisc || 0,
            decimals: isETF ? 3 : 2,
          });
        }
      }
    } catch {
      /* ignore */
    }
  }

  // 指数逐个获取
  for (const code of indexCodes) {
    const q = await fetchIndexQuote(code);
    if (q) result.set(code, q);
  }

  return result;
}

// 格式化成交量
export function formatVolume(v: number): string {
  if (!v) return '--';
  if (v >= 100000000) return (v / 100000000).toFixed(2) + '亿手';
  if (v >= 10000) return (v / 10000).toFixed(2) + '万手';
  return v + '手';
}

// 格式化成交额（元 -> 亿/万）
export function formatAmount(v: number): string {
  if (!v) return '--';
  if (v >= 100000000) return (v / 100000000).toFixed(2) + '亿';
  if (v >= 10000) return (v / 10000).toFixed(2) + '万';
  return v.toFixed(0);
}

// ===== 选股策略相关 =====

const STRATEGY_BASE = 'http://127.0.0.1:18081';

export interface ScreenerResult {
  code: string;
  name: string;
  tier: 'complete' | 'partial' | 'pool_only';
  low_raise_pct: number;
  rebound_pct: number;
  room_pct: number;
  last_close: number;
  low_60: number;
  low_prev40: number;
  low_60_date?: string;
  high_100: number;
  low_100: number;
  avg_amount_10: number;
  avg_amount_100: number;
}

export interface ScreenerRunResult {
  run_id: string;
  run_at: string;
  total_scanned: number;
  pool_count: number;
  tier_counts: Record<string, number>;
  results: ScreenerResult[];
}

export interface StockDetail {
  basic: {
    code: string;
    last_close: number;
    last_date: string;
    high_100: number;
    low_100: number;
    low_60: number;
    low_prev40: number;
    ma60: number;
  };
  pool_checks: {
    structure_double_window: boolean;
    new_high_confirm: boolean;
    amplitude: boolean;
    liquidity: boolean;
    all_pass: boolean;
  };
  tier_indicators: {
    low_raise_pct: number;
    rebound_pct: number;
    room_pct: number;
    avg_amount_10: number;
    rebound_pass: boolean;
    room_pass: boolean;
    volume_pass: boolean;
  };
  confirmations: {
    support: { pass: boolean; support_line: number; description: string };
    volume_breakout: { pass: boolean; breakout_date: string; volume_ratio: number; description: string };
    ma_turn: { pass: boolean; ma60_slope: number; description: string };
    all_pass: boolean;
  };
  invalidation: {
    invalidated: boolean;
    critical_line: number;
    invalidate_price: number;
    current_close: number;
    description: string;
  };
  klines: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    amount: number;
  }>;
}

// 执行选股
export async function runScreener(): Promise<ScreenerRunResult | null> {
  try {
    const resp = await fetch(`${STRATEGY_BASE}/api/screener/run`, { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// 获取选股结果
export async function getScreenerResults(runId?: string): Promise<ScreenerResult[]> {
  try {
    const url = runId
      ? `${STRATEGY_BASE}/api/screener/results?run_id=${runId}`
      : `${STRATEGY_BASE}/api/screener/results`;
    const resp = await fetch(url);
    const json = await resp.json();
    if (json.code === 0 && json.data?.results) return json.data.results;
    return [];
  } catch {
    return [];
  }
}

// 获取单票详细诊断
export async function getStockDetail(code: string): Promise<StockDetail | null> {
  try {
    const resp = await fetch(`${STRATEGY_BASE}/api/screener/stock/${code}`);
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// 触发数据同步（Go 服务）
export async function syncMarketData(codes?: string[]): Promise<boolean> {
  try {
    const body: any = { concurrency: 8, lookback: 140 };
    if (codes) body.codes = codes;
    const resp = await fetch('/api/screener/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

// 查询同步状态
export async function getSyncStatus(): Promise<{ status: string; total: number; done: number; failed: number } | null> {
  try {
    const resp = await fetch('/api/screener/sync-status');
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// 查询 DuckDB 统计
export async function getDBStats(): Promise<{ total_rows: number; total_codes: number } | null> {
  try {
    const resp = await fetch('/api/screener/db-stats');
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// ===== 交易监控相关 =====

export interface TradingAnchors {
  A: number;
  H: number;
  MA20: number;
  low_prev40: number;
  raise_line: number;
  current_price: number;
  current_date: string;
}

export interface TradingParams {
  B: number;
  L1: number;
  L2: number;
  T: number;
  RR: number;
  position_pct: number;
  position_value: number;
  shares: number;
  risk_amount: number;
  can_open: boolean;
  reason: string;
}

export interface PricePosition {
  zone: string;
  current_price: number;
  signals: string[];
  action: string;
}

export interface StockDetail {
  basic: {
    code: string;
    last_close: number;
    last_date: string;
    high_100: number;
    low_100: number;
    low_60: number;
    low_prev40: number;
    ma60: number;
  };
  pool_checks: {
    structure_double_window: boolean;
    new_high_confirm: boolean;
    amplitude: boolean;
    liquidity: boolean;
    all_pass: boolean;
  };
  tier_indicators: {
    low_raise_pct: number;
    rebound_pct: number;
    room_pct: number;
    avg_amount_10: number;
    rebound_pass: boolean;
    room_pass: boolean;
    volume_pass: boolean;
  };
  confirmations: {
    support: { pass: boolean; support_line: number; description: string };
    volume_breakout: { pass: boolean; breakout_date: string; volume_ratio: number; description: string };
    ma_turn: { pass: boolean; ma60_slope: number; description: string };
    all_pass: boolean;
  };
  invalidation: {
    invalidated: boolean;
    critical_line: number;
    invalidate_price: number;
    current_close: number;
    description: string;
  };
  trading?: {
    anchors: TradingAnchors;
    buy_info: { B: number; mode: string; description: string };
    params: TradingParams;
    position: PricePosition;
  };
  klines: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    amount: number;
  }>;
}

export interface MonitorItem {
  code: string;
  name: string;
  tier: string;
  urgency: number;
  current_price: number;
  B: number;
  L1: number;
  L2: number;
  T: number;
  RR: number;
  can_open: boolean;
  zone: string;
  action: string;
  signals: string[];
  shares: number;
  position_pct: number;
  low_60_date?: string;
}

// 执行实时监控
export async function runMonitor(capital?: number, riskBudget?: number): Promise<MonitorItem[]> {
  try {
    const params = new URLSearchParams();
    if (capital) params.set('capital', String(capital));
    if (riskBudget) params.set('risk_budget', String(riskBudget));
    const resp = await fetch(`/api/screener/monitor?${params.toString()}`, { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) return json.data.all || [];
    return [];
  } catch {
    return [];
  }
}

// 获取监控结果
export async function getMonitorResults(): Promise<{ time: string; count: number; alerts: MonitorItem[]; all: MonitorItem[] } | null> {
  try {
    const resp = await fetch('/api/screener/monitor');
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// ========== 监控忽略名单 ==========

export interface IgnoreItem {
  code: string;
  name: string;
  added_at: string;
  reason: string;
}

export async function listIgnore(): Promise<IgnoreItem[]> {
  try {
    const resp = await fetch('/api/screener/monitor/ignore');
    const json = await resp.json();
    if (json.code === 0) return json.data || [];
    return [];
  } catch {
    return [];
  }
}

export async function addIgnore(code: string, name?: string, reason?: string): Promise<boolean> {
  try {
    const resp = await fetch('/api/screener/monitor/ignore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, name: name || '', reason: reason || '' }),
    });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function removeIgnore(code: string): Promise<boolean> {
  try {
    const resp = await fetch(`/api/screener/monitor/ignore/${code}`, { method: 'DELETE' });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

// ========== 待买列表 ==========

export interface WatchBuyItem {
  code: string;
  name: string;
  target_buy_price: number;
  notes: string;
  added_at: string;
}

export interface WatchBuyCheckItem {
  code: string;
  name: string;
  current_price: number;
  B: number;
  L1: number;
  L2: number;
  T: number;
  RR: number;
  can_buy: boolean;
  distance_pct: number;
  signals: string[];
}

export async function listWatchBuy(): Promise<WatchBuyItem[]> {
  try {
    const resp = await fetch('/api/portfolio/watch-buy');
    const json = await resp.json();
    if (json.code === 0) return json.data || [];
    return [];
  } catch {
    return [];
  }
}

export async function addWatchBuy(code: string, name?: string, targetBuyPrice?: number, notes?: string): Promise<boolean> {
  try {
    const resp = await fetch('/api/portfolio/watch-buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, name: name || '', target_buy_price: targetBuyPrice || 0, notes: notes || '' }),
    });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function removeWatchBuy(code: string): Promise<boolean> {
  try {
    const resp = await fetch(`/api/portfolio/watch-buy/${code}`, { method: 'DELETE' });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function checkWatchBuy(): Promise<WatchBuyCheckItem[]> {
  try {
    const resp = await fetch('/api/portfolio/watch-buy/check', { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) return json.data || [];
    return [];
  } catch {
    return [];
  }
}

// ========== 持仓列表 ==========

export interface PositionItem {
  code: string;
  name: string;
  buy_price: number;
  shares: number;
  buy_date: string;
  notes: string;
  added_at: string;
}

export interface PositionCheckItem {
  code: string;
  name: string;
  buy_price: number;
  shares: number;
  current_price: number;
  profit_pct: number;
  market_value: number;
  L1: number;
  L2: number;
  T: number;
  signal_type: string;
  signal_level: number;
  has_signal: boolean;
}

export async function listPositions(): Promise<PositionItem[]> {
  try {
    const resp = await fetch('/api/portfolio/positions');
    const json = await resp.json();
    if (json.code === 0) return json.data || [];
    return [];
  } catch {
    return [];
  }
}

export async function addPosition(code: string, name: string, buyPrice: number, shares: number, buyDate?: string, notes?: string): Promise<boolean> {
  try {
    const resp = await fetch('/api/portfolio/positions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, name, buy_price: buyPrice, shares, buy_date: buyDate || '', notes: notes || '' }),
    });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function removePosition(code: string): Promise<boolean> {
  try {
    const resp = await fetch(`/api/portfolio/positions/${code}`, { method: 'DELETE' });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function checkPositions(): Promise<PositionCheckItem[]> {
  try {
    const resp = await fetch('/api/portfolio/positions/check', { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) return json.data || [];
    return [];
  } catch {
    return [];
  }
}

// ========== 告警 ==========

export interface AlertItem {
  id: number;
  alert_type: string;
  code: string;
  name: string;
  title: string;
  message: string;
  current_price: number;
  trigger_price: number;
  created_at: string;
  is_read: number;
}

export async function getAlerts(unreadOnly?: boolean, limit?: number): Promise<{ alerts: AlertItem[]; unread_count: number }> {
  try {
    const params = new URLSearchParams();
    if (unreadOnly) params.set('unread_only', 'true');
    if (limit) params.set('limit', String(limit));
    const resp = await fetch(`/api/portfolio/alerts?${params.toString()}`);
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return { alerts: [], unread_count: 0 };
  } catch {
    return { alerts: [], unread_count: 0 };
  }
}

export async function markAlertRead(alertId: number): Promise<boolean> {
  try {
    const resp = await fetch(`/api/portfolio/alerts/${alertId}/read`, { method: 'POST' });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function markAllAlertsRead(): Promise<boolean> {
  try {
    const resp = await fetch('/api/portfolio/alerts/read-all', { method: 'POST' });
    const json = await resp.json();
    return json.code === 0;
  } catch {
    return false;
  }
}

export async function runPortfolioCheck(): Promise<{ watch_buy: any[]; positions: any[]; total_alerts: number } | null> {
  try {
    const resp = await fetch('/api/portfolio/check', { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}

// 单票回测
export interface BacktestTrade {
  type: string;
  date: string;
  price: number;
  shares: number;
  amount: number;
  profit?: number;
  reason?: string;
  params?: any;
}

export interface BacktestResult {
  code: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_profit: number;
  avg_profit: number;
  max_profit: number;
  max_loss: number;
  structure_count: number;
  trades: BacktestTrade[];
  klines: any[];
  error?: string;
}

export async function runSingleBacktest(
  code: string,
  startDate?: string,
  endDate?: string,
  initialCapital = 100000,
  feeRate = 0.00025,
): Promise<BacktestResult | null> {
  try {
    const resp = await fetch(`/api/screener/backtest/${code}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_date: startDate || null,
        end_date: endDate || null,
        initial_capital: initialCapital,
        fee_rate: feeRate,
      }),
    });
    const json = await resp.json();
    if (json.code === 0) return json.data;
    return null;
  } catch {
    return null;
  }
}
