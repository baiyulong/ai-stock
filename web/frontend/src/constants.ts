// 周期映射：Vela -> tdx-api
export const TF_MAP: Record<string, string> = {
  '1': 'minute1',
  '5': 'minute5',
  '15': 'minute15',
  '30': 'minute30',
  '60': 'hour',
  'D': 'day',
  'W': 'week',
  'M': 'month',
};

// 常见大盘指数
export interface IndexItem {
  code: string;
  name: string;
  exchange: string;
}

export const INDEX_LIST: IndexItem[] = [
  { code: 'sh000001', name: '上证指数', exchange: 'sh' },
  { code: 'sz399001', name: '深证成指', exchange: 'sz' },
  { code: 'sz399006', name: '创业板指', exchange: 'sz' },
  { code: 'sh000300', name: '沪深300', exchange: 'sh' },
  { code: 'sh000016', name: '上证50', exchange: 'sh' },
  { code: 'sh000905', name: '中证500', exchange: 'sh' },
  { code: 'sh000688', name: '科创50', exchange: 'sh' },
  { code: 'sz399005', name: '中小板指', exchange: 'sz' },
];

// 判断是否为指数代码
export function isIndexCode(code: string): boolean {
  if (!code) return false;
  const c = code.toLowerCase();
  if (c.startsWith('sh') || c.startsWith('sz')) return true;
  if (/^399\d{3}$/.test(code)) return true;
  return false;
}

// 判断是否为 ETF 代码
export function isETFCode(code: string): boolean {
  return /^(51|56|58|15|16)\d{4}$/.test(code);
}

// 获取指数纯代码（去掉前缀）
export function getIndexPureCode(code: string): string {
  return code.replace(/^(sh|sz)/i, '');
}

// 默认自选股
export const DEFAULT_WATCHLIST = [
  { code: 'sh000001', name: '上证指数' },
  { code: 'sz399001', name: '深证成指' },
  { code: 'sz399006', name: '创业板指' },
  { code: '600519', name: '贵州茅台' },
  { code: '300750', name: '宁德时代' },
];

// 搜索结果项
export interface SearchResult {
  code: string;
  name: string;
  exchange?: string;
  type?: string; // stock / etf
  tag?: string; // 指数 / ETF
}

// 行情数据
export interface QuoteData {
  code: string;
  name: string;
  last: number;
  prevClose: number;
  change: number;
  changePct: number;
  up: boolean;
  open: number;
  high: number;
  low: number;
  volume: number;       // 成交量（手）
  amount: number;       // 成交额（元）
  insideDish: number;   // 内盘（手）
  outerDisc: number;    // 外盘（手）
  decimals: number;
}
