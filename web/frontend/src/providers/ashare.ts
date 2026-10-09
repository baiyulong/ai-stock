import type { DataProvider, OHLCV, BarRange, SymbolInfo } from '@luxalgo/vela';
import { TF_MAP, isIndexCode } from '@/constants';

interface TdxKline {
  Time: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
  Amount: number;
  Last: number;
}

interface TdxResponse {
  code: number;
  message: string;
  data: {
    Count: number;
    List: TdxKline[];
  };
}

/**
 * AShareProvider - 对接 tdx-api
 * 指数走 /api/index，个股/ETF 走 /api/kline-history
 * 价格单位：厘 -> 元（÷1000）
 */
export class AShareProvider implements DataProvider {
  readonly baseUrl: string;

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
  }

  async getBars(ticker: string, timeframe: string, range: BarRange): Promise<OHLCV[]> {
    const tdxType = TF_MAP[timeframe] ?? 'day';
    const limit = range.limit ?? 500;
    const isIndex = isIndexCode(ticker);

    // 指数走 /api/index，个股走 /api/kline-history（前复权）
    const apiPath = isIndex ? '/api/index' : '/api/kline-history';
    const url = `${this.baseUrl}${apiPath}?code=${encodeURIComponent(ticker)}&type=${tdxType}&limit=${limit}`;

    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error(`tdx-api HTTP ${resp.status}`);
    }

    const json: TdxResponse = await resp.json();
    if (json.code !== 0 || !json.data?.List) return [];

    // tdx 倒序 -> Vela 正序，价格厘 -> 元
    return json.data.List
      .map((k) => ({
        time: Date.parse(k.Time),
        open: k.Open / 1000,
        high: k.High / 1000,
        low: k.Low / 1000,
        close: k.Close / 1000,
        volume: k.Volume || 0,
      }))
      .reverse()
      .sort((a, b) => a.time - b.time);
  }

  async getSymbolInfo?(ticker: string): Promise<SymbolInfo | undefined> {
    return {
      ticker,
      description: ticker,
      type: isIndexCode(ticker) ? 'index' : 'stock',
      exchange: 'SSE/SZSE',
    };
  }

  info() {
    return {
      name: 'ashare',
      displayName: 'A股 (tdx-api)',
      requiresApiKey: false,
      supportedTimeframes: ['1', '5', '15', '30', '60', 'D', 'W', 'M'],
      capabilities: {
        enumerate: false,
        stream: false,
        symbolInfo: true,
      },
    };
  }
}
