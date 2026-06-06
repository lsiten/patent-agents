export type WorkflowState =
  | 'initial'
  | 'requirement'
  | 'retrieval'
  | 'writing'
  | 'reviewing'
  | 'iteration'
  | 'completed'
  | 'failed';

export type PatentType = 'invention' | 'utility' | 'design';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface KeyFeature {
  name: string;
  description: string;
  is_innovative: boolean;
}

export interface PatentTypeRecommendation {
  type: PatentType;
  rationale: string;
}

export interface RequirementDoc {
  tech_field: string;
  core_principle: string;
  application_scenarios: string[];
  technical_problem: string;
  key_features: KeyFeature[];
  patent_type_recommendation: PatentTypeRecommendation;
  beneficial_effects: string[];
  information_gaps: string[];
}

export interface Assessment {
  rating: 'high' | 'medium' | 'low';
  rationale: string;
}

export interface NoveltyAssessment extends Assessment {
  related_prior_art: string[];
}

export interface InventiveStepAssessment extends Assessment {
  distinguishing_features: string[];
}

export interface SimilarPatent {
  patent_id?: string;
  reference_id?: string;
  title: string;
  source?: string;
  url?: string;
  applicant?: string;
  publication_date?: string;
  similarity_score: number;
  risk_level?: Severity;
  key_similarities?: string[];
  matching_features?: string[];
  key_differences?: string[];
  differences?: string;
}

export interface RetrievalReport {
  novelty_assessment: NoveltyAssessment;
  inventive_step_assessment: InventiveStepAssessment;
  utility_assessment: Assessment;
  similar_patents: SimilarPatent[];
  prior_art_references?: SimilarPatent[];
  writing_recommendations: string[];
  overall_patentability: 'high' | 'medium' | 'low';
  risk_factors: string[];
}

export interface Claims {
  independent_claim: string;
  dependent_claims: string[];
}

export interface Description {
  technical_field: string;
  background_art: string;
  summary_of_invention: string;
  description_of_drawings: string;
  detailed_description: string;
}

export interface PatentDrawing {
  figure_number: string;
  title?: string;
  description?: string;
  file_path?: string;
  artifact_url?: string;
  artifactUrl?: string;
  mime_type?: string;
}

export interface PatentDraft {
  claims: Claims;
  description: Description;
  abstract: string;
  drawings?: PatentDrawing[];
  key_terms_dictionary: Record<string, string>;
}

export interface Issue {
  severity: Severity;
  location: string;
  description: string;
  suggestion: string;
}

export interface ReviewResult {
  passed: boolean;
  issues: Issue[];
}

export interface ClaimsReview extends ReviewResult {
  clarity_score: number;
  support_score: number;
}

export interface DescriptionReview extends ReviewResult {
  sufficiency_score: number;
  completeness_score: number;
}

export interface ExaminationRisk {
  risk_type: string;
  likelihood: Severity;
  mitigation_suggestion: string;
}

export interface ReviewReport {
  formal_compliance: ReviewResult;
  claims_review: ClaimsReview;
  description_review: DescriptionReview;
  consistency_review: ReviewResult;
  examination_risks: ExaminationRisk[];
  overall_score: number;
  recommendation: 'approve' | 'revise' | 'reject';
  revision_priority: Severity;
}

