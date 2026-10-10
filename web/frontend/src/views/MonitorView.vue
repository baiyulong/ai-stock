<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { runMonitor, getMonitorResults, addIgnore, addWatchBuy, type MonitorItem } from '@/api';

const monitorItems = ref<MonitorItem[]>([]);
const monitorLoading = ref(false);
const lastRunTime = ref('');
const urgencyFilter = ref<string>('all');
const newFormedOnly = ref(false);

// 计算第二个低点距今天数
function daysSinceLow(dateStr: string): number {
  if (!dateStr) return 999;
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

function isNewFormed(item: MonitorItem): boolean {
  const days = daysSinceLow(item.low_60_date || '');
  return days <= 20; // 第二个低点在20日内形成
}

// 排序
const sortKey = ref<string>('');
const sortDir = ref<'asc' | 'desc'>('desc');

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = 'desc';
  }
}

function sortIndicator(key: string): string {
  if (sortKey.value !== key) return '';
  return sortDir.value === 'asc' ? ' ▲' : ' ▼';
}

const filteredItems = computed(() => {
  let list = monitorItems.value;
  if (urgencyFilter.value === 'sell') list = list.filter(i => i.urgency >= 4);
  else if (urgencyFilter.value === 'reduce') list = list.filter(i => i.urgency === 3);
  else if (urgencyFilter.value === 'buy') list = list.filter(i => i.urgency === 2);
  else if (urgencyFilter.value === 'watch') list = list.filter(i => i.urgency === 1);
  else if (urgencyFilter.value === 'normal') list = list.filter(i => i.urgency === 0);

  if (newFormedOnly.value) {
    list = list.filter(i => isNewFormed(i));
  }

  if (sortKey.value) {
    const key = sortKey.value as keyof MonitorItem;
    list = [...list].sort((a, b) => {
      const va = Number(a[key]) || 0;
      const vb = Number(b[key]) || 0;
      return sortDir.value === 'asc' ? va - vb : vb - va;
    });
  }
  return list;
});

function setFilter(f: string) {
  urgencyFilter.value = urgencyFilter.value === f ? 'all' : f;
}

async function loadLastMonitor() {
  const data = await getMonitorResults();
  if (data && data.all && data.all.length > 0) {
    monitorItems.value = data.all;
    lastRunTime.value = data.time || '';
  }
}

async function handleRunMonitor() {
  monitorLoading.value = true;
  try {
    monitorItems.value = await runMonitor();
    lastRunTime.value = new Date().toLocaleString('zh-CN');
  } catch (e) {
    console.error('监控失败', e);
  } finally {
    monitorLoading.value = false;
  }
}

async function handleIgnore(item: MonitorItem) {
  const ok = await addIgnore(item.code, item.name, '手动忽略');
  if (ok) {
    monitorItems.value = monitorItems.value.filter(m => m.code !== item.code);
  }
}

async function handleAddWatchBuy(item: MonitorItem) {
  const ok = await addWatchBuy(item.code, item.name, item.B);
  if (ok) {
    // 视觉反馈
    const btn = document.querySelector(`[data-code="${item.code}"] .btn-watchbuy`);
    if (btn) {
      (btn as HTMLElement).textContent = '已添加';
      (btn as HTMLElement).style.color = '#26a69a';
      (btn as HTMLElement).style.borderColor = '#26a69a';
    }
  }
}

function urgencyLabel(u: number): string {
  if (u >= 4) return '清仓';
  if (u >= 3) return '减半';
  if (u >= 2) return '买入';
  if (u >= 1) return '关注';
  return '观察';
}

function urgencyClass(u: number): string {
  if (u >= 4) return 'urgency-sell';
  if (u >= 3) return 'urgency-reduce';
  if (u >= 2) return 'urgency-buy';
  if (u >= 1) return 'urgency-watch';
  return 'urgency-normal';
}

function handleDetail(code: string, name: string) {
  window.dispatchEvent(new CustomEvent('open-chart', { detail: { code, name } }));
}

onMounted(() => {
  loadLastMonitor();
});
</script>

