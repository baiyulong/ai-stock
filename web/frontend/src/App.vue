<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import WatchlistView from '@/views/WatchlistView.vue';
import ChartView from '@/views/ChartView.vue';
import ScreenerView from '@/views/ScreenerView.vue';
import MonitorView from '@/views/MonitorView.vue';
import IgnoreView from '@/views/IgnoreView.vue';
import WatchBuyView from '@/views/WatchBuyView.vue';
import PositionView from '@/views/PositionView.vue';
import SettingsView from '@/views/SettingsView.vue';
import { theme } from '@/stores/theme';
import { getAlerts, markAllAlertsRead, type AlertItem } from '@/api';

type View = 'watchlist' | 'chart' | 'screener' | 'monitor' | 'ignore' | 'watchbuy' | 'position' | 'settings';

const currentView = ref<View>('watchlist');
const previousView = ref<View>('watchlist');
const chartCode = ref('');
const chartName = ref('');

// 告警
const unreadCount = ref(0);
const showAlertPanel = ref(false);
const alerts = ref<AlertItem[]>([]);
let alertTimer: number | null = null;

async function refreshAlerts() {
  try {
    const data = await getAlerts(true, 20);
    unreadCount.value = data.unread_count;
    alerts.value = data.alerts;
  } catch {
    /* ignore */
  }
}

async function handleMarkAllRead() {
  await markAllAlertsRead();
  unreadCount.value = 0;
  alerts.value = [];
  showAlertPanel.value = false;
}

function openChart(code: string, name: string) {
  previousView.value = currentView.value;
  chartCode.value = code;
  chartName.value = name;
  currentView.value = 'chart';
}

function backFromChart() {
  currentView.value = previousView.value;
}

function switchView(view: View) {
  if (view === 'chart') return;
  currentView.value = view;
}

function onOpenChart(e: Event) {
  const detail = (e as CustomEvent).detail;
  if (detail?.code && detail?.name) {
    openChart(detail.code, detail.name);
  }
}

onMounted(() => {
  window.addEventListener('open-chart', onOpenChart);
  refreshAlerts();
  alertTimer = window.setInterval(refreshAlerts, 30000);
});

onUnmounted(() => {
  window.removeEventListener('open-chart', onOpenChart);
  if (alertTimer) clearInterval(alertTimer);
});
</script>

