/**
 * API Client for Patent Multi-Agent System
 */

import type { AgentConfig, AgentEvent, AgentTool, AgentSkill, AgentTimer, AgentMemory, OrgNode, DirEntry, BrowseDirResponse, FileContentResponse, SystemConfigResponse, SystemConfigUpdateRequest, EnvInfoResponse, ResolvedLLMConfig, ResolvedImageGenConfig, AgentLLMConfigUpdate, AgentImageGenConfigUpdate, AgentModelConfigTestResponse } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

function apiOrigin(): string {
  try {
    return new URL(API_BASE_URL).origin;
  } catch {
    return '';
  }
}

function resolveApiUrl(pathOrUrl: string): string {
  if (/^https?:\/\//.test(pathOrUrl)) {
    return pathOrUrl;
  }

  if (pathOrUrl.startsWith('/api/')) {
    return `${apiOrigin()}${pathOrUrl}`;
  }

  if (pathOrUrl.startsWith('/')) {
    return `${API_BASE_URL}${pathOrUrl}`;
  }

  return `${API_BASE_URL}/${pathOrUrl}`;
}

function encodeArtifactPath(artifactPath: string): string {
  return artifactPath
    .replace(/^\/+/, '')
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

// ============ Helper Functions ============
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = `API Error: ${response.status} ${response.statusText}`;
    try {
      const errorBody = await response.json();
      if (isRecord(errorBody)) {
        const detail = errorBody.detail || errorBody.error || errorBody.message;
        if (typeof detail === 'string') {
          message = detail;
        }
      }
    } catch {
      // Keep the HTTP status fallback when the response body is not JSON.
    }
    throw new Error(message);
  }

  // 204 No Content — no body to parse
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ============ Task API ============
export interface CreateTaskRequest {
  tech_description: string;
  patent_type_preference?: 'invention' | 'utility' | 'design';
  target_country?: string;
  user_id?: string;
}

export interface TaskResponse {
  task_id: string;
  user_id: string;
  current_state: string;
  created_at: string;
  updated_at: string;
  iteration_count: number;
  error_message?: string;
}

export interface TaskDetailResponse extends TaskResponse {
  requirement_doc?: any;
  retrieval_report?: any;
  draft_doc?: any;
  review_report?: any;
  final_patent?: any;
}

export interface TaskListResponse {
  total: number;
  tasks: TaskResponse[];
}

export const taskApi = {
  create: (data: CreateTaskRequest) =>
    request<TaskResponse>('/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: (user_id?: string, limit = 20, offset = 0) =>
    request<TaskListResponse>(
      `/tasks?${user_id ? `user_id=${encodeURIComponent(user_id)}&` : ''}limit=${limit}&offset=${offset}`
    ),

  get: (task_id: string) =>
    request<TaskDetailResponse>(`/tasks/${encodeURIComponent(task_id)}`),

  getEvents: (task_id: string) =>
    request<any[]>(`/tasks/${encodeURIComponent(task_id)}/events`),

  cancel: (task_id: string) =>
    request(`/tasks/${encodeURIComponent(task_id)}/cancel`, { method: 'POST' }),
};

// ============ Workflow API ============
export interface WorkflowPhaseResult {
  phase: string;
  success: boolean;
  duration_seconds: number;
  output: Record<string, unknown>;
  issues: string[];
  warnings: string[];
}

export interface WorkflowResponse {
  task_id: string;
  user_id: string;
  title?: string;
  current_state: string;
  created_at: string;
  updated_at?: string;
  iteration_count: number;
  message_count: number;
  conversation_id?: string;
  phase_history: WorkflowPhaseResult[];
  outputs: {
    brainstorming: Record<string, unknown>;
    requirement_analysis: Record<string, unknown>;
    retrieval_report: Record<string, unknown>;
    patent_draft: Record<string, unknown>;
    review_report: Record<string, unknown>;
  };
  quality_remediation?: Record<string, unknown>;
}

export interface WorkflowDecisionResponse {
  task_id: string;
  status: string;
  current_phase: string;
  action: 'continue_auto_fix' | 'provide_info';
  resume_phase: string;
}

export interface WorkflowChatResponse {
  role: 'assistant';
  content: string;
  timestamp: string;
  task_id: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw new Error(`Invalid workflow response: ${field} must be a string`);
  }
  return value;
}

function requireNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`Invalid workflow response: ${field} must be a number`);
  }
  return value;
}

function requireBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') {
    throw new Error(`Invalid workflow response: ${field} must be a boolean`);
  }
  return value;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function safeRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function parseWorkflowPhaseResult(value: unknown): WorkflowPhaseResult {
  if (!isRecord(value)) {
    throw new Error('Invalid workflow response: phase_history item must be an object');
  }

  return {
    phase: requireString(value.phase, 'phase_history.phase'),
    success: requireBoolean(value.success, 'phase_history.success'),
    duration_seconds: requireNumber(value.duration_seconds, 'phase_history.duration_seconds'),
    output: safeRecord(value.output),
    issues: stringArray(value.issues),
    warnings: stringArray(value.warnings),
  };
}

function parseWorkflowResponse(value: unknown): WorkflowResponse {
  if (!isRecord(value)) {
    throw new Error('Invalid workflow response: response must be an object');
  }

  const outputs = safeRecord(value.outputs);

  return {
    task_id: requireString(value.task_id, 'task_id'),
    user_id: requireString(value.user_id, 'user_id'),
    title: typeof value.title === 'string' ? value.title : undefined,
    current_state: requireString(value.current_state, 'current_state'),
    created_at: requireString(value.created_at, 'created_at'),
    updated_at: typeof value.updated_at === 'string' ? value.updated_at : undefined,
    iteration_count: requireNumber(value.iteration_count, 'iteration_count'),
    message_count: requireNumber(value.message_count, 'message_count'),
    phase_history: Array.isArray(value.phase_history)
      ? value.phase_history.map(parseWorkflowPhaseResult)
      : [],
    outputs: {
      brainstorming: safeRecord(outputs.brainstorming),
      requirement_analysis: safeRecord(outputs.requirement_analysis),
      retrieval_report: safeRecord(outputs.retrieval_report),
      patent_draft: safeRecord(outputs.patent_draft),
      review_report: safeRecord(outputs.review_report),
    },
    quality_remediation: isRecord(value.quality_remediation) ? value.quality_remediation : undefined,
  };
}

export interface WorkflowListResponse {
  total: number;
  items: WorkflowResponse[];
}

function parseWorkflowListResponse(value: unknown): WorkflowListResponse {
  if (!isRecord(value)) {
    throw new Error('Invalid workflow list response: response must be an object');
  }

  return {
    total: requireNumber(value.total, 'total'),
    items: Array.isArray(value.items) ? value.items.map(parseWorkflowResponse) : [],
  };
}

