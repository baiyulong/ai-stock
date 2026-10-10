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
    // Vela 用 UTC 格式化显示时间，需加上本地时区偏移，使显示为本地时间
    const tzOffset = new Date().getTimezoneOffset() * 60 * 1000; // 本地时区偏移（毫秒）
    return json.data.List
      .map((k) => {
        // 后端返回 ISO 格式 "2026-09-28T15:00:00+08:00"，自带时区，直接解析
        const time = new Date(k.Time).getTime();
        return {
          time: isNaN(time) ? Date.now() : time - tzOffset,
          open: k.Open / 1000,
          high: k.High / 1000,
          low: k.Low / 1000,
          close: k.Close / 1000,
          volume: k.Volume || 0,
        };
      })
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
