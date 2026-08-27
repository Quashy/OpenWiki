import { apiClient } from "./client";

export type Role = "admin" | "editor" | "viewer";
export type KnowledgeBaseType = "document" | "wiki";

export type User = {
  id: string;
  username: string;
  created_at: string;
};

export type Workspace = {
  id: string;
  name: string;
  created_by: string;
  created_at: string;
};

export type WorkspaceMember = {
  id: string;
  workspace_id: string;
  user: User;
  role: Role;
  created_at: string;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type AuthResponse = {
  user: User;
  workspace?: Workspace | null;
  membership?: WorkspaceMember | null;
  tokens: TokenPair;
};

export type OllamaModel = {
  tag: string;
  digest: string;
  capabilities: string[];
  embedding_dim: number | null;
  usable_for_v1: boolean;
  unusable_reason:
    | "network_error"
    | "model_not_found"
    | "not_embedding_model"
    | "dimension_incompatible"
    | "probe_failed"
    | null;
};

export type ChunkingConfig = {
  chunk_size: number;
  chunk_overlap: number;
  strategy: "header_aware";
};

export type WikiConfig = {
  auto_ingest: boolean;
  llm_timeout_seconds?: number;
  llm_max_retries?: number;
  temperature?: number;
};

export type KnowledgeBase = {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  type: KnowledgeBaseType;
  status: "active" | "building" | "disabled" | "embedding_incompatible";
  embedding_provider: "ollama";
  embedding_model_tag: string;
  embedding_model_digest: string;
  embedding_dim: 1024;
  chunking_config?: ChunkingConfig | null;
  wiki_config?: WikiConfig | null;
  document_count?: number;
  page_count?: number;
  bound_source_kbs?: Array<Pick<KnowledgeBase, "id" | "name" | "type" | "status">>;
  created_at: string;
  updated_at: string;
};

export type LlmConfig = {
  provider: "openai" | "deepseek";
  model: string;
  base_url: string;
  api_key_configured: boolean;
  api_key_masked: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  updated_at: string;
};

export type OllamaConfig = {
  base_url: string;
  updated_at: string;
};

export type ModelTestResult = {
  ok: boolean;
  code: string;
  message: string;
  latency_ms: number;
};

export async function register(payload: {
  username: string;
  password: string;
}): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/register", payload);
  return response.data;
}

export async function login(payload: {
  username: string;
  password: string;
}): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/login", payload);
  return response.data;
}

export async function getCurrentWorkspace(): Promise<Workspace> {
  const response = await apiClient.get<Workspace>("/workspaces/current");
  return response.data;
}

export async function updateCurrentWorkspace(payload: { name: string }): Promise<Workspace> {
  const response = await apiClient.patch<Workspace>("/workspaces/current", payload);
  return response.data;
}

export async function listMembers(): Promise<WorkspaceMember[]> {
  const response = await apiClient.get<{ items: WorkspaceMember[] }>("/workspaces/current/members");
  return response.data.items;
}

export async function addMember(payload: {
  username: string;
  role: Role;
}): Promise<WorkspaceMember> {
  const response = await apiClient.post<WorkspaceMember>("/workspaces/current/members", payload);
  return response.data;
}

export async function updateMemberRole(userId: string, role: Role): Promise<WorkspaceMember> {
  const response = await apiClient.patch<WorkspaceMember>(`/workspaces/current/members/${userId}`, {
    role,
  });
  return response.data;
}

export async function removeMember(userId: string): Promise<void> {
  await apiClient.delete(`/workspaces/current/members/${userId}`);
}

export async function listKnowledgeBases(params: {
  type?: KnowledgeBaseType;
  q?: string;
} = {}): Promise<KnowledgeBase[]> {
  const response = await apiClient.get<{ items: KnowledgeBase[] }>("/kbs", { params });
  return response.data.items;
}

export async function createKnowledgeBase(payload:
  | {
      type: "document";
      name: string;
      description: string;
      embedding_model_tag: string;
      chunking_config?: ChunkingConfig;
    }
  | {
      type: "wiki";
      name: string;
      description: string;
      embedding_model_tag: string;
      source_knowledge_base_ids: string[];
      wiki_config?: WikiConfig;
    }): Promise<KnowledgeBase> {
  const response = await apiClient.post<KnowledgeBase>("/kbs", payload);
  return response.data;
}

export async function updateKnowledgeBase(
  id: string,
  payload: Partial<Pick<KnowledgeBase, "name" | "description" | "status" | "chunking_config" | "wiki_config">>,
): Promise<KnowledgeBase> {
  const response = await apiClient.patch<KnowledgeBase>(`/kbs/${id}`, payload);
  return response.data;
}

export async function getKnowledgeBase(id: string): Promise<KnowledgeBase> {
  const response = await apiClient.get<KnowledgeBase>(`/kbs/${id}`);
  return response.data;
}

export async function deleteKnowledgeBase(id: string): Promise<void> {
  await apiClient.delete(`/kbs/${id}`);
}

export async function bindSourceKnowledgeBase(kbId: string, sourceKbId: string): Promise<void> {
  await apiClient.post(`/kbs/${kbId}/bindings`, { source_kb_id: sourceKbId });
}

export async function unbindSourceKnowledgeBase(kbId: string, sourceKbId: string): Promise<void> {
  await apiClient.delete(`/kbs/${kbId}/bindings/${sourceKbId}`);
}

export async function getLlmConfig(): Promise<LlmConfig> {
  const response = await apiClient.get<LlmConfig>("/admin/llm-config");
  return response.data;
}

export async function updateLlmConfig(
  payload: Omit<LlmConfig, "api_key_configured" | "api_key_masked" | "updated_at"> & {
    api_key?: string;
  },
): Promise<LlmConfig> {
  const response = await apiClient.put<LlmConfig>("/admin/llm-config", payload);
  return response.data;
}

export async function testLlmConfig(): Promise<ModelTestResult> {
  const response = await apiClient.post<ModelTestResult>("/admin/llm-config/test");
  return response.data;
}

export async function getOllamaConfig(): Promise<OllamaConfig> {
  const response = await apiClient.get<OllamaConfig>("/admin/ollama-config");
  return response.data;
}

export async function updateOllamaConfig(base_url: string): Promise<OllamaConfig> {
  const response = await apiClient.put<OllamaConfig>("/admin/ollama-config", { base_url });
  return response.data;
}

export async function listOllamaModels(): Promise<OllamaModel[]> {
  const response = await apiClient.get<{ items: OllamaModel[] }>("/admin/ollama/models");
  return response.data.items;
}

export async function probeOllamaModel(tag: string): Promise<OllamaModel> {
  const response = await apiClient.post<OllamaModel>("/admin/ollama/models/probe", { tag });
  return response.data;
}
