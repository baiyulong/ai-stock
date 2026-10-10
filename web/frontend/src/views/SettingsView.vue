<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { theme } from '@/stores/theme';

const webhookUrl = ref('');
const webhookEnabled = ref(true);
const timezone = ref('Asia/Shanghai');
const serverTime = ref('');
const saving = ref(false);
const testing = ref(false);
const testResult = ref('');
const saveResult = ref('');
const tzSaveResult = ref('');

const timezoneOptions = [
  { value: 'Asia/Shanghai', label: '中国标准时间 (UTC+8) 北京/上海' },
  { value: 'Asia/Hong_Kong', label: '香港时间 (UTC+8)' },
  { value: 'Asia/Tokyo', label: '日本时间 (UTC+9) 东京' },
  { value: 'Asia/Singapore', label: '新加坡时间 (UTC+8)' },
  { value: 'UTC', label: '协调世界时 (UTC+0)' },
  { value: 'America/New_York', label: '美国东部时间 (UTC-5/-4) 纽约' },
  { value: 'America/Los_Angeles', label: '美国太平洋时间 (UTC-8/-7) 洛杉矶' },
  { value: 'Europe/London', label: '英国时间 (UTC+0/+1) 伦敦' },
];

async function loadConfig() {
  try {
    const resp = await fetch('/api/screener/webhook');
    const json = await resp.json();
    if (json.code === 0) {
      webhookUrl.value = json.data.url || '';
      webhookEnabled.value = json.data.enabled;
    }
  } catch {
    /* ignore */
  }
  try {
    const resp = await fetch('/api/screener/timezone');
    const json = await resp.json();
    if (json.code === 0) {
      timezone.value = json.data.timezone || 'Asia/Shanghai';
      serverTime.value = json.data.server_time || '';
    }
  } catch {
    /* ignore */
  }
}

async function saveTimezone() {
  try {
    const resp = await fetch('/api/screener/timezone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timezone: timezone.value }),
    });
    const json = await resp.json();
    if (json.code === 0) {
      tzSaveResult.value = '时区已保存';
      serverTime.value = new Date().toLocaleString('zh-CN');
    } else {
      tzSaveResult.value = '保存失败';
    }
  } catch {
    tzSaveResult.value = '保存失败';
  }
  setTimeout(() => { tzSaveResult.value = ''; }, 3000);
}

async function saveConfig() {
  saving.value = true;
  saveResult.value = '';
  try {
    const resp = await fetch('/api/screener/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: webhookUrl.value, enabled: webhookEnabled.value }),
    });
    const json = await resp.json();
    if (json.code === 0) {
      saveResult.value = '保存成功';
    } else {
      saveResult.value = '保存失败: ' + json.message;
    }
  } catch (e) {
    saveResult.value = '保存失败';
  } finally {
    saving.value = false;
    setTimeout(() => { saveResult.value = ''; }, 3000);
  }
}

async function testWebhook() {
  testing.value = true;
  testResult.value = '';
  try {
    const resp = await fetch('/api/screener/webhook/test', { method: 'POST' });
    const json = await resp.json();
    if (json.code === 0) {
      testResult.value = '测试消息已发送，请查看企业微信';
    } else {
      testResult.value = '测试失败: ' + json.message;
    }
  } catch {
    testResult.value = '测试失败，请检查网络';
  } finally {
    testing.value = false;
  }
}

onMounted(() => {
  loadConfig();
});
</script>

