<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { agentApi } from '../api';
import type { LlmSettings, LlmSettingsPatch } from '../api/types';
import { errorMessage } from '../errors';

const emit = defineEmits<{ close: [] }>();

const current = ref<LlmSettings | null>(null);
const model = ref('');
// key 只存在这个输入框和后端内存里，不写 localStorage，保存后立即清空
const apiKey = ref('');
const saving = ref(false);
const error = ref<string | null>(null);
const saved = ref(false);

onMounted(async () => {
  try {
    current.value = await agentApi.getLlmSettings();
    model.value = current.value.model;
  } catch (e) {
    error.value = errorMessage(e);
  }
});

async function save() {
  if (!current.value || saving.value) return;
  const patch: LlmSettingsPatch = {};
  if (apiKey.value.trim()) patch.api_key = apiKey.value.trim();
  if (model.value !== current.value.model) patch.model = model.value as LlmSettingsPatch['model'];
  if (!Object.keys(patch).length) return;
  saving.value = true;
  error.value = null;
  saved.value = false;
  try {
    current.value = await agentApi.patchLlmSettings(patch);
    model.value = current.value.model;
    apiKey.value = '';
    saved.value = true;
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="backdrop" @click.self="emit('close')">
    <form class="dialog panel" role="dialog" aria-label="模型设置" @submit.prevent="save">
      <div class="row">
        <h3>模型设置</h3>
        <span class="spacer" />
        <button type="button" aria-label="关闭" @click="emit('close')">关闭</button>
      </div>
      <div v-if="error" class="alert error" role="alert">{{ error }}</div>
      <template v-if="current">
        <p class="small" :class="current.configured ? 'alert ok' : 'alert warn'">
          {{ current.configured ? 'API key 已配置（只保存在本机后端内存，后端重启后需重新填写）' : '尚未配置 API key' }}
        </p>
        <label>
          <span>模型</span>
          <select v-model="model" name="model">
            <option v-if="!current.available_models.includes(current.model)" :value="current.model">
              {{ current.model }}（启动配置）
            </option>
            <option v-for="m in current.available_models" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <label>
          <span>DeepSeek API key{{ current.configured ? '（留空则保持不变）' : '' }}</span>
          <input v-model="apiKey" name="api_key" type="password" autocomplete="off" spellcheck="false" />
        </label>
        <p class="muted small">key 只发送到本机后端，不会显示、回传或写入磁盘。</p>
        <div v-if="saved" class="alert ok" role="status">已保存。</div>
        <div class="row">
          <span class="spacer" />
          <button class="primary" type="submit" :disabled="saving">保存</button>
        </div>
      </template>
      <p v-else-if="!error" class="muted">加载中…</p>
    </form>
  </div>
</template>

<style scoped>
.backdrop { position: fixed; inset: 0; background: rgb(0 0 0 / 25%); display: flex; align-items: center; justify-content: center; z-index: 10; }
.dialog { width: min(420px, calc(100% - 32px)); }
</style>
