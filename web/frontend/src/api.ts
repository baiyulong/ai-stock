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
