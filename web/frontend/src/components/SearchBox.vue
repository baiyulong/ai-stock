<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { searchStocks, type SearchResult } from '@/api';

const props = defineProps<{
  placeholder?: string;
}>();

const emit = defineEmits<{
  select: [code: string, name: string];
}>();

const keyword = ref('');
const results = ref<SearchResult[]>([]);
const showDropdown = ref(false);
const inputRef = ref<HTMLInputElement | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | null = null;

function onInput() {
  if (searchTimer) clearTimeout(searchTimer);
  const kw = keyword.value.trim();
  if (!kw) {
    results.value = [];
    showDropdown.value = false;
    return;
  }
  searchTimer = setTimeout(async () => {
    results.value = await searchStocks(kw);
    showDropdown.value = results.value.length > 0;
  }, 200);
}

function onSelect(item: SearchResult) {
  emit('select', item.code, item.name);
  keyword.value = '';
  results.value = [];
  showDropdown.value = false;
}

function onBlur() {
  setTimeout(() => {
    showDropdown.value = false;
  }, 150);
}

function onFocus() {
  if (results.value.length > 0) showDropdown.value = true;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    showDropdown.value = false;
    inputRef.value?.blur();
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <div class="search-box">
    <input
      ref="inputRef"
      v-model="keyword"
      type="text"
      :placeholder="placeholder || '输入代码或名称，如 600519 / 茅台'"
      class="search-input"
      @input="onInput"
      @blur="onBlur"
      @focus="onFocus"
    />
    <div v-if="showDropdown" class="search-dropdown">
      <div
        v-for="item in results"
        :key="item.code"
        class="search-item"
        @mousedown.prevent="onSelect(item)"
      >
        <span class="si-name">
          {{ item.name }}
          <span v-if="item.tag" class="si-tag">{{ item.tag }}</span>
        </span>
        <span class="si-code">{{ item.code }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-box {
  position: relative;
  width: 280px;
}
.search-input {
  width: 100%;
  padding: 6px 12px;
  background: #2a2e39;
  border: 1px solid #363a45;
  border-radius: 4px;
  color: #d1d4dc;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}
.search-input:focus {
  border-color: #2962ff;
}
.search-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #1e222d;
  border: 1px solid #363a45;
  border-radius: 4px;
  margin-top: 4px;
  max-height: 300px;
  overflow-y: auto;
  z-index: 1000;
}
.search-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
}
.search-item:hover {
  background: #2a2e39;
}
.si-name {
  color: #d1d4dc;
  font-size: 12px;
}
.si-code {
  color: #787b86;
  font-size: 11px;
  font-family: monospace;
}
.si-tag {
  display: inline-block;
  background: #ff9800;
  color: #fff;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 6px;
  vertical-align: middle;
}
</style>
