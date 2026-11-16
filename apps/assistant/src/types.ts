export type Situation = "implementado" | "parcial" | "planejado";

export type ModuleStatus = { name: string; situacao: Situation; fase: number; resumo: string };
export type Unavailable = { situacao: "nao_implementado"; fase: number; mensagem?: string };

export type SystemStatus = {
  service: string;
  version: string;
  environment: string;
  started_at: number;
  health: { status: "ok" | "degraded" | "failed"; checks: Array<{ name: string; ok: boolean; critical: boolean; detail: string; elapsed_ms: number }> };
  database: { file: string | null; revision: string | null; head: string | null; size_bytes: number | null; counts: Record<"conversations" | "messages" | "memories" | "projects", number> };
  modules: ModuleStatus[];
  ai: Unavailable;
  voice: Unavailable;
};

export type Resources = {
  process: { rss_mb: number; cpu_percent: number; threads: number; uptime_s: number };
  system: { cpu_count: number; cpu_percent: number; memory_total_mb: number; memory_used_percent: number };
  storage: { database_bytes: number | null; disk_free_mb: number | null };
  measured_at: number;
};

export type ProcessSettings = {
  environment: string; data_dir: string; api_host: string; api_port: number; log_level: string;
  log_to_file: boolean; migrate_on_start: boolean; editable: boolean; note: string;
};

export type Activity = { id: number; kind: string; origin: string; title: string; state: string; ref_type: string; ref_id: string; at: string };

export type ConversationSummary = {
  id: number; title: string; project_id: number | null; started_at: string; updated_at: string;
  archived: boolean; message_count: number; preview: string;
};
export type Message = { id: number; role: "user" | "assistant" | "system" | "tool"; content: string; provenance: Record<string, unknown>; provider_id: number | null; created_at: string };
export type Conversation = ConversationSummary & { messages: Message[] };
export type SendResult = { message: Message; reply: { status: "indisponivel"; code: string; message: string } };

export type Project = {
  id: number; name: string; description: string; status: "active" | "archived"; created_at: string; updated_at: string;
  archived_at: string | null; conversation_count: number; memory_count: number;
};

export type MemoryKind = "fact" | "episode" | "procedure" | "note" | "reminder";
export type Memory = {
  id: number; kind: MemoryKind; kind_label: string; content: string; project_id: number | null; source: string;
  importance: number; created_at: string; updated_at: string; deleted_at: string | null;
};

export type Preference = { label: string; value: string | boolean; default: string | boolean; choices: string[] | null; source: string; updated_at: string | null };
export type Preferences = Record<"nome" | "tratamento" | "movimento_reduzido" | "densidade" | "tamanho_texto", Preference>;

export type AiStatus = {
  gateway: Unavailable;
  providers: Array<{ id: number; name: string; kind: string; enabled: boolean; default_model: string; allows_private: boolean; has_credential: boolean }>;
  selection_allowed: boolean;
};

export type ToolsOverview = {
  executor: Unavailable;
  tools: Array<{ name: string; category: string; risk: string; enabled: boolean; description: string }>;
  executions: Array<{ id: number; tool: string; status: string; verified: boolean | null; requested_at: string }>;
};