<template>
  <div class="monitor-view">
    <div class="monitor-toolbar">
      <div class="toolbar-left">
        <button class="btn btn-monitor" :disabled="monitorLoading" @click="handleRunMonitor">
          {{ monitorLoading ? '监控中...' : '刷新监控' }}
        </button>
        <span v-if="lastRunTime" class="last-run">上次刷新: {{ lastRunTime }}</span>
      </div>
      <div class="toolbar-right">
        <span :class="['stat-badge', 'new-formed', { active: newFormedOnly }]" @click="newFormedOnly = !newFormedOnly">
          新形成 {{ monitorItems.filter(i => isNewFormed(i)).length }}
        </span>
        <span :class="['stat-badge', 'sell', { active: urgencyFilter === 'sell' }]" @click="setFilter('sell')">清仓 {{ monitorItems.filter(i => i.urgency >= 4).length }}</span>
        <span :class="['stat-badge', 'reduce', { active: urgencyFilter === 'reduce' }]" @click="setFilter('reduce')">减半 {{ monitorItems.filter(i => i.urgency === 3).length }}</span>
        <span :class="['stat-badge', 'buy', { active: urgencyFilter === 'buy' }]" @click="setFilter('buy')">买入 {{ monitorItems.filter(i => i.urgency === 2).length }}</span>
        <span :class="['stat-badge', 'watch', { active: urgencyFilter === 'watch' }]" @click="setFilter('watch')">关注 {{ monitorItems.filter(i => i.urgency === 1).length }}</span>
        <span :class="['stat-badge', 'normal', { active: urgencyFilter === 'normal' }]" @click="setFilter('normal')">观察 {{ monitorItems.filter(i => i.urgency === 0).length }}</span>
        <span :class="['stat-badge', 'all', { active: urgencyFilter === 'all' }]" @click="setFilter('all')">全部</span>
      </div>
    </div>

    <div class="monitor-table-wrap">
      <div v-if="filteredItems.length === 0 && !monitorLoading" class="monitor-empty">
        {{ urgencyFilter === 'all' ? '暂无监控数据，点击"刷新监控"开始' : '当前筛选条件下无股票' }}
      </div>
      <table v-else class="monitor-table">
        <thead>
          <tr>
            <th class="col-level">级别</th>
            <th class="col-name">名称/代码</th>
            <th class="col-num sortable" @click="toggleSort('current_price')">最新价{{ sortIndicator('current_price') }}</th>
            <th class="col-action">操作</th>
            <th class="col-num sortable" @click="toggleSort('B')">买入B{{ sortIndicator('B') }}</th>
            <th class="col-num sortable" @click="toggleSort('L1')">止损L1{{ sortIndicator('L1') }}</th>
            <th class="col-num sortable" @click="toggleSort('L2')">硬止L2{{ sortIndicator('L2') }}</th>
            <th class="col-num sortable" @click="toggleSort('T')">目标T{{ sortIndicator('T') }}</th>
            <th class="col-num sortable" @click="toggleSort('RR')">RR{{ sortIndicator('RR') }}</th>
            <th class="col-num sortable" @click="toggleSort('position_pct')">仓位{{ sortIndicator('position_pct') }}</th>
            <th class="col-signal">信号</th>
            <th class="col-op">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in filteredItems"
            :key="item.code"
            :data-code="item.code"
            :class="['monitor-row', urgencyClass(item.urgency)]"
          >
            <td class="col-level">
              <span :class="['urgency-badge', urgencyClass(item.urgency)]">{{ urgencyLabel(item.urgency) }}</span>
            </td>
            <td class="col-name" @click="handleDetail(item.code, item.name)">
              <div class="cell-name">{{ item.name }}</div>
              <div class="cell-code">{{ item.code }}</div>
              <div v-if="item.low_60_date" :class="['cell-lowdate', { 'new-formed': isNewFormed(item) }]">
                低点 {{ item.low_60_date }} ({{ daysSinceLow(item.low_60_date) }}天前)
              </div>
            </td>
            <td class="col-num cell-price">¥{{ item.current_price }}</td>
            <td class="col-action cell-action">{{ item.action }}</td>
            <td class="col-num">{{ item.B }}</td>
            <td class="col-num">{{ item.L1 }}</td>
            <td class="col-num">{{ item.L2 }}</td>
            <td class="col-num">{{ item.T }}</td>
            <td class="col-num" :class="{ 'rr-good': item.RR >= 2, 'rr-bad': item.RR < 2 && item.RR > 0 }">{{ item.RR }}</td>
            <td class="col-num">{{ item.shares }}股 / {{ item.position_pct }}%</td>
            <td class="col-signal cell-signal">
              <span v-for="(sig, i) in item.signals.slice(0, 2)" :key="i" class="sig-tag">{{ sig }}</span>
            </td>
            <td class="col-op">
              <div class="op-buttons">
                <button class="btn-watchbuy" @click.stop="handleAddWatchBuy(item)" title="加入待买列表">待买</button>
                <button class="btn-ignore" @click.stop="handleIgnore(item)" title="加入不监控列表">忽略</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.monitor-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.monitor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  background: var(--bg-primary, #131722);
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; align-items: center; gap: 12px; }
.toolbar-right { display: flex; gap: 6px; flex-wrap: wrap; }

