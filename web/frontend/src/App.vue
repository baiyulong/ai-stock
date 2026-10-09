<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import WatchlistView from '@/views/WatchlistView.vue';
import ChartView from '@/views/ChartView.vue';
import { theme } from '@/stores/theme';

type View = 'watchlist' | 'chart';

const currentView = ref<View>('watchlist');
const chartCode = ref('');
const chartName = ref('');

function openChart(code: string, name: string) {
  chartCode.value = code;
  chartName.value = name;
  currentView.value = 'chart';
}

function backToWatchlist() {
  currentView.value = 'watchlist';
}

function onOpenChart(e: Event) {
  const detail = (e as CustomEvent).detail;
  if (detail?.code && detail?.name) {
    openChart(detail.code, detail.name);
  }
}

onMounted(() => {
  window.addEventListener('open-chart', onOpenChart);
});

onUnmounted(() => {
  window.removeEventListener('open-chart', onOpenChart);
});
</script>

<template>
  <div :class="{ light: theme === 'light' }" class="app-root">
    <WatchlistView v-if="currentView === 'watchlist'" @open-chart="openChart" />
    <ChartView
      v-else
      :code="chartCode"
      :name="chartName"
      @back="backToWatchlist"
    />
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
}
</style>
