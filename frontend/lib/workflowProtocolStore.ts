import { EventType, type BaseEvent } from '@ag-ui/core';
import type { BaseEvent as ClientBaseEvent } from '@ag-ui/client';
import type { AgentLogEntry } from '@/types';

export type AgUiClientEvent = ClientBaseEvent;
export type AgUiCoreEvent = BaseEvent;

export interface WorkflowProtocolEvent {
  agui_type: string;
  type?: string;
  event_type?: string;
  run_id?: string;
  message_id?: string;
  tool_call_id?: string;
  parent_message_id?: string;
  timestamp?: string;
  agent_name?: string;
  agent?: string;
  display_message?: string;
  message?: string;
  content?: string;
  phase?: string;
  phase_node?: string;
  node?: string;
  round?: number;
  state_delta?: Record<string, unknown>;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WorkflowToolCallState {
  id: string;
  name: string;
  args?: unknown;
  result?: unknown;
  status: 'running' | 'completed' | 'failed';
}

export interface WorkflowProtocolState {
  runId: string;
  currentNode: string;
  currentRound: number | null;
  messages: Record<string, string>;
  toolCalls: Record<string, WorkflowToolCallState>;
  retrievalResults: unknown[];
  writingSections: unknown[];
  qualityRoute: unknown | null;
  interrupt: unknown | null;
  sharedFacts: Record<string, unknown>;
  rawEvents: WorkflowProtocolEvent[];
}

const WORKFLOW_RELOAD_TYPES = new Set([
  'PHASE_ROUND_STARTED',
  'PHASE_ROUND_COMPLETED',
  'QUALITY_GATE_COMPLETED',
  'SHARED_FACTS_UPDATED',
  'HUMAN_INPUT_REQUESTED',
  EventType.RUN_FINISHED,
]);

const LEGACY_EVENT_TO_AGUI: Record<string, string> = {
  'workflow.run.started': EventType.RUN_STARTED,
  'workflow.state.delta': EventType.STATE_DELTA,
  'agent.message.start': EventType.TEXT_MESSAGE_START,
  'agent.content': EventType.TEXT_MESSAGE_CONTENT,
  'agent.message.end': EventType.TEXT_MESSAGE_END,
  'agent.tool_call_start': EventType.TOOL_CALL_START,
  'agent.tool_call_delta': EventType.TOOL_CALL_ARGS,
  'agent.tool_call_result': EventType.TOOL_CALL_RESULT,
  'agent.tool_call_end': EventType.TOOL_CALL_END,
  'workflow.phase_round.started': 'PHASE_ROUND_STARTED',
  'workflow.phase_round.completed': 'PHASE_ROUND_COMPLETED',
  'workflow.quality_gate.completed': 'QUALITY_GATE_COMPLETED',
  'workflow.shared_facts.updated': 'SHARED_FACTS_UPDATED',
  'workflow.human_input.requested': 'HUMAN_INPUT_REQUESTED',
  'workflow.run.finished': EventType.RUN_FINISHED,
};

function eventData(raw: WorkflowProtocolEvent): WorkflowProtocolEvent {
  const data = raw.data && typeof raw.data === 'object' ? raw.data : {};
  return { ...raw, ...data } as WorkflowProtocolEvent;
}

export function normalizeWorkflowProtocolEvent(raw: unknown): WorkflowProtocolEvent {
  const parsed = (raw && typeof raw === 'object' ? raw : {}) as WorkflowProtocolEvent;
  const data = eventData(parsed);
  const sourceEventType = String(parsed.event_type || parsed.type || data.event_type || data.type || '');
  const aguiType = String(
    data.agui_type || LEGACY_EVENT_TO_AGUI[sourceEventType] || sourceEventType || EventType.RAW
  );
  const stateDelta =
    data.state_delta && typeof data.state_delta === 'object' && !Array.isArray(data.state_delta)
      ? (data.state_delta as Record<string, unknown>)
      : {};
  return {
    ...data,
    agui_type: aguiType,
    type: aguiType,
    event_type: sourceEventType,
    state_delta: stateDelta,
    run_id: String(data.run_id || stateDelta.run_id || data.task_id || ''),
    message_id: String(data.message_id || data.id || ''),
    tool_call_id: String(data.tool_call_id || data.toolCallId || ''),
    parent_message_id: String(data.parent_message_id || data.parentMessageId || ''),
  };
}

export function workflowEventShouldReload(eventType: string): boolean {
  return WORKFLOW_RELOAD_TYPES.has(eventType) || eventType.startsWith('workflow.');
}

export function createWorkflowProtocolStore(initial?: Partial<WorkflowProtocolState>) {
  let state: WorkflowProtocolState = {
    runId: '',
    currentNode: '',
    currentRound: null,
    messages: {},
    toolCalls: {},
    retrievalResults: [],
    writingSections: [],
    qualityRoute: null,
    interrupt: null,
    sharedFacts: {},
    rawEvents: [],
    ...initial,
  };

  const apply = (raw: unknown): WorkflowProtocolState => {
    const event = normalizeWorkflowProtocolEvent(raw);
    const stateDelta = event.state_delta || {};
    const currentNode = String(stateDelta.current_node || event.phase_node || event.node || state.currentNode || '');
    const currentRoundValue = stateDelta.current_round ?? event.round ?? state.currentRound;
    const currentRound =
      typeof currentRoundValue === 'number'
        ? currentRoundValue
        : currentRoundValue === null || currentRoundValue === undefined
          ? null
          : Number(currentRoundValue);
    const toolCallId = event.tool_call_id || '';
    const toolName = String(event.tool_name || event.name || '');
    const toolCalls = { ...state.toolCalls };
    if (toolCallId) {
      const previous = toolCalls[toolCallId] || {
        id: toolCallId,
        name: toolName,
        status: 'running' as const,
      };
      toolCalls[toolCallId] = {
        ...previous,
        name: toolName || previous.name,
        args:
          event.agui_type === EventType.TOOL_CALL_ARGS
            ? event.delta || event.args || event.parameters || previous.args
            : previous.args,
        result:
          event.agui_type === EventType.TOOL_CALL_RESULT
            ? event.result || event.tool_result || previous.result
            : previous.result,
        status:
          event.agui_type === EventType.TOOL_CALL_END || event.agui_type === EventType.TOOL_CALL_RESULT
            ? event.success === false
              ? 'failed'
              : 'completed'
            : previous.status,
      };
    }
    const messageId = event.message_id || '';
    const messages = { ...state.messages };
    if (messageId && event.agui_type === EventType.TEXT_MESSAGE_CONTENT) {
      messages[messageId] = `${messages[messageId] || ''}${event.content || event.message || ''}`;
    }
    state = {
      ...state,
      runId: event.run_id || state.runId,
      currentNode,
      currentRound: Number.isFinite(currentRound) ? currentRound : null,
      messages,
      toolCalls,
      qualityRoute:
        event.agui_type === 'QUALITY_GATE_COMPLETED'
          ? event.result || event.state_delta || event
          : state.qualityRoute,
      interrupt:
        event.agui_type === 'HUMAN_INPUT_REQUESTED'
          ? event.state_delta || event
          : state.interrupt,
      sharedFacts:
        event.agui_type === 'SHARED_FACTS_UPDATED' && stateDelta.shared_facts
          ? (stateDelta.shared_facts as Record<string, unknown>)
          : state.sharedFacts,
      rawEvents: [...state.rawEvents, event].slice(-500),
    };
    return state;
  };

  return {
    getState: () => state,
    apply,
  };
}

export function workflowProtocolEventToLogEntry(
  event: WorkflowProtocolEvent,
  receivedAt: string
): Omit<AgentLogEntry, 'id'> {
  const agentName = String(event.agent_name || event.agent || 'Workflow Engine');
  const timestamp = String(event.timestamp || receivedAt);
  const message = String(event.display_message || event.message || event.content || event.agui_type);
  if (event.agui_type === EventType.TOOL_CALL_START) {
    return {
      timestamp,
      agent_name: agentName,
      type: 'tool_start',
      tool_name: String(event.tool_name || event.name || ''),
      tool_params: (event.parameters || event.args || {}) as Record<string, unknown>,
    };
  }
  if (event.agui_type === EventType.TOOL_CALL_ARGS) {
    return {
      timestamp,
      agent_name: agentName,
      type: 'tool_delta',
      tool_name: String(event.tool_name || event.name || ''),
      tool_delta: message,
      message,
    };
  }
  if (event.agui_type === EventType.TOOL_CALL_RESULT || event.agui_type === EventType.TOOL_CALL_END) {
    return {
      timestamp,
      agent_name: agentName,
      type: 'tool_end',
      tool_name: String(event.tool_name || event.name || ''),
      tool_result: String(event.result || event.tool_result || ''),
      tool_success: event.success !== false,
    };
  }
  if (event.agui_type === EventType.TEXT_MESSAGE_CONTENT) {
    return {
      timestamp,
      agent_name: agentName,
      type: 'content',
      content: message,
      phase: String(event.phase || event.phase_node || event.state_delta?.current_node || ''),
    };
  }
  return {
    timestamp,
    agent_name: agentName,
    type: event.agui_type === 'HUMAN_INPUT_REQUESTED' ? 'error' : 'progress',
    message,
    phase: String(event.phase || event.phase_node || event.state_delta?.current_node || ''),
  };
}