export interface PatentTask {
  task_id: string;
  user_id: string;
  tech_description: string;
  patent_type_preference?: PatentType;
  current_state: WorkflowState;
  requirement_doc?: RequirementDoc;
  retrieval_report?: RetrievalReport;
  draft_doc?: PatentDraft;
  review_report?: ReviewReport;
  iteration_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskRequest {
  tech_description: string;
  patent_type_preference?: PatentType;
  user_id: string;
}

export interface WorkflowEvent {
  task_id: string;
  timestamp: string;
  agent: string;
  message: string;
  type: 'info' | 'progress' | 'success' | 'warning' | 'error';
  data?: Record<string, unknown>;
}

// ============ Agent实时日志类型 ============
export type AgentLogEntryType =
  | 'dispatch'       // CEO调度子agent
  | 'thinking'       // agent思考过程
  | 'tool_start'     // 工具调用开始
  | 'tool_end'       // 工具调用完成
  | 'content'        // agent最终输出
  | 'progress'       // 阶段进度变化
  | 'error';         // 错误

export interface AgentLogEntry {
  id: string;
  timestamp: string;
  agent_name: string;
  type: AgentLogEntryType;
  // dispatch
  dispatch_to?: string;
  dispatch_task?: string;
  // thinking
  message?: string;
  // tool_start / tool_end
  tool_name?: string;
  tool_params?: Record<string, unknown>;
  tool_result?: string;
  tool_success?: boolean;
  // content
  content?: string;
  phase?: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  description: string;
  status: 'idle' | 'working' | 'completed' | 'error';
  icon: string;
}

// ============ 对话相关类型 ============
export type MessageRole = 'user' | 'assistant' | 'system' | 'agent';

export interface ToolCallInfo {
  name: string;
  parameters: Record<string, unknown>;
  result: unknown;
  success: boolean;
  error?: string;
  duration_ms?: number;
}

export interface SkillUseInfo {
  name: string;
  description: string;
  reasoning: string;
}

export interface AgentEvent {
  id: string;
  sequence: number;
  call_id: string;
  type: 'thinking' | 'tool_call_start' | 'tool_call_end' | 'skill_use' | 'status' | 'dispatch';
  agent_name: string;
  timestamp: string;
  message: string;
  data: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  task_id?: string;
  role: MessageRole;
  agent_name?: string;
  content: string;
  timestamp: string;
  type?: 'text' | 'json' | 'file' | 'progress';
  metadata?: Record<string, unknown>;
  tool_calls?: ToolCallInfo[];
  skill_uses?: SkillUseInfo[];
  agent_events?: AgentEvent[];
  isStreaming?: boolean;
}

export interface ChatSession {
  session_id: string;
  task_id?: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  status: 'draft' | 'in_progress' | 'completed';
  patent_title?: string;
}

// ============ Agent管理相关类型 ============
export interface AgentTool {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  category: 'search' | 'file' | 'analysis' | 'external';
  config?: Record<string, string>;
  source_code?: string;       // Tool implementation source (Python/TypeScript)
  is_hermes?: boolean;        // Whether created via Hermes framework
  related_files?: string[];   // Related source file paths (project-relative)
}

export interface AgentSkill {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  version: string;
  tags: string[];
  source_code?: string;       // Skill implementation source
  source_markdown?: string;   // Skill documented in Markdown
  related_files?: string[];   // Related source file paths (project-relative)
}

export interface AgentTimer {
  id: string;
  name: string;
  enabled: boolean;
  cron_expression: string;
  action: string;
  last_run?: string;
  next_run?: string;
}

export interface AgentMemory {
  id: string;
  type: 'short_term' | 'long_term' | 'knowledge_base';
  name: string;
  size: number;
  item_count: number;
  last_updated: string;
  content?: string;           // Memory content preview (JSON/text)
  entries?: MemoryEntry[];    // Individual memory entries
}

export interface MemoryEntry {
  id: string;
  type: 'fact' | 'context' | 'preference' | 'knowledge' | 'event';
  key: string;
  value: string;
  score?: number;
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  role: 'orchestrator' | 'specialist' | 'assistant' | 'critic';
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  working_directory: string;
  tools?: AgentTool[];
  skills?: AgentSkill[];
  timers?: AgentTimer[];
  memories?: AgentMemory[];
  parent_id?: string | null;
  child_ids: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

// ============ 组织架构相关类型 ============
export interface OrgNode {
  id: string;
  name: string;
  type: 'agent' | 'group' | 'team';
  description?: string;
  children: OrgNode[];
  parent_id?: string | null;
  agent_config?: AgentConfig;
  expanded?: boolean;
}

export type OrgAction = 'move' | 'copy' | 'delete' | 'edit' | 'add_child';

// ============ 专利管理扩展类型 ============
export interface PatentSummary {
  task_id: string;
  title: string;
  patent_type: PatentType;
  tech_field: string;
  current_state: WorkflowState;
  progress: number;
  created_at: string;
  updated_at: string;
  assignee?: string;
  inventors?: string[];
  application_number?: string;
  filing_date?: string;
}

export interface PatentFile {
  file_id: string;
  task_id: string;
  file_type: 'claims' | 'description' | 'abstract' | 'full_document' | 'drawing';
  format: 'docx' | 'pdf' | 'json' | 'md';
  version: string;
  file_name: string;
  file_size: number;
  created_at: string;
  download_url: string;
}

export interface PatentDetail extends PatentSummary {
  requirement_doc?: RequirementDoc;
  retrieval_report?: RetrievalReport;
  draft_doc?: PatentDraft;
  review_report?: ReviewReport;
  files: PatentFile[];
  events: WorkflowEvent[];
}

// ============ API响应类型 ============
export interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// ============ Agent 文件浏览类型 ============
// ============ 系统配置类型 ============
export interface ProviderConfigResponse {
  base_url: string;
  model_id: string;
  api_key_masked: string;
  configured: boolean;
}

export interface ModelConfigSectionResponse {
  active_provider: string;
  providers: Record<string, ProviderConfigResponse>;
}

export interface SystemConfigResponse {
  text_llm: ModelConfigSectionResponse;
  image_gen: ModelConfigSectionResponse;
  image_gen_fallback_to_llm: boolean;
}

export interface ProviderConfigUpdate {
  base_url?: string;
  api_key?: string;
  model_id?: string;
}

export interface ModelConfigSectionUpdate {
  active_provider?: string;
  providers?: Record<string, ProviderConfigUpdate>;
}

export interface SystemConfigUpdateRequest {
  text_llm?: ModelConfigSectionUpdate;
  image_gen?: ModelConfigSectionUpdate;
}

export interface EnvInfoResponse {
  environment: string;
  env_file: string;
  env_file_exists: boolean;
}

export interface DirEntry {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
}

export interface BrowseDirResponse {
  path: string;
  absolute_path: string;
  entries: DirEntry[];
}

export interface FileContentResponse {
  path: string;
  content: string;
  encoding?: 'utf-8' | 'base64';
}

// ============ Per-Agent LLM / ImageGen Config ============

export interface ResolvedLLMConfig {
  provider: string;
  base_url: string;
  api_key_masked: string;
  model: string;
  is_default: boolean;
  source: 'global' | 'agent_yaml' | 'runtime_override';
}

export interface ResolvedImageGenConfig {
  provider: string;
  base_url: string;
  api_key_masked: string;
  model_id: string;
  is_default: boolean;
  source: 'global' | 'agent_yaml' | 'runtime_override';
}

export interface AgentLLMConfigUpdate {
  provider?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  model?: string | null;
  use_default?: boolean;
}

export interface AgentImageGenConfigUpdate {
  provider?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  model_id?: string | null;
  use_default?: boolean;
}

export interface AgentModelConfigTestResponse {
  success: boolean;
  latency_ms: number;
  error?: string | null;
}
