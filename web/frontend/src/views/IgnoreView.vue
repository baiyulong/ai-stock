<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { listIgnore, addIgnore, removeIgnore, type IgnoreItem } from '@/api';

const ignoreItems = ref<IgnoreItem[]>([]);
const loading = ref(false);
const newCode = ref('');
const newName = ref('');

async function loadList() {
  loading.value = true;
  try {
    ignoreItems.value = await listIgnore();
  } finally {
    loading.value = false;
  }
}

async function handleAdd() {
  if (!newCode.value.trim()) return;
  const ok = await addIgnore(newCode.value.trim(), newName.value.trim(), '手动添加');
  if (ok) {
    newCode.value = '';
    newName.value = '';
    await loadList();
  }
}

async function handleRestore(code: string) {
  const ok = await removeIgnore(code);
  if (ok) {
    await loadList();
  }
}

function handleDetail(code: string, name: string) {
  window.dispatchEvent(new CustomEvent('open-chart', { detail: { code, name } }));
}

onMounted(() => {
  loadList();
});
</script>

<template>
  <div class="ignore-view">
    <div class="ignore-toolbar">
      <div class="toolbar-left">
        <span class="title">不监控股票列表（{{ ignoreItems.length }} 只）</span>
        <span class="hint">移除后，若仍符合选股条件，下次刷新监控将自动恢复</span>
      </div>
      <div class="toolbar-right">
        <input v-model="newCode" class="input-code" placeholder="股票代码" maxlength="6" @keyup.enter="handleAdd" />
        <input v-model="newName" class="input-name" placeholder="名称(可选)" @keyup.enter="handleAdd" />
        <button class="btn btn-add" @click="handleAdd">添加</button>
        <button class="btn btn-refresh" @click="loadList" :disabled="loading">刷新</button>
      </div>
    </div>

    <div class="ignore-table-wrap">
      <div v-if="ignoreItems.length === 0 && !loading" class="ignore-empty">
        暂无忽略股票
      </div>
      <table v-else class="ignore-table">
        <thead>
          <tr>
            <th class="col-name">名称/代码</th>
            <th class="col-time">加入时间</th>
            <th class="col-reason">原因</th>
            <th class="col-op">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in ignoreItems" :key="item.code" class="ignore-row">
            <td class="col-name cell-name" @click="handleDetail(item.code, item.name)">
              <div class="cell-name-text">{{ item.name || '--' }}</div>
              <div class="cell-code">{{ item.code }}</div>
            </td>
            <td class="col-time cell-time">{{ item.added_at }}</td>
            <td class="col-reason cell-reason">{{ item.reason || '--' }}</td>
            <td class="col-op">
              <button class="btn-restore" @click="handleRestore(item.code)">恢复监控</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ignore-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.ignore-toolbar {
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
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.title { font-weight: 600; font-size: 14px; }
.hint { font-size: 11px; color: var(--text-secondary, #787b86); }

.input-code, .input-name {
  padding: 5px 8px;
  border: 1px solid var(--border-color, #2a2e39);
  border-radius: 4px;
  background: var(--bg-secondary, #1e222d);
  color: var(--text-primary, #d1d4dc);
  font-size: 13px;
}
.input-code { width: 80px; }
.input-name { width: 100px; }

.btn {
  padding: 5px 14px;
  border-radius: 4px;
  border: 1px solid var(--border-color, #2a2e39);
  background: var(--bg-secondary, #1e222d);
  color: var(--text-primary, #d1d4dc);
  cursor: pointer;
  font-size: 13px;
}
.btn:hover { background: var(--row-hover, #252a35); }
.btn-add { background: #2962ff; color: #fff; border-color: #2962ff; font-weight: 600; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.ignore-table-wrap { flex: 1; overflow: auto; }
.ignore-empty { text-align: center; padding: 60px 20px; color: var(--text-secondary, #787b86); font-size: 14px; }

.ignore-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.ignore-table thead th {
  position: sticky;
  top: 0;
  background: var(--bg-secondary, #1e222d);
  color: var(--text-secondary, #787b86);
  font-weight: 600;
  font-size: 12px;
  padding: 10px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  z-index: 1;
}
.ignore-table tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color, #2a2e39);
  color: var(--text-primary, #d1d4dc);
}
.ignore-table tbody tr:hover { background: var(--row-hover, #252a35); }

.cell-name { font-weight: 600; cursor: pointer; }
.cell-name:hover { color: #2962ff; }
.cell-name-text { font-size: 13px; }
.cell-code { font-family: monospace; color: var(--text-secondary, #787b86); font-size: 11px; margin-top: 2px; }
.cell-time { color: var(--text-secondary, #787b86); font-size: 12px; }
.cell-reason { color: var(--text-secondary, #787b86); font-size: 12px; }

.btn-restore {
  padding: 3px 12px;
  border: 1px solid #26a69a;
  border-radius: 3px;
  background: transparent;
  color: #26a69a;
  font-size: 12px;
  cursor: pointer;
}
.btn-restore:hover { background: rgba(38,166,154,0.15); }

/* 浅色主题适配 */
.light .ignore-view {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f6f8;
  --text-primary: #131722;
  --text-secondary: #787b86;
  --border-color: #e0e3eb;
  --row-hover: #f5f6f8;
}
</style>
