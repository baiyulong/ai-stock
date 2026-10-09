<script setup lang="ts">
import { computed } from 'vue';
import type { QuoteData } from '@/constants';
import { formatVolume } from '@/api';

const props = defineProps<{
  quote: QuoteData | null;
  name: string;
}>();

const decimals = computed(() => props.quote?.decimals ?? 2);
</script>

<template>
  <div v-if="quote" class="quote-bar">
    <span class="q-name">{{ name }}</span>
    <span class="q-code">{{ quote.code }}</span>
    <span class="q-price" :class="quote.up ? 'up' : 'down'">
      {{ quote.last.toFixed(decimals) }}
    </span>
    <span class="q-change" :class="quote.up ? 'up' : 'down'">
      {{ quote.up ? '+' : '' }}{{ quote.change.toFixed(decimals) }}
    </span>
    <span class="q-change-pct" :class="quote.up ? 'up' : 'down'">
      {{ quote.up ? '+' : '' }}{{ quote.changePct.toFixed(2) }}%
    </span>
    <span class="q-meta">开 {{ quote.open.toFixed(decimals) }}</span>
    <span class="q-meta">高 {{ quote.high.toFixed(decimals) }}</span>
    <span class="q-meta">低 {{ quote.low.toFixed(decimals) }}</span>
    <span class="q-meta">量 {{ formatVolume(quote.volume) }}</span>
  </div>
</template>

<style scoped>
.quote-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 16px;
  background: #1e222d;
  border-bottom: 1px solid #2a2e39;
  font-size: 12px;
}
.q-name {
  font-weight: 600;
  color: #d1d4dc;
  font-size: 14px;
}
.q-code {
  color: #787b86;
  font-family: monospace;
}
.q-price {
  font-size: 16px;
  font-weight: 700;
}
.q-price.up, .q-change.up, .q-change-pct.up {
  color: #ef5350;
}
.q-price.down, .q-change.down, .q-change-pct.down {
  color: #26a69a;
}
.q-change, .q-change-pct {
  font-weight: 600;
}
.q-meta {
  color: #787b86;
}
</style>
