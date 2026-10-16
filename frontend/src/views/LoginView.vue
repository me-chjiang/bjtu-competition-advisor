<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { misApi } from '../api';
import type { LoginForm, LoginStep, MisStatus } from '../api/types';
import DynamicForm from '../components/DynamicForm.vue';
import { errorMessage } from '../errors';
import { formatTime } from '../labels';

const router = useRouter();
const status = ref<MisStatus | null>(null);
const form = ref<LoginForm | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    status.value = await misApi.status();
  } catch (e) {
    error.value = errorMessage(e);
  }
});

// 离开页面时释放云端登录会话，避免继续计费
onBeforeUnmount(() => {
  if (form.value) misApi.cancelLogin(form.value.login_id).catch(() => {});
});

async function run(action: () => Promise<LoginStep>) {
  busy.value = true;
  error.value = null;
  try {
    handle(await action());
  } catch (e) {
    error.value = errorMessage(e);
    form.value = null;
  } finally {
    busy.value = false;
  }
}

function handle(step: LoginStep) {
  if (step.state === 'form') {
    form.value = step;
    return;
  }
  form.value = null;
  if (step.state === 'failed') error.value = step.error;
  else router.push('/wait');
}

const start = () => run(() => misApi.startLogin());
const submit = (values: Record<string, string>) => run(() => misApi.submitLogin(form.value!.login_id, values));
const refreshCaptcha = () => run(() => misApi.refreshCaptcha(form.value!.login_id));

async function cancel() {
  const id = form.value?.login_id;
  form.value = null;
  if (id) await misApi.cancelLogin(id).catch(() => {});
}
</script>

<template>
  <section class="centered panel">
    <h2>登录北交大 MIS</h2>
    <p class="muted small">
      由云浏览器打开 MIS 统一身份认证页面，下方表单和验证码均实时取自该页面。
      账号密码只用于本次登录，不会保存。
    </p>

    <div v-if="error" class="alert error" role="alert">{{ error }}</div>

    <DynamicForm v-if="form" :form="form" :busy="busy" @submit="submit" @refresh-captcha="refreshCaptcha" />
    <div v-if="form" class="row" style="margin-top: 8px">
      <button class="link" type="button" :disabled="busy" @click="cancel">取消登录</button>
    </div>

    <template v-else>
      <button class="primary" type="button" :disabled="busy" @click="start">
        {{ busy ? '正在打开云浏览器…' : '连接教务系统' }}
      </button>
      <div v-if="status?.crawl.state === 'done'" class="alert info">
        已有采集结果：竞赛项目 {{ status.crawl.counts?.cpitem }} 条、可报名轮次
        {{ status.crawl.counts?.signup_rounds }} 条（{{ formatTime(status.crawl.finished_at) }}）。
        <button class="link" type="button" @click="router.push('/advisor')">跳过登录，直接进入推荐</button>
      </div>
    </template>
  </section>
</template>
