/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MIS_API?: 'mock' | 'real';
  readonly VITE_AGENT_API?: 'mock' | 'real';
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
