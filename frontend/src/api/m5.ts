import { getStoredAccessToken } from "../stores/authStorage";
import { apiClient } from "./client";

export type ChatSession = {
  id: string;
  workspace_id: string;
  user_id: string;
  kb_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Citation = {
  id: number;
  source_type: "document" | "wiki_page";
  kb_id: string;
  document_id?: string | null;
  wiki_page_id?: string | null;
  chunk_id?: string | null;
  filename?: string | null;
  title?: string | null;
  header_path?: string[];
  snippet: string;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  trace_id?: string | null;
  token_usage?: Record<string, unknown>;
  created_at: string;
};

export async function createChatSession(payload: { kb_id: string; title?: string }): Promise<ChatSession> {
  const response = await apiClient.post<ChatSession>("/chat/sessions", payload);
  return response.data;
}

export async function listChatSessions(kbId?: string): Promise<ChatSession[]> {
  const response = await apiClient.get<{ items: ChatSession[] }>("/chat/sessions", {
    params: kbId ? { kb_id: kbId } : undefined,
  });
  return response.data.items;
}

export async function listChatMessages(sessionId: string): Promise<ChatMessage[]> {
  const response = await apiClient.get<{ items: ChatMessage[] }>(`/chat/sessions/${sessionId}/messages`, {
    params: { page_size: 100 },
  });
  return response.data.items;
}

export async function updateChatSession(sessionId: string, title: string): Promise<ChatSession> {
  const response = await apiClient.patch<ChatSession>(`/chat/sessions/${sessionId}`, { title });
  return response.data;
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/chat/sessions/${sessionId}`);
}

export async function streamChatAnswer(
  sessionId: string,
  question: string,
  handlers: {
    onProgress?: (payload: { stage?: string; message?: string }) => void;
    onToken?: (content: string) => void;
    onDone?: (payload: { message_id: string; citations: Citation[]; trace_id?: string | null }) => void;
    onError?: (payload: { code?: string; message?: string }) => void;
  },
): Promise<void> {
  const baseURL = String(apiClient.defaults.baseURL ?? "/api/v1").replace(/\/$/, "");
  const url = `${baseURL}/chat/sessions/${sessionId}/stream?question=${encodeURIComponent(question)}`;
  const token = getStoredAccessToken();
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok || !response.body) {
    throw new Error(`stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      handleSseBlock(block, handlers);
    }
  }
  if (buffer.trim()) {
    handleSseBlock(buffer, handlers);
  }
}

function handleSseBlock(
  block: string,
  handlers: {
    onProgress?: (payload: { stage?: string; message?: string }) => void;
    onToken?: (content: string) => void;
    onDone?: (payload: { message_id: string; citations: Citation[]; trace_id?: string | null }) => void;
    onError?: (payload: { code?: string; message?: string }) => void;
  },
) {
  const event = block
    .split("\n")
    .find((line) => line.startsWith("event:"))
    ?.replace("event:", "")
    .trim();
  const data = block
    .split("\n")
    .find((line) => line.startsWith("data:"))
    ?.replace("data:", "")
    .trim();
  if (!event || !data) return;
  const payload = JSON.parse(data);
  if (event === "progress") handlers.onProgress?.(payload);
  if (event === "token") handlers.onToken?.(String(payload.content ?? ""));
  if (event === "done") handlers.onDone?.(payload);
  if (event === "error") handlers.onError?.(payload);
}
