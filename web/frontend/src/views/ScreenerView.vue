<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { theme, toggleTheme } from '@/stores/theme';
import {
  runScreener,
  getScreenerResults,
  getStockDetail,
  syncMarketData,
  getSyncStatus,
  getDBStats,
  formatAmount,
  type ScreenerResult,
  type StockDetail,
} from '@/api';

const emit = defineEmits<{
  openChart: [code: string, name: string];
}>();

// 状态
const results = ref<ScreenerResult[]>([]);
const loading = ref(false);
const syncing = ref(false);
const syncProgress = ref({ status: 'idle', total: 0, done: 0, failed: 0 });
const dbStats = ref({ total_rows: 0, total_codes: 0 });
const runInfo = ref({ run_id: '', run_at: '', total_scanned: 0, pool_count: 0 });

// 筛选
const tierFilter = ref<'all' | 'complete' | 'partial' | 'pool_only'>('all');
type SortKey = 'low_raise_pct' | 'rebound_pct' | 'room_pct' | 'last_close' | 'high_100' | 'low_100' | 'avg_amount_10';
const sortKey = ref<SortKey>('low_raise_pct');
const sortDesc = ref(true);

// 点击表头排序
function handleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDesc.value = !sortDesc.value;
  } else {
    sortKey.value = key;
    sortDesc.value = true; // 数字列默认降序
  }
}

// 排序箭头
function sortArrow(key: SortKey): string {
  if (sortKey.value !== key) return '';
  return sortDesc.value ? ' ↓' : ' ↑';
}

// 详情弹窗
const showDetail = ref(false);
const detailCode = ref('');
const detailData = ref<StockDetail | null>(null);
const detailLoading = ref(false);

let syncTimer: ReturnType<typeof setInterval> | null = null;

// 筛选后的结果
const filteredResults = computed(() => {
  let list = results.value;
  if (tierFilter.value !== 'all') {
    list = list.filter((r) => r.tier === tierFilter.value);
  }
  return [...list].sort((a, b) => {
    const av = a[sortKey.value] ?? 0;
    const bv = b[sortKey.value] ?? 0;
    return sortDesc.value ? bv - av : av - bv;
  });
});

// 分层统计
const tierCounts = computed(() => {
  const counts: Record<string, number> = { complete: 0, partial: 0, pool_only: 0 };
  results.value.forEach((r) => {
    counts[r.tier] = (counts[r.tier] || 0) + 1;
  });
  return counts;
});

// 执行选股
async function handleRunScreener() {
  loading.value = true;
  try {
    const data = await runScreener();
    if (data) {
      results.value = data.results;
      runInfo.value = {
        run_id: data.run_id,
        run_at: data.run_at,
        total_scanned: data.total_scanned,
        pool_count: data.pool_count,
      };
    }
  } finally {
    loading.value = false;
  }
}

// 同步数据
async function handleSync() {
  syncing.value = true;
  await syncMarketData();
  // 轮询同步状态
  syncTimer = setInterval(async () => {
    const status = await getSyncStatus();
    if (status) {
      syncProgress.value = status;
      if (status.status === 'success' || status.status === 'partial' || status.status === 'failed') {
        syncing.value = false;
        if (syncTimer) clearInterval(syncTimer);
        await loadDBStats();
      }
    }
  }, 2000);
}

// 加载数据库统计
async function loadDBStats() {
  const stats = await getDBStats();
  if (stats) dbStats.value = stats;
}

// 查看详情
async function handleDetail(code: string, name: string) {
  detailCode.value = code;
  showDetail.value = true;
  detailLoading.value = true;
  detailData.value = null;
  const data = await getStockDetail(code);
  detailData.value = data;
  detailLoading.value = false;
}

// 跳转图表
function handleOpenChart(code: string, name: string) {
  emit('openChart', code, name);
}

// 分层标签样式
function tierLabel(tier: string): string {
  switch (tier) {
    case 'complete': return '结构完整';
    case 'partial': return '部分满足';
    default: return '仅入池';
  }
}

function tierClass(tier: string): string {
  switch (tier) {
    case 'complete': return 'tier-complete';
    case 'partial': return 'tier-partial';
    default: return 'tier-pool';
  }
}

