export const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1';

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE_URL
).replace(/\/+$/, '');

export const SSE_RECONNECT = {
  maxRetries: 8,
  initialDelayMs: 1000,
  maxDelayMs: 30000,
} as const;

export const POLLING_INTERVALS = {
  conversationListMs: 30000,
  workflowInitialMs: 3000,
  workflowMaxMs: 30000,
  workflowSyncMs: 3000,
} as const;

export const CHAT_STREAM_DEFAULTS = {
  timeoutMs: 30000,
  maxRetries: 3,
  stallTimeoutMs: 60000,
  initialBackoffMs: 1000,
  maxBackoffMs: 10000,
} as const;
