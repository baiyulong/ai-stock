<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import {
  listPositions, addPosition, removePosition, checkPositions,
  type PositionItem, type PositionCheckItem,
} from '@/api';
import { theme } from '@/stores/theme';

const items = ref<PositionItem[]>([]);
const checkResults = ref<Map<string, PositionCheckItem>>(new Map());
const loading = ref(false);
const checking = ref(false);
const showAddForm = ref(false);
const newCode = ref('');
const newName = ref('');
const newBuyPrice = ref('');
const newShares = ref('');
const newBuyDate = ref('');
const autoRefreshTimer = ref<number | null>(null);

const hasSellSignal = computed(() => {
  for (const v of checkResults.value.values()) {
    if (v.has_signal) return true;
  }
  return false;
});

const totalMarketValue = computed(() => {
  let total = 0;
  for (const v of checkResults.value.values()) {
    total += v.market_value || 0;
  }
  return total;
});

const totalProfit = computed(() => {
  let total = 0;
  for (const v of checkResults.value.values()) {
    total += (v.current_price - v.buy_price) * v.shares;
  }
  return total;
});

async function loadList() {
  loading.value = true;
  try {
    items.value = await listPositions();
  } finally {
    loading.value = false;
  }
}

async function runCheck() {
  checking.value = true;
  try {
    const results = await checkPositions();
    const map = new Map<string, PositionCheckItem>();
    for (const r of results) map.set(r.code, r);
    checkResults.value = map;
  } finally {
    checking.value = false;
  }
}

async function handleAdd() {
  if (!newCode.value.trim() || !newBuyPrice.value || !newShares.value) return;
  const ok = await addPosition(
    newCode.value.trim(),
    newName.value.trim() || newCode.value.trim(),
    parseFloat(newBuyPrice.value),
    parseInt(newShares.value),
    newBuyDate.value || '',
  );
  if (ok) {
    newCode.value = '';
    newName.value = '';
    newBuyPrice.value = '';
    newShares.value = '';
    newBuyDate.value = '';
    showAddForm.value = false;
    await loadList();
    await runCheck();
  }
}

async function handleRemove(code: string) {
  await removePosition(code);
  checkResults.value.delete(code);
  await loadList();
}

function openChart(code: string, name: string) {
  window.dispatchEvent(new CustomEvent('open-chart', { detail: { code, name } }));
}

function getCheck(code: string): PositionCheckItem | undefined {
  return checkResults.value.get(code);
}

function getSignalClass(level: number): string {
  if (level === 3) return 'tag-clear';
  if (level === 2) return 'tag-half';
  if (level === 1) return 'tag-profit';
  return 'tag-hold';
}

function startAutoRefresh() {
  autoRefreshTimer.value = window.setInterval(() => {
    runCheck();
  }, 60000);
}

onMounted(() => {
  loadList().then(() => runCheck());
  startAutoRefresh();
});

onUnmounted(() => {
  if (autoRefreshTimer.value) clearInterval(autoRefreshTimer.value);
});
</script>