// 格式化百分比
function fmtPct(v: number | undefined): string {
  if (v === undefined || v === null) return '--';
  return v.toFixed(2) + '%';
}

// 格式化价格
function fmtPrice(v: number | undefined): string {
  if (v === undefined || v === null) return '--';
  return v.toFixed(2);
}

onMounted(() => {
  loadDBStats();
  // 页面加载时自动获取最近一次选股结果
  getScreenerResults().then((r) => {
    if (r.length > 0) results.value = r;
  });
});

onUnmounted(() => {
  if (syncTimer) clearInterval(syncTimer);
});
</script>

<template>
  <div class="screener-view">
    <!-- 顶部工具栏 -->
    <div class="sc-header">
      <div class="sc-title">选股策略</div>
      <div class="sc-actions">
        <span class="sc-db-info">
          数据: {{ dbStats.total_codes }} 只 / {{ dbStats.total_rows }} 条
        </span>
        <button class="btn-sync" :disabled="syncing" @click="handleSync">
          {{ syncing ? `同步中 ${syncProgress.done}/${syncProgress.total}` : '同步数据' }}
        </button>
        <button class="btn-run" :disabled="loading" @click="handleRunScreener">
          {{ loading ? '选股中...' : '执行选股' }}
        </button>
        <button class="btn-theme" @click="toggleTheme">
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
      </div>
    </div>

    <!-- 运行信息 -->
    <div v-if="runInfo.run_id" class="sc-run-info">
      运行ID: {{ runInfo.run_id }} | 扫描 {{ runInfo.total_scanned }} 只 |
      入池 {{ runInfo.pool_count }} 只 |
      结构完整 {{ tierCounts.complete }} | 部分满足 {{ tierCounts.partial }} | 仅入池 {{ tierCounts.pool_only }}
    </div>

    <!-- 筛选栏 -->
    <div class="sc-filter-bar">
      <div class="sc-filter-group">
        <span class="sc-filter-label">分层:</span>
        <button
          v-for="t in ['all', 'complete', 'partial', 'pool_only']"
          :key="t"
          :class="['sc-filter-btn', { active: tierFilter === t }]"
          @click="tierFilter = t as any"
        >
          {{ t === 'all' ? '全部' : tierLabel(t) }}
          <span class="sc-filter-count">{{ t === 'all' ? results.length : tierCounts[t] }}</span>
        </button>
      </div>
      <div class="sc-filter-hint">点击表头列名可排序</div>
    </div>

    <!-- 结果表格 -->
    <div class="sc-table-wrap">
      <table class="sc-table">
        <thead>
          <tr>
            <th class="col-name">名称/代码</th>
            <th class="col-num">分层</th>
            <th class="col-num sortable" @click="handleSort('low_raise_pct')">低点抬升{{ sortArrow('low_raise_pct') }}</th>
            <th class="col-num sortable" @click="handleSort('rebound_pct')">距低点回升{{ sortArrow('rebound_pct') }}</th>
            <th class="col-num sortable" @click="handleSort('room_pct')">距高点空间{{ sortArrow('room_pct') }}</th>
            <th class="col-num sortable" @click="handleSort('last_close')">最新价{{ sortArrow('last_close') }}</th>
            <th class="col-num sortable" @click="handleSort('high_100')">百日高点{{ sortArrow('high_100') }}</th>
            <th class="col-num sortable" @click="handleSort('low_100')">百日低点{{ sortArrow('low_100') }}</th>
            <th class="col-num sortable" @click="handleSort('avg_amount_10')">近10日日均额{{ sortArrow('avg_amount_10') }}</th>
            <th class="col-num">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredResults"
            :key="row.code"
            class="sc-row"
          >
            <td class="col-name" @click="handleOpenChart(row.code, row.name)">
              <div class="stock-name">{{ row.name }}</div>
              <div class="stock-code">{{ row.code }}</div>
            </td>
            <td class="col-num">
              <span :class="['tier-badge', tierClass(row.tier)]">{{ tierLabel(row.tier) }}</span>
            </td>
            <td class="col-num positive">{{ fmtPct(row.low_raise_pct) }}</td>
            <td class="col-num" :class="{ positive: row.rebound_pct >= 15 }">{{ fmtPct(row.rebound_pct) }}</td>
            <td class="col-num" :class="{ negative: row.room_pct <= 15 }">{{ fmtPct(row.room_pct) }}</td>
            <td class="col-num price">{{ fmtPrice(row.last_close) }}</td>
            <td class="col-num">{{ fmtPrice(row.high_100) }}</td>
            <td class="col-num">{{ fmtPrice(row.low_100) }}</td>
            <td class="col-num">{{ formatAmount(row.avg_amount_10) }}</td>
            <td class="col-num">
              <button class="btn-chart" @click.stop="handleDetail(row.code, row.name)">详情</button>
            </td>
          </tr>
          <tr v-if="filteredResults.length === 0">
            <td colspan="10" class="sc-empty">
              {{ loading ? '正在选股...' : '暂无结果，点击"执行选股"开始' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="showDetail" class="sc-modal-overlay" @click="showDetail = false">
      <div class="sc-modal" @click.stop>
        <div class="sc-modal-header">
          <span>{{ detailData?.basic?.code || detailCode }} 详细诊断</span>
          <button class="btn-close" @click="showDetail = false">×</button>
        </div>
        <div v-if="detailLoading" class="sc-modal-body">加载中...</div>
        <div v-else-if="detailData" class="sc-modal-body">
          <!-- 基本信息 -->
          <div class="detail-section">
            <h4>基本信息</h4>
            <div class="detail-grid">
              <div><span class="label">最新价:</span> {{ fmtPrice(detailData.basic.last_close) }}</div>
              <div><span class="label">最新日期:</span> {{ detailData.basic.last_date }}</div>
              <div><span class="label">百日高点:</span> {{ fmtPrice(detailData.basic.high_100) }}</div>
              <div><span class="label">百日低点:</span> {{ fmtPrice(detailData.basic.low_100) }}</div>
              <div><span class="label">近60日低点:</span> {{ fmtPrice(detailData.basic.low_60) }}</div>
              <div><span class="label">前40日低点:</span> {{ fmtPrice(detailData.basic.low_prev40) }}</div>
              <div><span class="label">MA60:</span> {{ fmtPrice(detailData.basic.ma60) }}</div>
            </div>
          </div>

          <!-- 入池条件 -->
          <div class="detail-section">
            <h4>入池条件</h4>
            <div class="detail-checks">
              <div :class="['check-item', { pass: detailData.pool_checks.structure_double_window }]">
                {{ detailData.pool_checks.structure_double_window ? '✓' : '✗' }} 结构双窗（低点抬高）
              </div>
              <div :class="['check-item', { pass: detailData.pool_checks.new_high_confirm }]">
                {{ detailData.pool_checks.new_high_confirm ? '✓' : '✗' }} 新高确认（20日内创60日新高）
              </div>
              <div :class="['check-item', { pass: detailData.pool_checks.amplitude }]">
                {{ detailData.pool_checks.amplitude ? '✓' : '✗' }} 波幅证据（≥25%）
              </div>
              <div :class="['check-item', { pass: detailData.pool_checks.liquidity }]">
                {{ detailData.pool_checks.liquidity ? '✓' : '✗' }} 流动性（日均额>2亿）
              </div>
            </div>
          </div>

          <!-- 分层指标 -->
          <div class="detail-section">
            <h4>分层指标</h4>
            <div class="detail-grid">
              <div><span class="label">低点抬升幅度:</span> {{ fmtPct(detailData.tier_indicators.low_raise_pct) }}</div>
              <div :class="{ 'pass-text': detailData.tier_indicators.rebound_pass }">
                <span class="label">距低点回升:</span> {{ fmtPct(detailData.tier_indicators.rebound_pct) }} (≥15%)
              </div>
              <div :class="{ 'pass-text': detailData.tier_indicators.room_pass }">
                <span class="label">距高点空间:</span> {{ fmtPct(detailData.tier_indicators.room_pct) }} (≤15%)
              </div>
              <div :class="{ 'pass-text': detailData.tier_indicators.volume_pass }">
                <span class="label">近10日日均额:</span> {{ formatAmount(detailData.tier_indicators.avg_amount_10) }} (>2亿)
              </div>
            </div>
          </div>

          <!-- 三点验证 -->
          <div class="detail-section">
            <h4>三点验证</h4>
            <div class="detail-checks">
              <div :class="['check-item', { pass: detailData.confirmations.support.pass }]">
                {{ detailData.confirmations.support.pass ? '✓' : '✗' }} 支撑验证: {{ detailData.confirmations.support.description }}
              </div>
              <div :class="['check-item', { pass: detailData.confirmations.volume_breakout.pass }]">
                {{ detailData.confirmations.volume_breakout.pass ? '✓' : '✗' }} 放量突破: {{ detailData.confirmations.volume_breakout.description }}
              </div>
              <div :class="['check-item', { pass: detailData.confirmations.ma_turn.pass }]">
                {{ detailData.confirmations.ma_turn.pass ? '✓' : '✗' }} 均线拐头: {{ detailData.confirmations.ma_turn.description }}
              </div>
            </div>
            <div class="detail-verdict" :class="{ allpass: detailData.confirmations.all_pass }">
              {{ detailData.confirmations.all_pass ? '★ 三点验证全部通过，可进入可操作清单' : '未完全通过三点验证' }}
            </div>
          </div>

          <!-- 证伪信号 -->
          <div class="detail-section" :class="{ invalid: detailData.invalidation.invalidated }">
            <h4>证伪信号（生死线）</h4>
            <div class="detail-checks">
              <div :class="['check-item', { pass: !detailData.invalidation.invalidated }]">
                {{ detailData.invalidation.invalidated ? '✗ 已破位' : '✓ 未破位' }}: {{ detailData.invalidation.description }}
              </div>
            </div>
          </div>

          <!-- 交易参数（三锚点 + 五公式） -->
          <div v-if="detailData.trading" class="detail-section trading-section">
            <h4>交易参数（三锚点 · 五公式）</h4>
            <div class="trading-anchors">
              <div class="anchor-item">
                <span class="anchor-label">结构低点 A</span>
                <span class="anchor-value">{{ detailData.trading.anchors.A }}</span>
              </div>
              <div class="anchor-item">
                <span class="anchor-label">百日高点 H</span>
                <span class="anchor-value">{{ detailData.trading.anchors.H }}</span>
              </div>
              <div class="anchor-item">
                <span class="anchor-label">MA20</span>
                <span class="anchor-value">{{ detailData.trading.anchors.MA20 }}</span>
              </div>
              <div class="anchor-item">
                <span class="anchor-label">抬升线</span>
                <span class="anchor-value">{{ detailData.trading.anchors.raise_line }}</span>
              </div>
            </div>

            <div class="trading-params">
              <div class="param-row param-buy">
                <span class="param-label">买入价 B</span>
                <span class="param-value">{{ detailData.trading.params.B }}</span>
                <span class="param-desc">{{ detailData.trading.buy_info.mode }}</span>
              </div>
              <div class="param-row param-stop1">
                <span class="param-label">先导止损 L1</span>
                <span class="param-value">{{ detailData.trading.params.L1 }}</span>
                <span class="param-desc">B×0.92，跌破减半</span>
              </div>
              <div class="param-row param-stop2">
                <span class="param-label">硬止损 L2</span>
                <span class="param-value">{{ detailData.trading.params.L2 }}</span>
                <span class="param-desc">A×0.97，跌破清仓</span>
              </div>
              <div class="param-row param-target">
                <span class="param-label">目标 T</span>
                <span class="param-value">{{ detailData.trading.params.T }}</span>
                <span class="param-desc">H×1.03</span>
              </div>
              <div class="param-row" :class="{ 'rr-pass': detailData.trading.params.RR >= 2, 'rr-fail': detailData.trading.params.RR < 2 }">
                <span class="param-label">盈亏比 RR</span>
                <span class="param-value">{{ detailData.trading.params.RR }}</span>
                <span class="param-desc">{{ detailData.trading.params.RR >= 2 ? '≥2.0 达标' : '<2.0 不开仓' }}</span>
              </div>
              <div class="param-row">
                <span class="param-label">建议仓位</span>
                <span class="param-value">{{ detailData.trading.params.position_pct }}%</span>
                <span class="param-desc">{{ detailData.trading.params.shares }}股 / {{ detailData.trading.params.position_value }}元</span>
              </div>
            </div>

            <!-- 价格位置与操作建议 -->
            <div class="trading-position" :class="'zone-' + detailData.trading.position.zone">
              <div class="position-action">
                <span class="action-label">操作建议:</span>
                <span class="action-value">{{ detailData.trading.position.action }}</span>
              </div>
              <div class="position-signals">
                <div v-for="(sig, i) in detailData.trading.position.signals" :key="i" class="signal-item">
                  {{ sig }}
                </div>
              </div>
            </div>

            <div v-if="!detailData.trading.params.can_open" class="trading-warning">
              ⚠ {{ detailData.trading.params.reason }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.screener-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary, #131722);
  color: var(--text-primary, #d1d4dc);
}

.sc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
}

.sc-title {
  font-size: 18px;
  font-weight: 600;
}

.sc-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sc-db-info {
  font-size: 12px;
  color: var(--text-secondary, #787b86);
}

.btn-sync, .btn-run, .btn-theme {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-sync {
  background: #2962ff;
  color: #fff;
}
.btn-sync:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-run {
  background: #f2994a;
  color: #fff;
  font-weight: 600;
}
.btn-run:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-theme {
  background: var(--btn-bg, #2a2e39);
  color: var(--text-primary, #d1d4dc);
}

.sc-run-info {
  padding: 8px 16px;
  font-size: 12px;
  color: var(--text-secondary, #787b86);
  background: var(--bg-secondary, #1e222d);
  border-bottom: 1px solid var(--border-color, #2a2e39);
}

.sc-filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
}

.sc-filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sc-filter-label {
  font-size: 12px;
  color: var(--text-secondary, #787b86);
}

.sc-filter-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 3px;
  background: transparent;
  color: var(--text-primary, #d1d4dc);
  cursor: pointer;
  font-size: 12px;
}
.sc-filter-btn.active {
  background: #2962ff;
  border-color: #2962ff;
  color: #fff;
}
.sc-filter-count {
  display: inline-block;
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(120,123,134,0.2);
  font-size: 10px;
  font-weight: 600;
  min-width: 16px;
  text-align: center;
}
.sc-filter-btn.active .sc-filter-count {
  background: rgba(255,255,255,0.25);
}

.sc-select {
  padding: 4px 8px;
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 3px;
  background: var(--bg-secondary, #1e222d);
  color: var(--text-primary, #d1d4dc);
  font-size: 12px;
}

.sc-filter-hint {
  font-size: 12px;
  color: var(--text-secondary, #787b86);
  font-style: italic;
}

.sc-table-wrap {
  flex: 1;
  overflow: auto;
}

.sc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.sc-table th {
  position: sticky;
  top: 0;
  background: var(--bg-secondary, #1e222d);
  padding: 8px 10px;
  text-align: right;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary, #787b86);
  border-bottom: 1px solid var(--border-color, #2a2e39);
  z-index: 1;
}

.sc-table th.sortable {
  cursor: pointer;
  user-select: none;
}
.sc-table th.sortable:hover {
  color: var(--text-primary, #d1d4dc);
  background: var(--row-hover, #252a35);
}

.sc-table th.col-name, .sc-table td.col-name {
  text-align: left;
}

.sc-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  text-align: right;
}

.sc-row {
  cursor: pointer;
}
.sc-row:hover {
  background: var(--row-hover, #1e222d);
}

.sc-table td.col-name {
  cursor: pointer;
}
.sc-table td.col-name:hover .stock-name {
  color: #2962ff;
}
.stock-name {
  font-weight: 600;
}
.stock-code {
  font-size: 11px;
  color: var(--text-secondary, #787b86);
  margin-top: 2px;
}

.tier-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}
.tier-complete { background: #26a69a; color: #fff; }
.tier-partial { background: #f2994a; color: #fff; }
.tier-pool { background: #787b86; color: #fff; }

.positive { color: #ef5350; }
.negative { color: #26a69a; }
.price { font-weight: 600; }

.btn-chart {
  padding: 3px 10px;
  border: 1px solid #2962ff;
  border-radius: 3px;
  background: transparent;
  color: #2962ff;
  cursor: pointer;
  font-size: 12px;
}

.sc-empty {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary, #787b86);
}

/* 弹窗 */
.sc-modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.sc-modal {
  width: 600px;
  max-height: 80vh;
  background: var(--bg-primary, #131722);
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.sc-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  color: var(--text-primary, #d1d4dc);
  font-size: 20px;
  cursor: pointer;
}

.sc-modal-body {
  padding: 16px;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 16px;
}
.detail-section h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: var(--text-secondary, #787b86);
}
.detail-section.invalid h4 {
  color: #ef5350;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
  font-size: 13px;
}
.detail-grid .label {
  color: var(--text-secondary, #787b86);
}

.detail-checks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.check-item {
  color: var(--text-secondary, #787b86);
}
.check-item.pass {
  color: #26a69a;
}

.pass-text {
  color: #26a69a;
}

.detail-verdict {
  margin-top: 8px;
  padding: 8px;
  border-radius: 4px;
  background: var(--bg-secondary, #1e222d);
  font-size: 13px;
  text-align: center;
}
.detail-verdict.allpass {
  background: rgba(38, 166, 154, 0.15);
  color: #26a69a;
  font-weight: 600;
}

/* 交易参数 */
.trading-section {
  border-top: 2px solid #2962ff;
  padding-top: 12px;
}
.trading-anchors {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 10px;
}
.anchor-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px;
  background: var(--bg-secondary, #1e222d);
  border-radius: 3px;
  font-size: 12px;
}
.anchor-label { color: var(--text-secondary, #787b86); }
.anchor-value { font-weight: 600; }

.trading-params {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}
.param-row {
  display: flex;
  align-items: center;
  padding: 5px 8px;
  border-radius: 3px;
  font-size: 13px;
  background: var(--bg-secondary, #1e222d);
}
.param-label { width: 90px; color: var(--text-secondary, #787b86); }
.param-value { width: 70px; font-weight: 600; text-align: right; }
.param-desc { flex: 1; font-size: 11px; color: var(--text-secondary, #787b86); margin-left: 8px; }
.param-buy .param-value { color: #2962ff; }
.param-stop1 .param-value { color: #f2994a; }
.param-stop2 .param-value { color: #ef5350; }
.param-target .param-value { color: #26a69a; }
.rr-pass .param-value { color: #26a69a; }
.rr-fail .param-value { color: #ef5350; }

.trading-position {
  padding: 10px;
  border-radius: 4px;
  margin-bottom: 8px;
  border-left: 3px solid;
}
.position-action {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.action-label { font-size: 12px; color: var(--text-secondary, #787b86); }
.action-value { font-weight: 700; font-size: 15px; }
.position-signals { font-size: 12px; }
.signal-item { margin: 2px 0; color: var(--text-primary, #d1d4dc); }

.zone-below_L2 { background: rgba(239,83,80,0.15); border-color: #ef5350; }
.zone-below_L2 .action-value { color: #ef5350; }
.zone-L2_L1 { background: rgba(242,153,74,0.15); border-color: #f2994a; }
.zone-L2_L1 .action-value { color: #f2994a; }
.zone-L1_B { background: rgba(120,123,134,0.1); border-color: #787b86; }
.zone-B_T { background: rgba(41,98,255,0.1); border-color: #2962ff; }
.zone-B_T .action-value { color: #2962ff; }
.zone-above_T { background: rgba(38,166,154,0.15); border-color: #26a69a; }
.zone-above_T .action-value { color: #26a69a; }

.trading-warning {
  padding: 8px;
  background: rgba(239,83,80,0.1);
  border-radius: 4px;
  color: #ef5350;
  font-size: 12px;
}

/* 浅色主题 */
.light .screener-view {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f6f8;
  --text-primary: #131722;
  --text-secondary: #787b86;
  --border-color: #e0e3eb;
  --btn-bg: #f0f1f3;
  --row-hover: #f5f6f8;
}
</style>