<template>
  <div class="settings-view" :class="{ light: theme === 'light' }">
    <div class="page-header">
      <h2 class="page-title">系统设置</h2>
    </div>

    <div class="settings-section">
      <h3 class="section-title">消息推送 (Webhook)</h3>
      <p class="section-desc">
        配置后，买入/卖出信号将自动推送到企业微信群。支持企业微信机器人、钉钉、Server酱等格式。
      </p>

      <div class="form-group">
        <label class="form-label">Webhook 地址</label>
        <input
          v-model="webhookUrl"
          type="text"
          class="form-input"
          placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        />
        <div class="form-hint">
          企业微信：群设置 → 群机器人 → 添加 → 复制 Webhook 地址
        </div>
      </div>

      <div class="form-group form-group-inline">
        <label class="form-label">启用推送</label>
        <label class="switch">
          <input type="checkbox" v-model="webhookEnabled" />
          <span class="slider"></span>
        </label>
      </div>

      <div class="form-actions">
        <button class="btn-primary" :disabled="saving" @click="saveConfig">
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
        <button class="btn-secondary" :disabled="testing || !webhookUrl" @click="testWebhook">
          {{ testing ? '测试中...' : '发送测试消息' }}
        </button>
      </div>

      <div v-if="saveResult" class="result-msg success">{{ saveResult }}</div>
      <div v-if="testResult" :class="['result-msg', testResult.includes('失败') ? 'error' : 'success']">
        {{ testResult }}
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">时区设置</h3>
      <p class="section-desc">
        所有时间显示和定时任务基于此时区。A 股交易使用中国标准时间 (UTC+8)。
      </p>
      <div class="form-group">
        <label class="form-label">时区</label>
        <select v-model="timezone" class="form-select" @change="saveTimezone">
          <option v-for="opt in timezoneOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">服务器当前时间</label>
        <div class="server-time">{{ serverTime || '加载中...' }}</div>
      </div>
      <div v-if="tzSaveResult" class="result-msg success">{{ tzSaveResult }}</div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">自动监控</h3>
      <div class="info-list">
        <div class="info-item">
          <span class="info-label">交易时段监控</span>
          <span class="info-value">每 5 分钟自动检查待买/持仓</span>
        </div>
        <div class="info-item">
          <span class="info-label">监控时段</span>
          <span class="info-value">9:30-11:30 / 13:00-15:00（周一至周五）</span>
        </div>
        <div class="info-item">
          <span class="info-label">收盘任务</span>
          <span class="info-value">15:30 自动同步数据 + 选股 + 证伪检查</span>
        </div>
        <div class="info-item">
          <span class="info-label">页面刷新</span>
          <span class="info-value">待买/持仓页每 60 秒自动刷新</span>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">策略参数</h3>
      <div class="info-list">
        <div class="info-item">
          <span class="info-label">入池条件</span>
          <span class="info-value">近60日低>前40日低 + 20日内创60日新高 + 百日振幅≥25% + 日均额>2亿 + 非ST</span>
        </div>
        <div class="info-item">
          <span class="info-label">买入条件</span>
          <span class="info-value">现价 ≤ B(买入价) 且 RR ≥ 2.0</span>
        </div>
        <div class="info-item">
          <span class="info-label">止损条件</span>
          <span class="info-value">跌破 L1=B×0.92 减半 / 跌破 L2=A×0.97 清仓</span>
        </div>
        <div class="info-item">
          <span class="info-label">止盈条件</span>
          <span class="info-value">达到 T=H×1.03 止盈</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-view {
  padding: 16px 20px;
  color: #d1d4dc;
  max-width: 800px;
}
.settings-view.light {
  color: #1a1a2e;
  background: #f5f6fa;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}
.settings-section {
  background: #1e2128;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}
.light .settings-section {
  background: #fff;
  border: 1px solid #e0e0e0;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 8px;
  color: #d1d4dc;
}
.light .section-title { color: #333; }
.section-desc {
  font-size: 12px;
  color: #787b86;
  margin: 0 0 16px;
  line-height: 1.5;
}
.light .section-desc { color: #888; }
.form-group {
  margin-bottom: 16px;
}
.form-group-inline {
  display: flex;
  align-items: center;
  gap: 12px;
}
.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
  color: #a0a3ab;
}
.light .form-label { color: #555; }
.form-group-inline .form-label {
  margin-bottom: 0;
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #363a45;
  background: #131722;
  color: #d1d4dc;
  font-size: 13px;
  font-family: monospace;
}
.light .form-input {
  background: #f9f9f9;
  border-color: #d0d0d0;
  color: #333;
}
.form-hint {
  font-size: 11px;
  color: #555;
  margin-top: 4px;
}
.light .form-hint { color: #999; }
.form-select {
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #363a45;
  background: #131722;
  color: #d1d4dc;
  font-size: 13px;
  cursor: pointer;
}
.light .form-select {
  background: #f9f9f9;
  border-color: #d0d0d0;
  color: #333;
}
.server-time {
  font-size: 14px;
  font-family: monospace;
  color: #26a69a;
  font-weight: 600;
}
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #363a45;
  border-radius: 24px;
  transition: 0.3s;
}
.slider:before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: #787b86;
  border-radius: 50%;
  transition: 0.3s;
}
.switch input:checked + .slider {
  background: #2962ff;
}
.switch input:checked + .slider:before {
  transform: translateX(20px);
  background: #fff;
}
.form-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
.btn-primary {
  padding: 8px 20px;
  border-radius: 6px;
  border: none;
  background: #2962ff;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}
.btn-primary:hover { background: #1e53e0; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  padding: 8px 20px;
  border-radius: 6px;
  border: 1px solid #363a45;
  background: transparent;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 13px;
}
.light .btn-secondary {
  border-color: #d0d0d0;
  color: #555;
}
.btn-secondary:hover { background: #2a2e39; }
.light .btn-secondary:hover { background: #f0f0f0; }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.result-msg {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.result-msg.success {
  background: rgba(38, 166, 154, 0.15);
  color: #26a69a;
}
.result-msg.error {
  background: rgba(239, 83, 80, 0.15);
  color: #ef5350;
}
.info-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.info-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px solid #2a2e39;
}
.light .info-item { border-bottom-color: #f0f0f0; }
.info-item:last-child { border-bottom: none; }
.info-label {
  font-size: 13px;
  color: #787b86;
  white-space: nowrap;
  min-width: 100px;
}
.light .info-label { color: #888; }
.info-value {
  font-size: 13px;
  color: #d1d4dc;
  text-align: right;
  line-height: 1.5;
}
.light .info-value { color: #333; }
</style>
