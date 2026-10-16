<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import type { Message } from '../api/types';

const props = defineProps<{
  messages: Message[];
  busy: boolean;
  confirmLabel: string | null;
  confirmDisabled: boolean;
}>();
const emit = defineEmits<{ send: [content: string]; confirm: [] }>();

const draft = ref('');
const list = ref<HTMLElement | null>(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    list.value?.scrollTo({ top: list.value.scrollHeight });
  },
);

function send() {
  const content = draft.value.trim();
  if (!content || props.busy) return;
  emit('send', content);
  draft.value = '';
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
      <div v-if="busy" class="msg assistant muted">思考中…</div>
    </div>
    <div v-if="confirmLabel" class="confirm-bar">
      <button class="primary" type="button" :disabled="busy || confirmDisabled" @click="emit('confirm')">
        {{ confirmLabel }}
      </button>
    </div>
    <div class="composer">
      <textarea
        v-model="draft"
        rows="3"
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
.confirm-bar { padding: 8px 14px; border-top: 1px solid var(--border); text-align: right; }
.composer { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--border); align-items: flex-end; }
.composer textarea { resize: vertical; }
.composer button { flex-shrink: 0; white-space: nowrap; }
</style>
