<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue';
import { Vela, registerNativeIndicator } from '@luxalgo/vela';
import { AShareProvider, StaticProvider } from '@/providers/ashare';

// 全局存储买卖点数据，供 NativeIndicator 读取
let tradeMarkersData: Array<{ date: string; price: number; type: string }> = [];

// 注册买卖点标记指标
registerNativeIndicator({
  type: 'trade_markers',
  title: 'Trade Markers',
  shortTitle: 'TM',
  paneHint: 'price',
  overlay: true,
  legend: false,
  multiInstance: false,
  inputsSchema: () => [],
  defaultInputs: () => ({}),
  create: () => {
    let ctx: any = null;
    const emitMarkers = () => {
      if (!ctx) return;
      const tzOffset = new Date().getTimezoneOffset() * 60 * 1000;
      const labels = tradeMarkersData.map((trade, idx) => {
        const time = new Date(trade.date + 'T15:00:00+08:00').getTime() - tzOffset;
        const isBuy = trade.type === 'buy';
        return {
          id: `tm_${idx}`,
          paneId: 'price',
          xloc: 'bar_time',
          x: time,
          y: trade.price,
          yloc: 'price',
          text: isBuy ? 'B' : 'S',
          style: {},
          color: isBuy ? '#ef5350' : '#26a69a',
          textColor: '#ffffff',
          size: 'normal',
          textAlign: 'center',
          fontFamily: 'default',
          tooltip: `${isBuy ? '买入' : '卖出'} ${trade.date} @ ${trade.price}`,
        };
      });
      ctx.emit({ labels });
    };
    return {
      start(context: any) {
        ctx = context;
        emitMarkers();
      },
      onBars() {
        emitMarkers();
      },
      onViewport() {},
      setInputs() {},
      suspend() {},
      resume() {
        emitMarkers();
      },
      stop() {},
    };
  },
});
import { theme, toggleTheme } from '@/stores/theme';
import { isInWatchlist, addToWatchlist, removeFromWatchlist } from '@/stores/watchlist';
import { fetchStockQuote, fetchIndexQuote, type QuoteData, runSingleBacktest, type BacktestResult } from '@/api';
import { isIndexCode, getIndexPureCode } from '@/constants';
import SearchBox from '@/components/SearchBox.vue';
import QuoteBar from '@/components/QuoteBar.vue';

const props = defineProps<{
  code: string;
  name: string;
}>();

const emit = defineEmits<{
  back: [];
}>();

const chartContainer = ref<HTMLDivElement | null>(null);
const currentTF = ref('D');
const quote = ref<QuoteData | null>(null);
const chartRef = ref<InstanceType<typeof Vela> | null>(null);
const staticProvider = ref<StaticProvider | null>(null);
const isBacktestMode = ref(false);
let quoteTimer: ReturnType<typeof setInterval> | null = null;

const TIMEFRAMES = [
  { key: '1', label: '1分' },
  { key: '5', label: '5分' },
  { key: '15', label: '15分' },
  { key: '30', label: '30分' },
  { key: '60', label: '60分' },
  { key: 'D', label: '日K' },
  { key: 'W', label: '周线' },
  { key: 'M', label: '月线' },
];

const inWatchlist = ref(false);

// 回测相关
const showBacktestModal = ref(false);
const backtestLoading = ref(false);
const backtestResult = ref<BacktestResult | null>(null);
const showBacktestPanel = ref(false);
const btStartDate = ref('');
const btEndDate = ref('');
const btCapital = ref(100000);
const btFeeRate = ref(0.00025); // 手续费率，默认万2.5

function checkWatchlist() {
  inWatchlist.value = isInWatchlist(props.code);
}

function toggleWatch() {
  if (inWatchlist.value) {
    removeFromWatchlist(props.code);
  } else {
    addToWatchlist(props.code, props.name);
  }
  inWatchlist.value = !inWatchlist.value;
}

async function loadQuote() {
  const q = isIndexCode(props.code)
    ? await fetchIndexQuote(props.code)
    : await fetchStockQuote(props.code);
  if (q) {
    q.code = isIndexCode(props.code) ? getIndexPureCode(props.code) : q.code;
    quote.value = q;
  }
}

