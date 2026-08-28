import { apiClient } from "./client";

export type DocumentStatus = "pending" | "running" | "completed" | "failed";

export type Tag = {
  id: string;
  kb_id: string;
  name: string;
};

export type Document = {
  id: string;
  kb_id: string;
  filename: string;
  file_hash: string;
  file_size: number;
  status: DocumentStatus;
  error_message?: string | null;
  chunk_count: number;
  tags?: Tag[];
  created_by: string;
  created_by_username: string;
  created_at: string;
  updated_at: string;
};

export type Chunk = {
  id: string;
  document_id?: string | null;
  kb_id: string;
  content: string;
  header_path: string[];
  seq: number;
  start_pos: number;
  end_pos: number;
  chunk_type: "text" | "wiki_page";
  source_page_id?: string | null;
  created_at: string;
};

export type DocumentDetail = Document & {
  content: string;
  chunks: Chunk[];
};

export type Task = {
  id: string;
  kb_id: string;
  task_type: "document_process" | "wiki_ingest" | "wiki_rebuild";
  status: "pending" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  payload: Record<string, unknown>;
  error?: { code: string; message: string; details?: Record<string, unknown> } | null;
  created_at: string;
  updated_at: string;
};

export type ChunkPreviewItem = {
  content: string;
  header_path: string[];
  seq: number;
  start_pos: number;
  end_pos: number;
  char_count: number;
};

export async function listDocuments(params: {
  kbId: string;
  q?: string;
  tag_id?: string;
  status?: DocumentStatus | "";
  sort?: string;
}): Promise<Document[]> {
  const { kbId, ...query } = params;
  const response = await apiClient.get<{ items: Document[] }>(`/kbs/${kbId}/documents`, { params: query });
  return response.data.items;
}

export async function getDocument(documentId: string): Promise<DocumentDetail> {
  const response = await apiClient.get<DocumentDetail>(`/documents/${documentId}`);
  return response.data;
}

export async function uploadDocuments(payload: {
  kbId: string;
  files: File[];
  tagIds: string[];
}): Promise<{ documents: Document[]; task_ids: string[] }> {
  const form = new FormData();
  payload.files.forEach((file) => form.append("files", file));
  payload.tagIds.forEach((tagId) => form.append("tag_ids", tagId));
  const response = await apiClient.post<{ documents: Document[]; task_ids: string[] }>(`/kbs/${payload.kbId}/documents/upload`, form);
  return response.data;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiClient.delete(`/documents/${documentId}`);
}

export async function retryDocument(documentId: string): Promise<{ task_id: string }> {
  const response = await apiClient.post<{ task_id: string }>(`/documents/${documentId}/retry`);
  return response.data;
}

export async function listTags(kbId: string): Promise<Tag[]> {
  const response = await apiClient.get<{ items: Tag[] }>(`/kbs/${kbId}/tags`);
  return response.data.items;
}

export async function createTag(kbId: string, name: string): Promise<Tag> {
  const response = await apiClient.post<Tag>(`/kbs/${kbId}/tags`, { name });
  return response.data;
}

export async function updateTag(kbId: string, tagId: string, name: string): Promise<Tag> {
  const response = await apiClient.patch<Tag>(`/kbs/${kbId}/tags/${tagId}`, { name });
  return response.data;
}

export async function deleteTag(kbId: string, tagId: string): Promise<void> {
  await apiClient.delete(`/kbs/${kbId}/tags/${tagId}`);
}

export async function getTask(taskId: string): Promise<Task> {
  const response = await apiClient.get<Task>(`/tasks/${taskId}`);
  return response.data;
}

export async function previewChunks(payload: {
  kbId: string;
  content: string;
  content_type: "markdown" | "text";
  chunking_config?: { chunk_size: number; chunk_overlap: number; strategy: "header_aware" };
}): Promise<ChunkPreviewItem[]> {
  const { kbId, ...body } = payload;
  const response = await apiClient.post<{ items: ChunkPreviewItem[] }>(`/kbs/${kbId}/chunk-preview`, body);
  return response.data.items;
}