.btn {
  padding: 6px 16px;
  border-radius: 4px;
  border: 1px solid var(--border-color, #2a2e39);
  background: var(--bg-secondary, #1e222d);
  color: var(--text-primary, #d1d4dc);
  cursor: pointer;
  font-size: 13px;
}
.btn:hover { background: var(--row-hover, #252a35); }
.btn-monitor { background: #26a69a; color: #fff; font-weight: 600; border-color: #26a69a; }
.btn-monitor:disabled { opacity: 0.6; cursor: not-allowed; }
.last-run { font-size: 12px; color: var(--text-secondary, #787b86); }

.stat-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.stat-badge:hover { opacity: 0.8; }
.stat-badge.active { outline: 2px solid currentColor; outline-offset: 1px; }
.stat-badge.sell { background: rgba(239,83,80,0.15); color: #ef5350; }
.stat-badge.reduce { background: rgba(242,153,74,0.15); color: #f2994a; }
.stat-badge.buy { background: rgba(41,98,255,0.15); color: #2962ff; }
.stat-badge.watch { background: rgba(38,166,154,0.15); color: #26a69a; }
.stat-badge.normal { background: rgba(120,123,134,0.15); color: #787b86; }
.stat-badge.all { background: rgba(209,212,220,0.1); color: var(--text-primary, #d1d4dc); }
.stat-badge.new-formed { background: rgba(38,166,154,0.15); color: #26a69a; }

.monitor-table-wrap { flex: 1; overflow: auto; }
.monitor-empty { text-align: center; padding: 60px 20px; color: var(--text-secondary, #787b86); font-size: 14px; }

.monitor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 1100px;
}
.monitor-table thead th {
  position: sticky;
  top: 0;
  background: var(--bg-secondary, #1e222d);
  color: var(--text-secondary, #787b86);
  font-weight: 600;
  font-size: 12px;
  padding: 10px 8px;
  text-align: right;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  z-index: 1;
}
.monitor-table thead th.col-level,
.monitor-table thead th.col-name,
.monitor-table thead th.col-action,
.monitor-table thead th.col-signal,
.monitor-table thead th.col-op { text-align: left; }

.monitor-table tbody td {
  padding: 8px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  text-align: right;
  vertical-align: middle;
  color: var(--text-primary, #d1d4dc);
}
.monitor-table tbody tr { cursor: pointer; transition: background 0.1s; }
.monitor-table tbody tr:hover { background: var(--row-hover, #252a35); }

.monitor-row.urgency-sell { border-left: 3px solid #ef5350; }
.monitor-row.urgency-reduce { border-left: 3px solid #f2994a; }
.monitor-row.urgency-buy { border-left: 3px solid #2962ff; }
.monitor-row.urgency-watch { border-left: 3px solid #26a69a; }
.monitor-row.urgency-normal { border-left: 3px solid transparent; }

.col-level { width: 60px; text-align: left; }
.col-name { width: 120px; text-align: left; }
.col-action { width: 80px; text-align: left; }
.col-signal { width: 200px; text-align: left; }
.col-op { width: 60px; text-align: left; }

.cell-name { font-weight: 600; font-size: 13px; cursor: pointer; }
.cell-name:hover { color: #2962ff; }
.cell-code { font-size: 11px; color: var(--text-secondary, #787b86); margin-top: 2px; }
.cell-lowdate {
  font-size: 10px;
  color: var(--text-secondary, #787b86);
  margin-top: 2px;
  opacity: 0.7;
}
.cell-lowdate.new-formed {
  color: #26a69a;
  opacity: 1;
  font-weight: 600;
}
.cell-price { font-weight: 700; font-size: 14px; }
.cell-action { font-weight: 600; font-size: 12px; color: #2962ff; }
.urgency-sell .cell-action { color: #ef5350; }
.urgency-reduce .cell-action { color: #f2994a; }
.cell-signal { font-size: 11px; }
.sig-tag { display: inline-block; margin-right: 6px; color: var(--text-secondary, #787b86); }
.rr-good { color: #26a69a; font-weight: 600; }
.rr-bad { color: #f2994a; }

.urgency-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  text-align: center;
}
.urgency-badge.urgency-sell { background: #ef5350; }
.urgency-badge.urgency-reduce { background: #f2994a; }
.urgency-badge.urgency-buy { background: #2962ff; }
.urgency-badge.urgency-watch { background: #26a69a; }
.urgency-badge.urgency-normal { background: #787b86; }

.btn-ignore {
  padding: 2px 8px;
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 3px;
  background: transparent;
  color: var(--text-secondary, #787b86);
  font-size: 11px;
  cursor: pointer;
}
.btn-ignore:hover { background: rgba(239,83,80,0.15); color: #ef5350; border-color: #ef5350; }

.btn-watchbuy {
  padding: 2px 8px;
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 3px;
  background: transparent;
  color: var(--text-secondary, #787b86);
  font-size: 11px;
  cursor: pointer;
  margin-right: 4px;
}
.btn-watchbuy:hover { background: rgba(41,98,255,0.15); color: #2962ff; border-color: #2962ff; }
.op-buttons { display: flex; gap: 4px; white-space: nowrap; }

.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--text-primary, #d1d4dc); }

/* 浅色主题适配 */
.light .monitor-view {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f6f8;
  --text-primary: #131722;
  --text-secondary: #787b86;
  --border-color: #e0e3eb;
  --row-hover: #f5f6f8;
}
</style>