function initChart() {
  if (!chartContainer.value) return;
  if (chartRef.value) {
    chartRef.value.destroy();
    chartRef.value = null;
  }

  chartRef.value = new Vela(chartContainer.value, {
    symbol: `ashare:${props.code}`,
    timeframe: currentTF.value,
    theme: theme.value,
    upColor: '#ef5350',
    downColor: '#26a69a',
  });

  const provider = new AShareProvider();
  chartRef.value.data.registerProvider('ashare', provider);
  chartRef.value.addNativeIndicator('volume');
}

function switchTF(tf: string) {
  currentTF.value = tf;
  if (chartRef.value) {
    chartRef.value.setMarket({ timeframe: tf });
  }
}

function onSearchSelect(code: string, name: string) {
  emit('back');
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent('open-chart', { detail: { code, name } }));
  }, 50);
}

// 回测功能
function openBacktestModal() {
  // 默认回测区间：最近180天
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 180);
  btStartDate.value = start.toISOString().slice(0, 10);
  btEndDate.value = end.toISOString().slice(0, 10);
  showBacktestModal.value = true;
}

async function startBacktest() {
  backtestLoading.value = true;
  showBacktestModal.value = false;
  try {
    // 去掉 sh/sz 前缀，DuckDB 中存储纯数字代码
    const pureCode = props.code.replace(/^(sh|sz|bj)/i, '');
    const result = await runSingleBacktest(
      pureCode,
      btStartDate.value || undefined,
      btEndDate.value || undefined,
      btCapital.value,
      btFeeRate.value,
    );
    if (result) {
      if (result.error) {
        alert('回测失败：' + result.error);
        return;
      }
      if (result.klines.length === 0) {
        alert('回测无数据：该股票在指定区间内没有足够的历史数据');
        return;
      }
      backtestResult.value = result;
      showBacktestPanel.value = true;
      // 切换到回测模式
      enterBacktestMode();
    } else {
      alert('回测请求失败，请检查服务是否正常');
    }
  } finally {
    backtestLoading.value = false;
  }
}

// 回测K线转 OHLCV 格式
function backtestKlinesToOHLCV(klines: any[]): any[] {
  const tzOffset = new Date().getTimezoneOffset() * 60 * 1000;
  return klines.map((k) => {
    const time = new Date(k.date + 'T15:00:00+08:00').getTime();
    return {
      time: isNaN(time) ? Date.now() : time - tzOffset,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
      volume: k.volume || 0,
    };
  });
}

// 进入回测模式：用静态数据替换实时数据
function enterBacktestMode() {
  if (!backtestResult.value || !chartRef.value) return;
  isBacktestMode.value = true;
  const allBars = backtestKlinesToOHLCV(backtestResult.value.klines);
  // 显示全部K线
  staticProvider.value = new StaticProvider(allBars);
  chartRef.value.data.registerProvider('static', staticProvider.value);
  chartRef.value.setMarket({ symbol: `static:${props.code}`, timeframe: 'D' });
  currentTF.value = 'D';
  // 延迟绘制买卖点标记，等图表加载完成
  setTimeout(() => drawTradeMarkers(), 800);
}

// 退出回测模式
function exitBacktestMode() {
  isBacktestMode.value = false;
  staticProvider.value = null;
  if (chartRef.value) {
    chartRef.value.setMarket({ symbol: `ashare:${props.code}`, timeframe: currentTF.value });
  }
}

// 在K线图上绘制买卖点标记（通过 NativeIndicator）
function drawTradeMarkers() {
  if (!chartRef.value || !backtestResult.value) return;
  // 设置全局买卖点数据
  tradeMarkersData = backtestResult.value.trades.map(t => ({
    date: t.date,
    price: t.price,
    type: t.type,
  }));
  // 添加指标（如果已存在则先移除）
  const chart = chartRef.value as any;
  try {
    // 尝试移除已存在的指标
    const indicators = chart.indicators?.list?.() || [];
    indicators.forEach((ind: any) => {
      if (ind.type === 'trade_markers') {
        chart.removeIndicator?.(ind.handle || ind.id);
      }
    });
  } catch (e) {
    // ignore
  }
  // 添加新指标
  setTimeout(() => {
    try {
      chart.addNativeIndicator('trade_markers');
    } catch (e) {
      console.warn('Failed to add trade_markers indicator:', e);
    }
  }, 300);
}

function closeBacktestPanel() {
  showBacktestPanel.value = false;
  exitBacktestMode();
}

watch(theme, () => {
  nextTick(() => initChart());
});

