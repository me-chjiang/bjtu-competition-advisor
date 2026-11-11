<script setup lang="ts">
import { reactive, watch } from 'vue';
import type { LoginForm } from '../api/types';

const props = defineProps<{ form: LoginForm; busy: boolean }>();
const emit = defineEmits<{ submit: [values: Record<string, string>]; refreshCaptcha: [] }>();

const values = reactive<Record<string, string>>({});

// 新表单（含失败后的新验证码）到达时只保留用户名类文本，清掉密码和验证码
watch(
  () => props.form,
  (form) => {
    for (const key of Object.keys(values)) {
      if (!form.fields.some((f) => f.name === key && f.kind === 'text')) delete values[key];
    }
    for (const f of form.fields) values[f.name] ??= '';
  },
  { immediate: true },
);

function onSubmit() {
  emit('submit', { ...values });
}
</script>

<template>
  <form class="dynamic-form" @submit.prevent="onSubmit">
    <div v-if="form.error" class="alert error" role="alert">登录失败：{{ form.error }}</div>
    <div v-for="field in form.fields" :key="field.name" class="field">
      <label :for="`login-${field.name}`">{{ field.label }}</label>
      <div v-if="field.kind === 'captcha'" class="row captcha-row">
        <img v-if="form.captcha" :src="form.captcha" alt="验证码" class="captcha" />
        <span v-else class="muted small">未能获取验证码图片</span>
        <button type="button" :disabled="busy" @click="emit('refreshCaptcha')">换一张</button>
      </div>
      <input
        :id="`login-${field.name}`"
        v-model="values[field.name]"
        :name="field.name"
        :type="field.kind === 'password' ? 'password' : 'text'"
        :autocomplete="field.kind === 'password' ? 'current-password' : field.kind === 'captcha' ? 'off' : 'username'"
        :disabled="busy"
        required
      />
    </div>
    <p class="muted small">剩余尝试次数：{{ form.attempts_left }}。失败不会自动重试，连续出错可能导致账号被锁定。</p>
    <button class="primary" type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
  </form>
</template>

<style scoped>
.field { margin-bottom: 10px; }
.field > label { color: var(--muted); margin-bottom: 4px; }
.captcha-row { margin-bottom: 6px; }
.captcha { height: 40px; border: 1px solid var(--border); border-radius: 4px; background: #fff; }
</style>