<template>
  <div class="position-view" :class="{ light: theme === 'light' }">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          持仓列表
          <span v-if="hasSellSignal" class="breathing-dot" title="有卖出信号"></span>
        </h2>
        <span class="item-count">{{ items.length }} 只</span>
        <span v-if="totalMarketValue > 0" class="total-value">
          市值 {{ (totalMarketValue / 10000).toFixed(1) }}万
          <span :class="totalProfit >= 0 ? 'profit-up' : 'profit-down'">
            {{ totalProfit >= 0 ? '+' : '' }}{{ (totalProfit / 10000).toFixed(1) }}万
          </span>
        </span>
      </div>
      <div class="header-actions">
        <button class="btn-refresh" :disabled="checking" @click="runCheck">
          {{ checking ? '检查中...' : '立即检查' }}
        </button>
        <button class="btn-add" @click="showAddForm = !showAddForm">
          {{ showAddForm ? '取消' : '+ 添加' }}
        </button>
      </div>
    </div>

    <!-- 添加表单 -->
    <div v-if="showAddForm" class="add-form">
      <input v-model="newCode" placeholder="股票代码" class="form-input" />
      <input v-model="newName" placeholder="名称" class="form-input" />
      <input v-model="newBuyPrice" placeholder="买入价" class="form-input" type="number" step="0.01" />
      <input v-model="newShares" placeholder="股数" class="form-input" type="number" />
      <input v-model="newBuyDate" placeholder="买入日期 (可选)" class="form-input" type="date" />
      <button class="btn-confirm" @click="handleAdd">确认添加</button>
    </div>

    <!-- 表格 -->
    <div class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>名称/代码</th>
            <th>买入价</th>
            <th>股数</th>
            <th>现价</th>
            <th>浮盈%</th>
            <th>市值</th>
            <th>L1(减半)</th>
            <th>L2(清仓)</th>
            <th>T(目标)</th>
            <th>信号</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="11" class="empty-cell">加载中...</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="11" class="empty-cell">暂无持仓，点击"添加"开始</td>
          </tr>
          <tr v-for="item in items" :key="item.code" :class="{ 'signal-row': getCheck(item.code)?.has_signal }">
            <td class="cell-name" @click="openChart(item.code, item.name)">
              <div class="cell-title">{{ item.name || item.code }}</div>
              <div class="cell-code">{{ item.code }}</div>
            </td>
            <td class="cell-num">{{ item.buy_price.toFixed(2) }}</td>
            <td class="cell-num">{{ item.shares.toLocaleString() }}</td>
            <td class="cell-num">{{ getCheck(item.code)?.current_price?.toFixed(2) || '--' }}</td>
            <td class="cell-num" :class="{ up: (getCheck(item.code)?.profit_pct || 0) >= 0, down: (getCheck(item.code)?.profit_pct || 0) < 0 }">
              {{ getCheck(item.code) ? (getCheck(item.code)!.profit_pct >= 0 ? '+' : '') + getCheck(item.code)!.profit_pct.toFixed(2) + '%' : '--' }}
            </td>
            <td class="cell-num">{{ getCheck(item.code) ? (getCheck(item.code)!.market_value / 10000).toFixed(1) + '万' : '--' }}</td>
            <td class="cell-num down">{{ getCheck(item.code)?.L1?.toFixed(2) || '--' }}</td>
            <td class="cell-num down">{{ getCheck(item.code)?.L2?.toFixed(2) || '--' }}</td>
            <td class="cell-num up">{{ getCheck(item.code)?.T?.toFixed(2) || '--' }}</td>
            <td class="cell-status">
              <span v-if="getCheck(item.code)?.has_signal" :class="['tag', getSignalClass(getCheck(item.code)!.signal_level), 'breathing-tag']">
                {{ getCheck(item.code)?.signal_type }}
              </span>
              <span v-else-if="getCheck(item.code)" class="tag tag-hold">持有</span>
              <span v-else class="tag tag-unknown">未检查</span>
            </td>
            <td class="cell-action">
              <button class="btn-remove" @click="handleRemove(item.code)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.position-view {
  padding: 16px 20px;
  color: #d1d4dc;
}
.position-view.light {
  color: #1a1a2e;
  background: #f5f6fa;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.item-count {
  font-size: 13px;
  color: #787b86;
}
.light .item-count { color: #888; }
.total-value {
  font-size: 13px;
  color: #787b86;
}
.light .total-value { color: #666; }
.profit-up { color: #ef5350; margin-left: 6px; }
.profit-down { color: #26a69a; margin-left: 6px; }
.header-actions {
  display: flex;
  gap: 8px;
}
.btn-refresh, .btn-add, .btn-confirm {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #363a45;
  background: #2a2e39;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 13px;
}
.light .btn-refresh, .light .btn-add, .light .btn-confirm {
  background: #fff;
  border-color: #d0d0d0;
  color: #333;
}
.btn-refresh:hover, .btn-add:hover, .btn-confirm:hover { background: #363a45; }
.light .btn-refresh:hover, .light .btn-add:hover, .light .btn-confirm:hover { background: #f0f0f0; }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.add-form {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #1e2128;
  border-radius: 8px;
  flex-wrap: wrap;
}
.light .add-form { background: #fff; border: 1px solid #e0e0e0; }
.form-input {
  flex: 1;
  min-width: 100px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #363a45;
  background: #131722;
  color: #d1d4dc;
  font-size: 13px;
}
.light .form-input {
  background: #f9f9f9;
  border-color: #d0d0d0;
  color: #333;
}
.table-container {
  overflow-x: auto;
  border-radius: 8px;
  background: #131722;
}
.light .table-container { background: #fff; border: 1px solid #e0e0e0; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 900px;
}
.data-table th {
  position: sticky;
  top: 0;
  background: #1e2128;
  padding: 10px 12px;
  text-align: right;
  font-weight: 600;
  color: #787b86;
  border-bottom: 1px solid #2a2e39;
  white-space: nowrap;
}
.light .data-table th {
  background: #f5f6fa;
  color: #666;
  border-bottom: 1px solid #e0e0e0;
}
.data-table th:first-child { text-align: left; }
.data-table td {
  padding: 10px 12px;
  text-align: right;
  border-bottom: 1px solid #1e2128;
  white-space: nowrap;
}
.light .data-table td { border-bottom: 1px solid #f0f0f0; }
.data-table tr:hover { background: #1e2128; }
.light .data-table tr:hover { background: #f9f9f9; }
.signal-row { background: rgba(239, 83, 80, 0.08); }
.light .signal-row { background: rgba(239, 83, 80, 0.05); }
.cell-name {
  text-align: left;
  cursor: pointer;
}
.cell-name:hover .cell-title { color: #2962ff; }
.cell-title {
  font-weight: 500;
  color: #d1d4dc;
}
.light .cell-title { color: #333; }
.cell-code {
  font-size: 11px;
  color: #787b86;
  margin-top: 2px;
}
.light .cell-code { color: #999; }
.cell-num { font-family: monospace; }
.cell-num.up { color: #ef5350; }
.cell-num.down { color: #26a69a; }
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.tag-clear {
  background: rgba(239, 83, 80, 0.2);
  color: #ef5350;
}
.tag-half {
  background: rgba(255, 152, 0, 0.15);
  color: #ff9800;
}
.tag-profit {
  background: rgba(38, 166, 154, 0.15);
  color: #26a69a;
}
.tag-hold {
  background: rgba(120, 123, 134, 0.15);
  color: #787b86;
}
.tag-unknown {
  background: rgba(120, 123, 134, 0.1);
  color: #555;
}
.breathing-tag {
  animation: breathe 1.5s ease-in-out infinite;
}
.breathing-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef5350;
  animation: breathe 1.5s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px rgba(239, 83, 80, 0.6); }
  50% { opacity: 0.4; box-shadow: 0 0 12px rgba(239, 83, 80, 0.9); }
}
.btn-remove {
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid #363a45;
  background: transparent;
  color: #787b86;
  cursor: pointer;
  font-size: 12px;
}
.light .btn-remove {
  border-color: #d0d0d0;
  color: #999;
}
.btn-remove:hover { color: #ef5350; border-color: #ef5350; }
.empty-cell {
  text-align: center;
  padding: 40px;
  color: #787b86;
}
.light .empty-cell { color: #999; }
</style>