<template>
  <div :class="{ light: theme === 'light' }" class="app-root">
    <!-- 顶部导航（图表页隐藏） -->
    <div v-if="currentView !== 'chart'" class="app-nav">
      <button
        :class="['nav-btn', { active: currentView === 'watchlist' }]"
        @click="switchView('watchlist')"
      >自选</button>
      <button
        :class="['nav-btn', { active: currentView === 'screener' }]"
        @click="switchView('screener')"
      >选股</button>
      <button
        :class="['nav-btn', { active: currentView === 'monitor' }]"
        @click="switchView('monitor')"
      >监控</button>
      <button
        :class="['nav-btn', { active: currentView === 'ignore' }]"
        @click="switchView('ignore')"
      >忽略</button>
      <button
        :class="['nav-btn', { active: currentView === 'watchbuy' }]"
        @click="switchView('watchbuy')"
      >
        待买
        <span v-if="unreadCount > 0" class="nav-badge breathing-badge">{{ unreadCount }}</span>
      </button>
      <button
        :class="['nav-btn', { active: currentView === 'position' }]"
        @click="switchView('position')"
      >持仓</button>

      <!-- 告警铃铛 -->
      <div class="alert-wrapper">
        <button class="alert-bell" :class="{ 'has-alert': unreadCount > 0 }" @click="showAlertPanel = !showAlertPanel">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span v-if="unreadCount > 0" class="bell-count">{{ unreadCount }}</span>
        </button>
        <!-- 设置按钮 -->
        <button class="alert-bell settings-btn" :class="{ active: currentView === 'settings' }" @click="switchView('settings')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <!-- 告警面板 -->
        <div v-if="showAlertPanel" class="alert-panel">
          <div class="alert-panel-header">
            <span>交易提醒 ({{ unreadCount }} 未读)</span>
            <button v-if="unreadCount > 0" class="btn-read-all" @click="handleMarkAllRead">全部已读</button>
          </div>
          <div class="alert-list">
            <div v-if="alerts.length === 0" class="alert-empty">暂无未读提醒</div>
            <div v-for="alert in alerts" :key="alert.id" class="alert-item" :class="'alert-' + alert.alert_type">
              <div class="alert-title">{{ alert.title }}</div>
              <div class="alert-msg">{{ alert.message }}</div>
              <div class="alert-time">{{ alert.created_at }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="app-content">
      <WatchlistView v-if="currentView === 'watchlist'" @open-chart="openChart" />
      <ScreenerView v-else-if="currentView === 'screener'" @open-chart="openChart" />
      <MonitorView v-else-if="currentView === 'monitor'" @open-chart="openChart" />
      <IgnoreView v-else-if="currentView === 'ignore'" @open-chart="openChart" />
      <WatchBuyView v-else-if="currentView === 'watchbuy'" @open-chart="openChart" />
      <PositionView v-else-if="currentView === 'position'" @open-chart="openChart" />
      <SettingsView v-else-if="currentView === 'settings'" />
      <ChartView
        v-else
        :code="chartCode"
        :name="chartName"
        @back="backFromChart"
      />
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html, body, #app {
  height: 100%;
  overflow: hidden;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #131722;
  color: #d1d4dc;
}
.app-root {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.app-nav {
  display: flex;
  gap: 4px;
  padding: 8px 16px 0;
  background: #131722;
  border-bottom: 1px solid #2a2e39;
  align-items: center;
}
.light .app-nav {
  background: #ffffff;
  border-bottom-color: #e0e3eb;
}
.nav-btn {
  padding: 8px 20px;
  border: none;
  background: transparent;
  color: #787b86;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  position: relative;
}
.nav-btn.active {
  color: #2962ff;
  border-bottom-color: #2962ff;
}
.nav-btn:hover {
  color: #d1d4dc;
}
.light .nav-btn:hover {
  color: #131722;
}
.nav-badge {
  display: inline-block;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  padding: 0 5px;
  margin-left: 6px;
  border-radius: 9px;
  background: #ef5350;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  text-align: center;
  animation: badge-breathe 1.5s ease-in-out infinite;
}
@keyframes badge-breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.15); }
}
.alert-wrapper {
  margin-left: auto;
  position: relative;
}
.alert-bell {
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: #787b86;
  cursor: pointer;
  position: relative;
  border-radius: 6px;
}
.alert-bell:hover {
  background: #1e2128;
  color: #d1d4dc;
}
.settings-btn.active {
  color: #2962ff;
}
.light .alert-bell:hover {
  background: #f0f0f0;
  color: #333;
}
.alert-bell.has-alert {
  color: #ef5350;
  animation: bell-shake 2s ease-in-out infinite;
}
@keyframes bell-shake {
  0%, 90%, 100% { transform: rotate(0); }
  92% { transform: rotate(-10deg); }
  94% { transform: rotate(10deg); }
  96% { transform: rotate(-8deg); }
  98% { transform: rotate(8deg); }
}
.bell-count {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #ef5350;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  text-align: center;
}
.alert-panel {
  position: absolute;
  top: 100%;
  right: 0;
  width: 360px;
  max-height: 400px;
  background: #1e2128;
  border: 1px solid #2a2e39;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}
.light .alert-panel {
  background: #fff;
  border-color: #e0e0e0;
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
}
.alert-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #2a2e39;
  font-weight: 600;
  font-size: 14px;
}
.light .alert-panel-header { border-bottom-color: #e0e0e0; }
.btn-read-all {
  padding: 4px 10px;
  border: 1px solid #363a45;
  background: transparent;
  color: #787b86;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.light .btn-read-all {
  border-color: #d0d0d0;
  color: #666;
}
.btn-read-all:hover { color: #2962ff; border-color: #2962ff; }
.alert-list {
  overflow-y: auto;
  flex: 1;
}
.alert-empty {
  padding: 30px;
  text-align: center;
  color: #787b86;
  font-size: 13px;
}
.alert-item {
  padding: 12px 16px;
  border-bottom: 1px solid #131722;
}
.light .alert-item { border-bottom-color: #f0f0f0; }
.alert-item:last-child { border-bottom: none; }
.alert-buy { border-left: 3px solid #ef5350; }
.alert-sell { border-left: 3px solid #26a69a; }
.alert-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}
.alert-msg {
  font-size: 12px;
  color: #a0a3ab;
  line-height: 1.5;
}
.light .alert-msg { color: #666; }
.alert-time {
  font-size: 11px;
  color: #555;
  margin-top: 4px;
}
.app-content {
  flex: 1;
  overflow: hidden;
}
</style>
