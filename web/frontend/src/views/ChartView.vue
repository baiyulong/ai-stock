<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { Vela } from '@luxalgo/vela';
import { AShareProvider } from '@/providers/ashare';
import { theme, toggleTheme } from '@/stores/theme';
import { isInWatchlist, addToWatchlist, removeFromWatchlist } from '@/stores/watchlist';
import { fetchStockQuote, fetchIndexQuote, type QuoteData } from '@/api';
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

  // 注册 A 股数据 provider
  const provider = new AShareProvider();
  chartRef.value.data.registerProvider('ashare', provider);

  // 添加成交量副图
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
  // 延迟切换，等回到自选列表后再打开新图表
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent('open-chart', { detail: { code, name } }));
  }, 50);
}

// 主题切换时重建图表
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
  <div class="chart-view">
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
      <button class="btn-star" :class="{ active: inWatchlist }" @click="toggleWatch">
        {{ inWatchlist ? '★' : '☆' }}
      </button>
      <button class="btn-theme" @click="toggleTheme">
        {{ theme === 'dark' ? '☀' : '☾' }}
      </button>
    </div>

    <QuoteBar :quote="quote" :name="name" />

    <div ref="chartContainer" class="chart-container"></div>
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
.chart-container {
  flex: 1;
  min-height: 0;
}
</style>
