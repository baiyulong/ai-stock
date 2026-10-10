<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { watchlist, removeFromWatchlist, addToWatchlist } from '@/stores/watchlist';
import { theme, toggleTheme } from '@/stores/theme';
import { fetchQuotes, formatVolume, formatAmount, type QuoteData } from '@/api';
import SearchBox from '@/components/SearchBox.vue';

const emit = defineEmits<{
  openChart: [code: string, name: string];
}>();

const quotes = ref<Map<string, QuoteData>>(new Map());
const showAddBar = ref(false);
let refreshTimer: ReturnType<typeof setInterval> | null = null;

async function refreshQuotes() {
  if (watchlist.value.length === 0) return;
  const codes = watchlist.value.map((s) => s.code);
  quotes.value = await fetchQuotes(codes);
}

function getQuote(code: string): QuoteData | undefined {
  return quotes.value.get(code);
}

function onOpenChart(code: string, name: string) {
  emit('openChart', code, name);
}

function onRemove(code: string, e: Event) {
  e.stopPropagation();
  removeFromWatchlist(code);
}

function onAddSelect(code: string, name: string) {
  addToWatchlist(code, name);
  showAddBar.value = false;
}

onMounted(() => {
  refreshQuotes();
  refreshTimer = setInterval(refreshQuotes, 5000);
});

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <div class="watchlist-view">
    <div class="wl-header">
      <div class="wl-title">自选股</div>
      <div class="wl-actions">
        <button class="btn-theme" @click="toggleTheme">
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
        <button class="btn-add" @click="showAddBar = !showAddBar">+ 添加自选</button>
      </div>
    </div>

    <div v-if="showAddBar" class="add-bar">
      <SearchBox placeholder="输入代码或名称添加自选" @select="onAddSelect" />
      <button class="btn-cancel" @click="showAddBar = false">取消</button>
    </div>

    <div class="wl-table-wrap">
      <table class="wl-table">
        <thead>
          <tr>
            <th class="col-name">名称/代码</th>
            <th class="col-num">最新价</th>
            <th class="col-num">涨跌额</th>
            <th class="col-num">涨跌幅</th>
            <th class="col-num">成交量</th>
            <th class="col-num">成交额</th>
            <th class="col-num">今开</th>
            <th class="col-num">最高</th>
            <th class="col-num">最低</th>
            <th class="col-num">内盘</th>
            <th class="col-num">外盘</th>
            <th class="col-op">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in watchlist"
            :key="item.code"
            class="wl-row"
          >
            <td class="col-name" @click="onOpenChart(item.code, item.name)">
              <div class="cell-name">{{ item.name }}</div>
              <div class="cell-code">{{ item.code }}</div>
            </td>
            <template v-if="getQuote(item.code)">
              <td class="col-num col-bold" :class="getQuote(item.code)!.up ? 'up' : 'down'">
                {{ getQuote(item.code)!.last.toFixed(getQuote(item.code)!.decimals) }}
              </td>
              <td class="col-num col-bold" :class="getQuote(item.code)!.up ? 'up' : 'down'">
                {{ getQuote(item.code)!.up ? '+' : '' }}{{ getQuote(item.code)!.change.toFixed(getQuote(item.code)!.decimals) }}
              </td>
              <td class="col-num col-bold" :class="getQuote(item.code)!.up ? 'up' : 'down'">
                {{ getQuote(item.code)!.up ? '+' : '' }}{{ getQuote(item.code)!.changePct.toFixed(2) }}%
              </td>
              <td class="col-num">{{ formatVolume(getQuote(item.code)!.volume) }}</td>
              <td class="col-num">{{ formatAmount(getQuote(item.code)!.amount) }}</td>
              <td class="col-num">{{ getQuote(item.code)!.open.toFixed(getQuote(item.code)!.decimals) }}</td>
              <td class="col-num">{{ getQuote(item.code)!.high.toFixed(getQuote(item.code)!.decimals) }}</td>
              <td class="col-num">{{ getQuote(item.code)!.low.toFixed(getQuote(item.code)!.decimals) }}</td>
              <td class="col-num">{{ getQuote(item.code)!.insideDish > 0 ? formatVolume(getQuote(item.code)!.insideDish) : '--' }}</td>
              <td class="col-num">{{ getQuote(item.code)!.outerDisc > 0 ? formatVolume(getQuote(item.code)!.outerDisc) : '--' }}</td>
            </template>
            <template v-else>
              <td class="col-num" colspan="10">--</td>
            </template>
            <td class="col-op">
              <button class="btn-remove" @click.stop="onRemove(item.code, $event)">×</button>
            </td>
          </tr>
          <tr v-if="watchlist.length === 0">
            <td colspan="12" class="wl-empty">暂无自选股，点击右上角添加</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.watchlist-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #131722;
}
.wl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  border-bottom: 1px solid #2a2e39;
}
.wl-title {
  font-size: 16px;
  font-weight: 600;
  color: #d1d4dc;
}
.wl-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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
.btn-add {
  padding: 6px 16px;
  background: #2962ff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.add-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 24px;
  border-bottom: 1px solid #2a2e39;
}
.btn-cancel {
  padding: 6px 12px;
  background: transparent;
  color: #787b86;
  border: 1px solid #363a45;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.wl-table-wrap {
  flex: 1;
  overflow: auto;
}
.wl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1100px;
}
.wl-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
}
.wl-table th {
  background: #1e222d;
  color: #787b86;
  font-weight: 500;
  padding: 10px 12px;
  text-align: right;
  border-bottom: 1px solid #2a2e39;
  white-space: nowrap;
}
.wl-table th.col-name {
  text-align: left;
  min-width: 120px;
}
.wl-table th.col-op {
  text-align: center;
  width: 50px;
}
.wl-table td {
  padding: 10px 12px;
  text-align: right;
  border-bottom: 1px solid #1e222d;
  white-space: nowrap;
  color: #d1d4dc;
}
.wl-table td.col-name {
  text-align: left;
  cursor: pointer;
}
.wl-table td.col-name:hover .cell-name {
  color: #2962ff;
}
.wl-table td.col-op {
  text-align: center;
}
.wl-row:hover {
  background: #1e222d;
}
.cell-name {
  font-size: 13px;
  font-weight: 500;
  color: #d1d4dc;
}
.cell-code {
  font-size: 11px;
  color: #787b86;
  margin-top: 2px;
}
.col-num.up { color: #ef5350; }
.col-num.down { color: #26a69a; }
.col-bold { font-weight: 600; font-size: 13px; }
.btn-remove {
  width: 22px;
  height: 22px;
  background: transparent;
  border: none;
  color: #787b86;
  font-size: 16px;
  cursor: pointer;
  border-radius: 3px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-remove:hover {
  background: #2a2e39;
  color: #ef5350;
}
.wl-empty {
  text-align: center;
  padding: 60px 20px;
  color: #787b86;
  font-size: 13px;
}
</style>