export const workflowApi = {
  create: async (techDescription: string, userId = 'default_user', patentTypePreference?: 'invention' | 'utility' | 'design') =>
    parseWorkflowResponse(await request<unknown>('/workflows', {
      method: 'POST',
      body: JSON.stringify({
        tech_description: techDescription,
        user_id: userId,
        ...(patentTypePreference ? { patent_type_preference: patentTypePreference } : {}),
      }),
    })),

  chat: (taskId: string, content: string, userId = 'default_user') =>
    request<WorkflowChatResponse>(`/workflows/${encodeURIComponent(taskId)}/chat`, {
      method: 'POST',
      body: JSON.stringify({ content, user_id: userId, task_id: taskId }),
    }),

  start: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/start`, { method: 'POST' }),

  list: async (userId = 'default_user', limit = 50, offset = 0) =>
    parseWorkflowListResponse(
      await request<unknown>(`/workflows?user_id=${encodeURIComponent(userId)}&limit=${limit}&offset=${offset}`)
    ),

  get: async (taskId: string) =>
    parseWorkflowResponse(await request<unknown>(`/workflows/${encodeURIComponent(taskId)}`)),

  getMessages: (taskId: string) =>
    request<{ messages: ChatMessage[]; count: number }>(`/workflows/${encodeURIComponent(taskId)}/messages`),

  pause: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/pause`, { method: 'POST' }),

  unpause: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/unpause`, { method: 'POST' }),

  resume: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/resume`, { method: 'POST' }),

  decision: (taskId: string, action: 'continue_auto_fix' | 'provide_info', supplementalInfo?: string) =>
    request<WorkflowDecisionResponse>(`/workflows/${encodeURIComponent(taskId)}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        ...(supplementalInfo ? { supplemental_info: supplementalInfo } : {}),
      }),
    }),

  restart: (taskId: string) =>
    request<{ task_id: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/restart`, { method: 'POST' }),

  retryPhase: (taskId: string, phase: string) =>
    request<{ task_id: string; phase: string; status: string }>(`/workflows/${encodeURIComponent(taskId)}/retry-phase`, {
      method: 'POST',
      body: JSON.stringify({ phase }),
    }),

  exportDocx: (taskId: string) =>
    `${API_BASE_URL}/workflows/${encodeURIComponent(taskId)}/export/docx`,

  artifactUrl: (taskId: string, artifactPathOrUrl: string) => {
    const trimmedArtifactPathOrUrl = artifactPathOrUrl.trim();

    if (!trimmedArtifactPathOrUrl) {
      return '';
    }

    if (/^https?:\/\//.test(trimmedArtifactPathOrUrl) || trimmedArtifactPathOrUrl.startsWith('/api/')) {
      return resolveApiUrl(trimmedArtifactPathOrUrl);
    }

    return `${API_BASE_URL}/workflows/${encodeURIComponent(taskId)}/artifacts/${encodeArtifactPath(trimmedArtifactPathOrUrl)}`;
  },
};

// ============ Chat API ============
export interface ChatMessage {
  id: string;
  task_id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  type?: 'text' | 'json' | 'file' | 'progress';
  metadata?: Record<string, unknown>;
  agent_events?: AgentEvent[];
  tool_calls?: Array<{
    name: string;
    parameters: Record<string, unknown>;
    result: unknown;
    success: boolean;
    error?: string;
    duration_ms?: number;
  }>;
}

export const chatApi = {
  sendMessage: (content: string, task_id?: string, user_id?: string) =>
    request<{ user_message: ChatMessage; assistant_message: ChatMessage }>('/chat/messages', {
      method: 'POST',
      headers: user_id ? { 'X-User-ID': user_id } : undefined,
      body: JSON.stringify({ content, task_id }),
    }),

  getMessages: (session_id = 'default', user_id?: string) =>
    request<{ messages: ChatMessage[]; count: number }>(
      `/chat/messages?session_id=${encodeURIComponent(session_id)}`,
      { headers: user_id ? { 'X-User-ID': user_id } : undefined },
    ),
};

// ============ Agent Management API ============
export interface AgentDetailResponse {
  config: AgentConfig;
  tools: AgentTool[];
  skills: AgentSkill[];
  timers: AgentTimer[];
  memories: AgentMemory[];
}

// ============ Hermes Hot-Plug API ============
export interface ValidateToolResponse {
  valid: boolean;
  name: string | null;
  error: string | null;
}

export interface HotPlugResponse {
  success: boolean;
  name: string;
  message: string;
}

export interface ChatGenerateResponse {
  success: boolean;
  name: string;
  code: string;
  message: string;
  skill_data?: { name: string; description: string; proficiency: number; keywords: string[] };
  generated_content?: string;
}

