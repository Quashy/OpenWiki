import { apiClient } from "./client";

export type WikiPageType = "index" | "source" | "entity" | "concept" | "overview" | "analysis";

export type WikiPageSummary = {
  id: string;
  kb_id: string;
  slug: string;
  title: string;
  page_type: WikiPageType;
  summary: string;
  category_path: string[];
  aliases: string[];
  source_refs: string[];
  updated_at: string;
};

export type WikiPage = WikiPageSummary & {
  content: string;
  current_revision_id: string;
  manual_edit_warning?: boolean;
  created_at: string;
};

export type WikiPageTreeNode = {
  name: string;
  path: string[];
  pages: WikiPageSummary[];
  children: WikiPageTreeNode[];
};

export type WikiGraphNode = {
  id: string;
  name: string;
  slug: string;
  entity_type: string;
  wiki_page_id?: string | null;
};

export type WikiGraphEdge = {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  source_chunk_id?: string | null;
};

export type WikiGraph = {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
};

export type WikiPageSourceChunk = {
  id: string;
  seq: number;
  header_path: string[];
  content: string;
  start_pos: number;
  end_pos: number;
};

export type WikiPageSource = {
  document_id: string;
  filename: string;
  status: string;
  precise: boolean;
  chunks: WikiPageSourceChunk[];
};

export async function ingestWiki(kbId: string, documentIds?: string[]): Promise<{ task_id: string }> {
  const response = await apiClient.post<{ task_id: string }>(`/wiki/${kbId}/ingest`, {
    document_ids: documentIds,
  });
  return response.data;
}

export async function rebuildWiki(kbId: string): Promise<{ task_id: string }> {
  const response = await apiClient.post<{ task_id: string }>(`/wiki/${kbId}/rebuild`, {
    confirm: "REBUILD",
  });
  return response.data;
}

export async function listWikiPages(params: {
  kbId: string;
  q?: string;
  page_type?: WikiPageType | "";
}): Promise<{ items: WikiPageSummary[]; tree: WikiPageTreeNode[] }> {
  const { kbId, ...query } = params;
  const response = await apiClient.get<{ items: WikiPageSummary[]; tree: WikiPageTreeNode[] }>(`/wiki/${kbId}/pages`, {
    params: query,
  });
  return response.data;
}

export async function getWikiPage(pageId: string): Promise<WikiPage> {
  const response = await apiClient.get<WikiPage>(`/wiki-pages/${pageId}`);
  return response.data;
}

export async function getWikiPageSources(pageId: string): Promise<WikiPageSource[]> {
  const response = await apiClient.get<{ items: WikiPageSource[] }>(`/wiki-pages/${pageId}/sources`);
  return response.data.items;
}

export async function getWikiGraph(params: {
  kbId: string;
  entity_type?: string;
  relation_type?: string;
}): Promise<WikiGraph> {
  const { kbId, ...query } = params;
  const response = await apiClient.get<WikiGraph>(`/wiki/${kbId}/graph`, { params: query });
  return response.data;
}