onMounted(() => {
  checkWatchlist();
  loadQuote();
  quoteTimer = setInterval(loadQuote, 5000);
  nextTick(() => initChart());
});

onUnmounted(() => {
  if (quoteTimer) clearInterval(quoteTimer);
  if (chartRef.value) {
    chartRef.value.destroy();
    chartRef.value = null;
  }
});
</script>

<template>
  <div class="chart-view" :class="{ light: theme === 'light' }">
    <div class="chart-header">
      <button class="btn-back" @click="emit('back')">←</button>
      <SearchBox @select="onSearchSelect" />
      <div class="tf-group">
        <button
          v-for="tf in TIMEFRAMES"
          :key="tf.key"
          :class="{ active: currentTF === tf.key }"
          @click="switchTF(tf.key)"
        >
          {{ tf.label }}
        </button>
      </div>
      <button class="btn-backtest" @click="openBacktestModal" title="历史回测">
        📊 回测
      </button>
      <button class="btn-star" :class="{ active: inWatchlist }" @click="toggleWatch">
        {{ inWatchlist ? '★' : '☆' }}
      </button>
      <button class="btn-theme" @click="toggleTheme">
        {{ theme === 'dark' ? '☀' : '☾' }}
      </button>
    </div>

    <QuoteBar :quote="quote" :name="name" />

    <div class="chart-body">
      <div ref="chartContainer" class="chart-container"></div>

      <!-- 回测结果面板 -->
      <div v-if="showBacktestPanel && backtestResult" class="backtest-panel">
        <div class="bt-header">
          <span class="bt-title">📊 回测结果</span>
          <button class="bt-close" @click="closeBacktestPanel">×</button>
        </div>

        <!-- 收益统计 -->
        <div class="bt-stats">
          <div class="stat-card" :class="{ positive: backtestResult.total_return_pct >= 0, negative: backtestResult.total_return_pct < 0 }">
            <div class="stat-label">总收益</div>
            <div class="stat-value">{{ backtestResult.total_return_pct >= 0 ? '+' : '' }}{{ backtestResult.total_return_pct }}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">胜率</div>
            <div class="stat-value">{{ backtestResult.win_rate }}%</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">交易次数</div>
            <div class="stat-value">{{ backtestResult.total_trades }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">结构数</div>
            <div class="stat-value">{{ backtestResult.structure_count }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">期末资金</div>
            <div class="stat-value">¥{{ backtestResult.final_value.toLocaleString() }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">最大盈利</div>
            <div class="stat-value positive">+¥{{ backtestResult.max_profit.toLocaleString() }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">最大亏损</div>
            <div class="stat-value negative">¥{{ backtestResult.max_loss.toLocaleString() }}</div>
          </div>
        </div>

        <!-- 交易记录 -->
        <div class="bt-trades">
          <div class="trades-title">交易记录（{{ backtestResult.trades.length }}笔）</div>
          <div class="trades-table">
            <div class="trades-header">
              <span>日期</span>
              <span>方向</span>
              <span>价格</span>
              <span>数量</span>
              <span>盈亏</span>
              <span>原因</span>
            </div>
            <div
              v-for="(t, i) in backtestResult.trades"
              :key="i"
              class="trades-row"
            >
              <span>{{ t.date }}</span>
              <span :class="t.type">{{ t.type === 'buy' ? '买入' : '卖出' }}</span>
              <span>{{ t.price }}</span>
              <span>{{ t.shares }}</span>
              <span :class="{ positive: (t.profit || 0) > 0, negative: (t.profit || 0) < 0 }">
                {{ t.profit !== undefined ? (t.profit > 0 ? '+' : '') + t.profit : '--' }}
              </span>
              <span>{{ t.reason || '--' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 回测参数弹窗 -->
    <div v-if="showBacktestModal" class="modal-overlay" @click.self="showBacktestModal = false">
      <div class="modal-box">
        <div class="modal-title">历史回测设置</div>
        <div class="modal-body">
          <div class="form-group">
            <label>回测开始日期</label>
            <input type="date" v-model="btStartDate" />
          </div>
          <div class="form-group">
            <label>回测结束日期</label>
            <input type="date" v-model="btEndDate" />
          </div>
          <div class="form-group">
            <label>初始资金（元）</label>
            <input type="number" v-model.number="btCapital" min="10000" step="10000" />
          </div>
          <div class="form-group">
            <label>手续费率（如0.00025=万2.5）</label>
            <input type="number" v-model.number="btFeeRate" min="0" step="0.00001" />
          </div>
          <div class="form-hint">
            策略：底部抬高形态确认后买入，跌破L1减半、跌破L2清仓、达到T止盈
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showBacktestModal = false">取消</button>
          <button class="btn-confirm" :disabled="backtestLoading" @click="startBacktest">
            {{ backtestLoading ? '回测中...' : '开始回测' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #131722;
}
.chart-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #2a2e39;
}
.btn-back {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn-back:hover {
  background: #2a2e39;
}
.btn-backtest {
  padding: 4px 12px;
  background: #2962ff;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}
.btn-backtest:hover {
  background: #1e53e0;
}
.tf-group {
  display: flex;
  gap: 2px;
  background: #2a2e39;
  border-radius: 4px;
  padding: 2px;
  margin-left: auto;
}
.tf-group button {
  padding: 4px 10px;
  background: transparent;
  border: none;
  color: #787b86;
  cursor: pointer;
  border-radius: 3px;
  font-size: 11px;
}
.tf-group button.active {
  background: #2962ff;
  color: #fff;
}
.btn-star {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #787b86;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn-star.active {
  color: #ffc107;
  border-color: #ffc107;
}
.btn-theme {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn-theme:hover {
  background: #2a2e39;
}
.chart-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.chart-container {
  flex: 1;
  min-height: 0;
}

/* 回测面板 */
.backtest-panel {
  width: 380px;
  background: #1e222d;
  border-left: 1px solid #2a2e39;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.bt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #2a2e39;
}
.bt-title {
  font-weight: 600;
  color: #d1d4dc;
  font-size: 14px;
}
.bt-close {
  background: none;
  border: none;
  color: #787b86;
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}
.bt-close:hover {
  color: #d1d4dc;
}
.bt-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px 14px;
}
.stat-card {
  background: #131722;
  border-radius: 6px;
  padding: 8px 10px;
}
.stat-label {
  font-size: 11px;
  color: #787b86;
  margin-bottom: 4px;
}
.stat-value {
  font-size: 15px;
  font-weight: 700;
  color: #d1d4dc;
}
.stat-value.positive { color: #ef5350; }
.stat-value.negative { color: #26a69a; }
.stat-card.positive .stat-value { color: #ef5350; }
.stat-card.negative .stat-value { color: #26a69a; }

/* 播放控制 */
.bt-playback {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-top: 1px solid #2a2e39;
  border-bottom: 1px solid #2a2e39;
}
.play-btn {
  width: 28px;
  height: 28px;
  background: #2a2e39;
  border: none;
  border-radius: 4px;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.play-btn:hover:not(:disabled) {
  background: #363a45;
}
.play-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.play-btn.play-main {
  width: 36px;
  height: 36px;
  background: #2962ff;
  font-size: 14px;
}
.play-btn.play-main:hover {
  background: #1e53e0;
}
.play-slider {
  flex: 1;
  height: 4px;
  -webkit-appearance: none;
  background: #363a45;
  border-radius: 2px;
  outline: none;
}
.play-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  background: #2962ff;
  border-radius: 50%;
  cursor: pointer;
}
.play-info {
  font-size: 11px;
  color: #787b86;
  min-width: 50px;
  text-align: center;
}
.speed-select {
  background: #2a2e39;
  border: 1px solid #363a45;
  color: #d1d4dc;
  border-radius: 4px;
  padding: 2px 4px;
  font-size: 11px;
}

/* 当前K线信息 */
.bt-current {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 14px;
  font-size: 12px;
  color: #d1d4dc;
  border-bottom: 1px solid #2a2e39;
}
.current-date {
  font-weight: 600;
  color: #2962ff;
}
.trade-signal {
  display: flex;
  gap: 4px;
}
.signal-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}
.signal-badge.buy {
  background: rgba(239, 83, 80, 0.2);
  color: #ef5350;
}
.signal-badge.sell {
  background: rgba(38, 166, 154, 0.2);
  color: #26a69a;
}

/* 交易记录 */
.bt-trades {
  flex: 1;
  padding: 10px 14px;
  overflow-y: auto;
}
.trades-title {
  font-size: 13px;
  font-weight: 600;
  color: #d1d4dc;
  margin-bottom: 8px;
}
.trades-table {
  font-size: 11px;
}
.trades-header {
  display: grid;
  grid-template-columns: 70px 40px 50px 40px 60px 1fr;
  gap: 4px;
  padding: 6px 4px;
  color: #787b86;
  border-bottom: 1px solid #2a2e39;
  font-weight: 600;
}
.trades-row {
  display: grid;
  grid-template-columns: 70px 40px 50px 40px 60px 1fr;
  gap: 4px;
  padding: 6px 4px;
  color: #d1d4dc;
  border-bottom: 1px solid #1a1e28;
  cursor: pointer;
}
.trades-row:hover {
  background: #2a2e39;
}
.trades-row.active {
  background: rgba(41, 98, 255, 0.2);
}
.trades-row .buy { color: #ef5350; }
.trades-row .sell { color: #26a69a; }
.trades-row .positive { color: #ef5350; }
.trades-row .negative { color: #26a69a; }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-box {
  background: #1e222d;
  border-radius: 8px;
  width: 380px;
  border: 1px solid #2a2e39;
}
.modal-title {
  padding: 14px 18px;
  font-size: 15px;
  font-weight: 600;
  color: #d1d4dc;
  border-bottom: 1px solid #2a2e39;
}
.modal-body {
  padding: 18px;
}
.form-group {
  margin-bottom: 14px;
}
.form-group label {
  display: block;
  font-size: 12px;
  color: #787b86;
  margin-bottom: 6px;
}
.form-group input {
  width: 100%;
  padding: 8px 10px;
  background: #131722;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #d1d4dc;
  font-size: 13px;
  box-sizing: border-box;
}
.form-group input:focus {
  outline: none;
  border-color: #2962ff;
}
.form-hint {
  font-size: 11px;
  color: #787b86;
  margin-top: 10px;
  line-height: 1.5;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid #2a2e39;
}
.btn-cancel {
  padding: 7px 16px;
  background: transparent;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 13px;
}
.btn-cancel:hover {
  background: #2a2e39;
}
.btn-confirm {
  padding: 7px 16px;
  background: #2962ff;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.btn-confirm:hover:not(:disabled) {
  background: #1e53e0;
}
.btn-confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 浅色主题 */
.chart-view.light {
  background: #ffffff;
}
.chart-view.light .chart-header {
  border-bottom-color: #e0e0e0;
}
.chart-view.light .btn-back,
.chart-view.light .btn-star,
.chart-view.light .btn-theme {
  color: #333;
  border-color: #ddd;
}
.chart-view.light .btn-backtest {
  background: #2962ff;
  color: #fff;
}
.chart-view.light .btn-back:hover,
.chart-view.light .btn-star:hover,
.chart-view.light .btn-theme:hover {
  background: #f5f5f5;
}
.chart-view.light .tf-group {
  background: #f0f0f0;
}
.chart-view.light .tf-group button {
  color: #666;
}
.chart-view.light .tf-group button.active {
  background: #2962ff;
  color: #fff;
}
.chart-view.light .backtest-panel {
  background: #fafafa;
  border-left-color: #e0e0e0;
}
.chart-view.light .bt-header {
  border-bottom-color: #e0e0e0;
}
.chart-view.light .bt-title {
  color: #333;
}
.chart-view.light .bt-close {
  color: #999;
}
.chart-view.light .bt-close:hover {
  color: #333;
}
.chart-view.light .stat-card {
  background: #fff;
  border: 1px solid #eee;
}
.chart-view.light .stat-label {
  color: #999;
}
.chart-view.light .stat-value {
  color: #333;
}
.chart-view.light .trades-title {
  color: #333;
}
.chart-view.light .trades-header {
  background: #f5f5f5;
  color: #666;
  border-bottom-color: #e0e0e0;
}
.chart-view.light .trades-row {
  border-bottom-color: #eee;
  color: #333;
}
.chart-view.light .trades-row:hover {
  background: #f0f7ff;
}
.chart-view.light .modal-box {
  background: #fff;
}
.chart-view.light .modal-title {
  color: #333;
  border-bottom-color: #e0e0e0;
}
.chart-view.light .form-group label {
  color: #666;
}
.chart-view.light .form-group input {
  background: #fff;
  border-color: #ddd;
  color: #333;
}
.chart-view.light .form-hint {
  color: #999;
}
.chart-view.light .modal-footer {
  border-top-color: #e0e0e0;
}
.chart-view.light .btn-cancel {
  color: #333;
  border-color: #ddd;
}
.chart-view.light .btn-cancel:hover {
  background: #f5f5f5;
}
</style>