export interface UploadSkillResponse {
  success: boolean;
  name: string;
  files: { filename: string; content: string; size: number }[];
  scripts: string[];
  message: string;
}

export interface RelatedFileEntry {
  path: string;
  content: string | null;
}

export interface RelatedFilesResponse {
  type: 'tool' | 'skill';
  name: string;
  source_code: string | null;
  source_markdown?: string;
  files: RelatedFileEntry[];
}

export const hermesApi = {
  validateTool: (agentId: string, code: string) =>
    request<ValidateToolResponse>(`/agents/${encodeURIComponent(agentId)}/tools/validate`, {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  hotPlugTool: (agentId: string, name: string, description: string, code: string) =>
    request<HotPlugResponse>(`/agents/${encodeURIComponent(agentId)}/tools/hot-plug`, {
      method: 'POST',
      body: JSON.stringify({ name, description, code }),
    }),

  chatGenerateTool: (agentId: string, name: string, description: string, parameters?: Record<string, string>) =>
    request<ChatGenerateResponse>(`/agents/${encodeURIComponent(agentId)}/tools/chat-generate`, {
      method: 'POST',
      body: JSON.stringify({ name, description, parameters }),
    }),

   uploadSkill: (agentId: string, name: string, description: string, options?: { markdown?: string; zipBase64?: string; tags?: string[] }) =>
     request<UploadSkillResponse>(`/agents/${encodeURIComponent(agentId)}/skills/upload`, {
       method: 'POST',
       body: JSON.stringify({ name, description, ...options }),
     }),

   chatGenerateSkill: (agentId: string, name: string | undefined, description: string, parameters?: Record<string, string>) =>
     request<ChatGenerateResponse>(`/agents/${encodeURIComponent(agentId)}/skills/chat-generate`, {
       method: 'POST',
       body: JSON.stringify({ name, description, parameters }),
     }),

   getRelatedFiles: (agentId: string, toolId?: string, skillId?: string) => {
    const params = new URLSearchParams();
    if (toolId) params.set('tool_id', toolId);
    if (skillId) params.set('skill_id', skillId);
    return request<RelatedFilesResponse>(`/agents/${encodeURIComponent(agentId)}/related-files?${params.toString()}`);
  },

  createTool: (agentId: string, toolData: Record<string, unknown>) =>
    request<{ success: boolean; tool: Record<string, unknown> }>(`/agents/${encodeURIComponent(agentId)}/tools`, {
      method: 'POST',
      body: JSON.stringify(toolData),
    }),

  updateTool: (agentId: string, toolId: string, toolData: Record<string, unknown>) =>
    request<{ success: boolean; tool: Record<string, unknown> }>(`/agents/${encodeURIComponent(agentId)}/tools/${encodeURIComponent(toolId)}`, {
      method: 'PUT',
      body: JSON.stringify(toolData),
    }),

  deleteTool: (agentId: string, toolId: string) =>
    request<{ success: boolean; tool_id: string }>(`/agents/${encodeURIComponent(agentId)}/tools/${encodeURIComponent(toolId)}`, {
      method: 'DELETE',
    }),
};

export const agentApi = {
  list: () =>
    request<{ agents: AgentConfig[]; total: number }>('/agents'),

  browseDirectory: (agentId: string, path = '') =>
    request<BrowseDirResponse>(`/agents/${encodeURIComponent(agentId)}/browse?path=${encodeURIComponent(path)}`),

  getAgentFileContent: (agentId: string, path: string) =>
    request<FileContentResponse>(`/agents/${encodeURIComponent(agentId)}/file?path=${encodeURIComponent(path)}`),

  get: (agent_id: string) =>
    request<AgentDetailResponse>(`/agents/${encodeURIComponent(agent_id)}`),

  update: (agent_id: string, config: Partial<AgentConfig>) =>
    request(`/agents/${encodeURIComponent(agent_id)}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  toggleTool: (agent_id: string, tool_id: string, enabled: boolean) =>
    request(`/agents/${encodeURIComponent(agent_id)}/tools/${encodeURIComponent(tool_id)}/toggle?enabled=${enabled}`, { method: 'POST' }),

  toggleSkill: (agent_id: string, skill_id: string, enabled: boolean) =>
    request(`/agents/${encodeURIComponent(agent_id)}/skills/${encodeURIComponent(skill_id)}/toggle?enabled=${enabled}`, { method: 'POST' }),

  toggleTimer: (agent_id: string, timer_id: string, enabled: boolean) =>
    request(`/agents/${encodeURIComponent(agent_id)}/timers/${encodeURIComponent(timer_id)}/toggle?enabled=${enabled}`, { method: 'POST' }),

  clearMemory: (agent_id: string, memory_id: string) =>
    request(`/agents/${encodeURIComponent(agent_id)}/memory/${encodeURIComponent(memory_id)}/clear`, { method: 'POST' }),

  deleteMemoryEntry: (agent_id: string, memory_id: string, entry_id: string) =>
    request(`/agents/${encodeURIComponent(agent_id)}/memory/${encodeURIComponent(memory_id)}/entries/${encodeURIComponent(entry_id)}`, {
      method: 'DELETE',
    }),

  // Helper: update full tools/skills/timers arrays via PUT agents/{id}
  updateTools: (agent_id: string, tools: AgentTool[]) =>
    request(`/agents/${encodeURIComponent(agent_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ tools }),
    }),

  updateSkills: (agent_id: string, skills: AgentSkill[]) =>
    request(`/agents/${encodeURIComponent(agent_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ skills }),
    }),

  updateTimers: (agent_id: string, timers: AgentTimer[]) =>
    request(`/agents/${encodeURIComponent(agent_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ timers }),
    }),

  // Per-agent LLM config
  getLLMConfig: async (agent_id: string): Promise<ResolvedLLMConfig | null> => {
    const detail = await agentApi.get(agent_id) as any;
    return detail?.llm_config ?? null;
  },

  updateLLMConfig: (agent_id: string, body: AgentLLMConfigUpdate) =>
    request<ResolvedLLMConfig>(`/agents/${encodeURIComponent(agent_id)}/llm-config`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  testLLMConfig: (agent_id: string, body: AgentLLMConfigUpdate) =>
    request<AgentModelConfigTestResponse>(`/agents/${encodeURIComponent(agent_id)}/llm-config/test`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Per-agent ImageGen config
  getImageGenConfig: async (agent_id: string): Promise<ResolvedImageGenConfig | null> => {
    const detail = await agentApi.get(agent_id) as any;
    return detail?.image_gen_config ?? null;
  },

  updateImageGenConfig: (agent_id: string, body: AgentImageGenConfigUpdate) =>
    request<ResolvedImageGenConfig>(`/agents/${encodeURIComponent(agent_id)}/image-gen-config`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  testImageGenConfig: (agent_id: string, body: AgentImageGenConfigUpdate) =>
    request<AgentModelConfigTestResponse>(`/agents/${encodeURIComponent(agent_id)}/image-gen-config/test`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};

// ============ Organization API ============
export const organizationApi = {
  getTree: () =>
    request<OrgNode>('/organization/tree'),

  updateTree: (tree: OrgNode) =>
    request('/organization/tree', {
      method: 'PUT',
      body: JSON.stringify(tree),
    }),
};

// ============ Search API ============
export interface SearchPatentRequest {
  query: string;
  sources?: string[];
  limit?: number;
}

export interface SearchResult {
  id: string;
  title: string;
  abstract?: string;
  applicant?: string;
  publication_date?: string;
  similarity_score?: number;
  source: string;
}

export interface SearchResponse {
  total: number;
  results: SearchResult[];
  query: string;
  search_time: number;
}

export const searchApi = {
  patents: (data: SearchPatentRequest) =>
    request<SearchResponse>('/search/patents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  knowledgeBase: (query: string, top_k = 5) =>
    request<{ total: number; patents: any[]; query: string }>(`/knowledge/search?query=${encodeURIComponent(query)}&top_k=${top_k}`),
};

// ============ System API ============
export interface SystemStatusResponse {
  status: string;
  active_tasks: number;
  agents: { name: string; description: string; status: string }[];
  knowledge_base_count: number;
  data_sources: string[];
}

export interface DashboardStats {
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
  failed_tasks: number;
  active_agents: number;
  avg_completion_time: string;
  success_rate: number;
}

export const systemApi = {
  status: () =>
    request<SystemStatusResponse>('/system/status'),

  config: () =>
    request<SystemConfigResponse>('/system/config'),

  updateConfig: (data: SystemConfigUpdateRequest) =>
    request<SystemConfigResponse>('/system/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  envInfo: () =>
    request<EnvInfoResponse>('/system/config/env-info'),

  health: () =>
    request<{ status: string; timestamp: string }>('/health'),

  dashboardStats: () =>
    request<DashboardStats>('/stats/dashboard'),
};

// ============ SSE Event Stream ============
const SSE_MAX_RETRIES = 8;
const SSE_INITIAL_DELAY = 1000;
const SSE_MAX_DELAY = 30000;

export function createEventStream(
  task_id: string,
  onEvent: (event: any) => void,
  onDone: (state: string) => void,
): () => void {
  let retryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  let currentEventSource: EventSource | null = null;

  function cleanup() {
    closed = true;
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }
  }

  function connect() {
    if (closed) return;
    if (currentEventSource) {
      currentEventSource.close();
    }

    currentEventSource = new EventSource(`${API_BASE_URL}/tasks/${task_id}/stream`);

    currentEventSource.onmessage = (event) => {
      if (closed) return;
      try {
        const data = JSON.parse(event.data);
        onEvent(data);
      } catch (e) {
        console.error('Failed to parse SSE event:', e);
      }
    };

    currentEventSource.addEventListener('done', (event: any) => {
      if (closed) return;
      onDone(event.data);
      cleanup();
    });

    currentEventSource.onerror = () => {
      if (closed) return;
      retryCount++;
      if (retryCount > SSE_MAX_RETRIES) {
        console.error(`SSE: max retries (${SSE_MAX_RETRIES}) exceeded, giving up`);
        cleanup();
        return;
      }
      const delay = Math.min(SSE_INITIAL_DELAY * Math.pow(2, retryCount - 1), SSE_MAX_DELAY);
      if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
      }
      retryTimer = setTimeout(connect, delay);
    };
  }

  connect();
  return cleanup;
}

// ============ React Query Hooks (Optional) ============
// These can be used with @tanstack/react-query for caching and state management

// ============ Conversation API ============
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  status: string;
  linked_workflow_id?: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface CreateConversationRequest {
  user_id: string;
  title?: string;
}

export interface ConversationChatRequest {
  content: string;
}

export interface ConversationChatResponse {
  message: ChatMessage;
  has_recommendation: boolean;
  conversation_id: string;
}

export const conversationApi = {
  create: (data: CreateConversationRequest) =>
    request<ConversationDetail>('/conversations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: async (user_id = 'default_user') => {
    const raw = await request<{ total: number; items: ConversationSummary[] }>(
      `/conversations?user_id=${encodeURIComponent(user_id)}`
    );
    // Backend returns { items, total, page, page_size }; normalize to { conversations, total }
    return {
      total: raw.total,
      conversations: raw.items ?? [],
    };
  },

  get: (conv_id: string) =>
    request<ConversationDetail>(`/conversations/${encodeURIComponent(conv_id)}`),

  rename: (conv_id: string, title: string) =>
    request<{ id: string; title: string; updated_at: string }>(`/conversations/${encodeURIComponent(conv_id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  delete: (conv_id: string) =>
    request<void>(`/conversations/${encodeURIComponent(conv_id)}`, {
      method: 'DELETE',
    }),

  chat: (conv_id: string, data: ConversationChatRequest) =>
    request<ConversationChatResponse>(`/conversations/${encodeURIComponent(conv_id)}/chat`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * 上传交底书/技术资料文件到对话中。
   * 后端会自动解析文件内容并作为用户消息追加到对话历史。
   */
  uploadDisclosure: async (conv_id: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    const url = `${API_BASE_URL}/conversations/${encodeURIComponent(conv_id)}/upload`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      let message = `Upload failed: ${response.status} ${response.statusText}`;
      try {
        const errorBody = await response.json();
        if (isRecord(errorBody)) {
          const detail = errorBody.detail || errorBody.error || errorBody.message;
          if (typeof detail === 'string') {
            message = detail;
          }
        }
      } catch {
      }
      throw new Error(message);
    }

    return (await response.json()) as {
      conversation_id: string;
      filename: string;
      file_type: string;
      file_size: number;
      extracted_text: string;
      message_id: string;
      char_count: number;
      metadata?: Record<string, unknown>;
    };
  },

  createWorkflow: (conv_id: string) =>
    request<{ task_id: string; status: string; redirect_url: string }>(
      `/conversations/${encodeURIComponent(conv_id)}/create-workflow`,
      {
        method: 'POST',
        body: JSON.stringify({}),
      }
    ),

  /**
   * 流式聊天 — SSE 接收 agent 的工具调用、技能使用、内容输出
   * 内置超时 + 自动重试 (最多 3 次) 增强连接可靠性
   */
  chatStream: (
    conv_id: string,
    data: ConversationChatRequest,
    callbacks: {
      onThinking?: (data: { iteration: number; agent: string; phase?: string }) => void;
      onSkillUse?: (data: { name: string; description: string; reasoning: string }) => void;
      onToolCallStart?: (data: { name: string; parameters: Record<string, unknown> }) => void;
      onToolCallEnd?: (data: { name: string; parameters: Record<string, unknown>; result: unknown; success: boolean; error?: string }) => void;
      onStreamDelta?: (data: { content: string }) => void;
      onContent?: (data: { content: string; has_recommendation: boolean }) => void;
      onConfirmation?: (data: { question: string; options: string[] }) => void;
      onAgentActivity?: (data: AgentEvent) => void;
      onDone?: (data: { message: ChatMessage; has_recommendation: boolean; needs_confirmation?: boolean; conversation_id: string }) => void;
      onError?: (error: string) => void;
      onStatusChange?: (status: 'connecting' | 'connected' | 'disconnected') => void;
      onStatus?: (data: { agent: string; status: string; message: string; iteration?: number }) => void;
    },
    options?: { timeout?: number; maxRetries?: number; stallTimeout?: number },
  ): { abort: () => void } => {
    const controller = new AbortController();
    const timeout = options?.timeout ?? 30000;
    const maxRetries = options?.maxRetries ?? 3;
    const stallTimeout = options?.stallTimeout ?? 60000;

    // Timeout timer — fires once if initial fetch takes too long
    let timeoutTimer: ReturnType<typeof setTimeout> | null = null;
    // Stall timer — resets on each data chunk, errors if nothing arrives within window
    let stallTimer: ReturnType<typeof setTimeout> | null = null;

    (async () => {
      let attempt = 0;
      while (attempt <= maxRetries) {
        if (controller.signal.aborted) return;

        if (attempt > 0) {
          callbacks.onStatusChange?.('connecting');
          // Exponential backoff: 1s, 2s, 4s
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }

        attempt++;

        try {
          callbacks.onStatusChange?.('connecting');

          const response = await Promise.race([
            fetch(
              `${API_BASE_URL}/conversations/${encodeURIComponent(conv_id)}/chat/stream`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
                signal: controller.signal,
              }
            ),
            new Promise<Response>((_, reject) => {
              timeoutTimer = setTimeout(() => {
                reject(new Error('Request timeout'));
              }, timeout);
            }),
          ]);

          if (timeoutTimer) clearTimeout(timeoutTimer);
          timeoutTimer = null;

          if (!response.ok) {
            const errBody = await response.text();
            if (attempt <= maxRetries) {
              continue;
            }
            callbacks.onError?.(errBody || `HTTP ${response.status}`);
            return;
          }

          callbacks.onStatusChange?.('connected');

          // Reset stall timer on each data chunk
          const resetStallTimer = () => {
            if (stallTimer) clearTimeout(stallTimer);
            stallTimer = setTimeout(() => {
              controller.abort();
              callbacks.onError?.('Stream stalled — no data received');
            }, stallTimeout);
          };

          const reader = response.body?.getReader();
          if (!reader) {
            callbacks.onError?.('No response body');
            callbacks.onStatusChange?.('disconnected');
            return;
          }

          const decoder = new TextDecoder();
          let buffer = '';

          // Start stall timer before first chunk
          resetStallTimer();

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            resetStallTimer();

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let eventType = '';
            let eventData = '';

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                eventData = line.slice(6);
              } else if (line === '' && eventType && eventData) {
                try {
                  const parsed = JSON.parse(eventData);
                  switch (eventType) {
                    case 'agent_activity':
                      callbacks.onAgentActivity?.(parsed);
                      break;
                    case 'thinking':
                      callbacks.onThinking?.(parsed);
                      break;
                    case 'skill_use':
                      callbacks.onSkillUse?.(parsed);
                      break;
                    case 'tool_call_start':
                      callbacks.onToolCallStart?.(parsed);
                      break;
                    case 'tool_call_end':
                      callbacks.onToolCallEnd?.(parsed);
                      break;
                    case 'stream_delta':
                      callbacks.onStreamDelta?.(parsed);
                      break;
                    case 'content':
                      callbacks.onContent?.(parsed);
                      break;
                    case 'status':
                      callbacks.onStatus?.(parsed);
                      break;
                    case 'confirmation':
                      callbacks.onConfirmation?.(parsed);
                      break;
                    case 'done':
                      callbacks.onDone?.(parsed);
                      break;
                    case 'error':
                      callbacks.onError?.(parsed.error || 'Unknown error');
                      break;
                    default:
                      if (parsed?.kind === 'lifecycle' && parsed?.message) {
                        callbacks.onError?.(parsed.message);
                      }
                      break;
                  }
                } catch {
                  // ignore parse errors
                }
                eventType = '';
                eventData = '';
              }
            }
          }

          // Stream completed successfully — exit retry loop
          return;
        } catch (err) {
          if (controller.signal.aborted) return;

          if (attempt <= maxRetries) {
            continue;
          }

          callbacks.onError?.(err instanceof Error ? err.message : 'Stream failed');
          callbacks.onStatusChange?.('disconnected');
          return;
        } finally {
          if (timeoutTimer) clearTimeout(timeoutTimer);
          if (stallTimer) clearTimeout(stallTimer);
        }
      }
    })();

    return {
      abort: () => {
        if (timeoutTimer) clearTimeout(timeoutTimer);
        controller.abort();
      },
    };
  },
};

// ============ React Query Hooks (Optional) ============
// These can be used with @tanstack/react-query for caching and state management

export const queryKeys = {
  tasks: ['tasks'],
  task: (id: string) => ['task', id],
  taskEvents: (id: string) => ['task-events', id],
  chat: (session_id: string) => ['chat', session_id],
  agents: ['agents'],
  agent: (id: string) => ['agent', id],
  organization: ['organization'],
  systemStatus: ['system-status'],
  dashboardStats: ['dashboard-stats'],
  conversations: ['conversations'],
  conversation: (id: string) => ['conversation', id],
};
