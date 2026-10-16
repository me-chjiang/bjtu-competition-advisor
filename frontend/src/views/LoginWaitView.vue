<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { misApi } from '../api';
import type { CrawlStatus } from '../api/types';
import { errorMessage } from '../errors';
import { formatTime } from '../labels';

const POLL_MS = 1500;

const router = useRouter();
const crawl = ref<CrawlStatus | null>(null);
const error = ref<string | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

async function poll() {
  try {
    crawl.value = await misApi.crawlStatus();
  } catch (e) {
    error.value = errorMessage(e);
    return;
  }
  if (crawl.value.state === 'running') timer = setTimeout(poll, POLL_MS);
}

async function startCrawl() {
  error.value = null;
  try {
    crawl.value = await misApi.startCrawl();
    timer = setTimeout(poll, POLL_MS);
  } catch (e) {
    error.value = errorMessage(e);
  }
}

onMounted(async () => {
  try {
    crawl.value = (await misApi.status()).crawl;
  } catch (e) {
    error.value = errorMessage(e);
    return;
  }
  if (crawl.value.state === 'running') poll();
  else if (crawl.value.state === 'idle') startCrawl();
});

onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <section class="centered panel">
    <h2>采集竞赛列表</h2>
    <p class="muted small">已登录 MIS。云浏览器正在低频读取「竞赛项目」和「可报名轮次」两个列表，不会进行报名等操作。</p>

    <div v-if="error" class="alert error" role="alert">{{ error }}</div>

    <template v-if="crawl">
      <div v-if="crawl.state === 'running'" class="alert info">
        <span class="spinner" aria-hidden="true" /> 正在采集：{{ crawl.step ?? '准备中' }}
      </div>

      <div v-else-if="crawl.state === 'error'" class="alert error">采集失败：{{ crawl.error }}</div>

      <div v-else-if="crawl.state === 'done'" class="alert ok">
        采集完成：竞赛项目 {{ crawl.counts?.cpitem }} 条，可报名轮次 {{ crawl.counts?.signup_rounds }} 条
        （{{ formatTime(crawl.finished_at) }}）。
      </div>

      <div class="row">
        <button v-if="crawl.state !== 'running'" type="button" @click="startCrawl">
          {{ crawl.state === 'done' ? '重新采集' : '重试' }}
        </button>
        <span class="spacer" />
        <button class="primary" type="button" :disabled="crawl.state !== 'done'" @click="router.push('/advisor')">
          进入推荐
        </button>
      </div>
    </template>
    <p v-else-if="!error" class="muted">读取状态中…</p>
  </section>
</template>

<style scoped>
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: -2px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
