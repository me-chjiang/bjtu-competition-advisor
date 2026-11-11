<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import type { Message } from '../api/types';

const props = defineProps<{
  messages: Message[];
  busy: boolean;
  pending: string | null;
  canConfirm: boolean;
  confirmDisabledReason: string | null;
  canGenerate: boolean;
}>();
const emit = defineEmits<{ send: [content: string]; confirm: []; generate: [] }>();

const draft = ref('');
const sent = ref<string | null>(null);
const list = ref<HTMLElement | null>(null);

// 发送失败时保留输入，等消息真正进入快照后才清空
watch(
  () => props.messages.length,
  async () => {
    if (sent.value !== null && draft.value.trim() === sent.value) draft.value = '';
    sent.value = null;
    await nextTick();
    if (list.value) list.value.scrollTop = list.value.scrollHeight;
  },
);

function send() {
  const content = draft.value.trim();
  if (!content || props.busy) return;
  sent.value = content;
  emit('send', content);
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
}
</script>

<template>
  <div class="chat panel">
    <div ref="list" class="messages">
      <div v-for="m in messages" :key="m.id" :class="['msg', m.role]">{{ m.content }}</div>
      <div v-if="busy && pending" class="msg user">{{ pending }}</div>
      <div v-if="busy" class="msg assistant muted">思考中…</div>
    </div>
    <div v-if="canConfirm || canGenerate" class="action-bar">
      <span v-if="confirmDisabledReason" class="muted small">{{ confirmDisabledReason }}</span>
      <button v-if="canGenerate" class="primary" type="button" data-action="generate" :disabled="busy" @click="emit('generate')">
        生成本阶段结果
      </button>
      <button
        v-if="canConfirm"
        class="primary"
        type="button"
        data-action="confirm"
        :disabled="busy || confirmDisabledReason !== null"
        @click="emit('confirm')"
      >
        确认本阶段
      </button>
    </div>
    <div class="composer">
      <textarea
        v-model="draft"
        rows="3"
        maxlength="4000"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="busy"
        @keydown="onKeydown"
      />
      <button type="button" :disabled="busy || !draft.trim()" @click="send">发送</button>
    </div>
  </div>
</template>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 0; }
.messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 8px; }
.msg { max-width: 85%; padding: 8px 12px; border-radius: 10px; white-space: pre-wrap; line-height: 1.5; }
.msg.assistant { background: #eef1f5; align-self: flex-start; }
.msg.user { background: var(--primary-weak); align-self: flex-end; }
.action-bar { display: flex; gap: 8px; justify-content: flex-end; align-items: center; padding: 8px 14px; border-top: 1px solid var(--border); }
.composer { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--border); align-items: flex-end; }
.composer textarea { resize: vertical; }
.composer button { flex-shrink: 0; white-space: nowrap; }
</style>
