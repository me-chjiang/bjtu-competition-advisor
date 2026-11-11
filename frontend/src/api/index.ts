import { realAgentApi, realMisApi } from './client';
import { mockAgentApi } from './mock/agent';
import { mockMisApi } from './mock/mis';
import type { AgentApi, MisApi } from './types';

export const apiModes = {
  mis: import.meta.env.VITE_MIS_API === 'real' ? 'real' : 'mock',
  agent: import.meta.env.VITE_AGENT_API === 'real' ? 'real' : 'mock',
} as const;

export const misApi: MisApi = apiModes.mis === 'real' ? realMisApi : mockMisApi;
export const agentApi: AgentApi = apiModes.agent === 'real' ? realAgentApi : mockAgentApi;
