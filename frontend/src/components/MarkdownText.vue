<script setup lang="ts">
import MarkdownIt from 'markdown-it';
import { computed } from 'vue';

const props = defineProps<{ source: string }>();

// 模型文本不可信：html:false 让原始 HTML 一律转义，链接只放行 http(s)
const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
md.validateLink = (url) => /^https?:\/\//i.test(url.trim());
const renderLink = md.renderer.rules.link_open ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank');
  tokens[idx].attrSet('rel', 'noopener noreferrer');
  return renderLink(tokens, idx, options, env, self);
};

const html = computed(() => md.render(props.source));
</script>

<template>
  <div class="markdown" v-html="html" />
</template>

<style scoped>
.markdown { word-break: break-word; line-height: 1.6; }
.markdown :deep(h1), .markdown :deep(h2), .markdown :deep(h3) { font-size: 14px; margin: 12px 0 4px; }
.markdown :deep(ul), .markdown :deep(ol) { margin: 4px 0; padding-left: 20px; }
.markdown :deep(p) { margin: 4px 0; }
</style>
