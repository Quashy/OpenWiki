import {
  Button,
  Chip,
  Divider,
  Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownTrigger,
  ScrollShadow,
  Select,
  SelectItem,
  Spinner,
  Textarea,
  Tooltip,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  FileText,
  MoreHorizontal,
  Network,
  PenLine,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { listKnowledgeBases } from "../api/m1";
import {
  createChatSession,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
  streamChatAnswer,
  updateChatSession,
  type ChatMessage,
  type ChatSession,
  type Citation,
} from "../api/m5";
import { firstKey } from "../app/navigation";

type LocalMessage = ChatMessage | {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  trace_id?: string | null;
  created_at: string;
};

export function ChatPage({ onOpenWikiPage }: { onOpenWikiPage?: (pageId: string) => void }) {
  const queryClient = useQueryClient();
  const [selectedKbId, setSelectedKbId] = useState("");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [question, setQuestion] = useState("");
  const [draftMessages, setDraftMessages] = useState<LocalMessage[]>([]);
  const [progress, setProgress] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState("");

  const { data: knowledgeBases = [], isLoading: loadingKbs } = useQuery({
    queryKey: ["kbs", "chat"],
    queryFn: () => listKnowledgeBases(),
  });
  const activeKb = useMemo(() => knowledgeBases.find((kb) => kb.id === selectedKbId), [knowledgeBases, selectedKbId]);

  useEffect(() => {
    if (!selectedKbId && knowledgeBases.length > 0) {
      const firstActive = knowledgeBases.find((kb) => kb.status === "active") ?? knowledgeBases[0];
      setSelectedKbId(firstActive.id);
    }
  }, [knowledgeBases, selectedKbId]);

  const { data: sessions = [], isLoading: loadingSessions } = useQuery({
    queryKey: ["chat-sessions", selectedKbId],
    queryFn: () => listChatSessions(selectedKbId),
    enabled: Boolean(selectedKbId),
  });

  useEffect(() => {
    if (!activeSessionId && sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    }
    if (activeSessionId && sessions.length > 0 && !sessions.some((item) => item.id === activeSessionId)) {
      setActiveSessionId(sessions[0].id);
    }
    if (sessions.length === 0) {
      setActiveSessionId("");
    }
  }, [activeSessionId, sessions]);

  const { data: serverMessages = [], isLoading: loadingMessages } = useQuery({
    queryKey: ["chat-messages", activeSessionId],
    queryFn: () => listChatMessages(activeSessionId),
    enabled: Boolean(activeSessionId),
  });

  useEffect(() => {
    setDraftMessages([]);
    setProgress("");
    setStreamError("");
  }, [activeSessionId]);

  const messages = draftMessages.length > 0 ? draftMessages : serverMessages;

  const createMutation = useMutation({
    mutationFn: () => createChatSession({ kb_id: selectedKbId }),
    onSuccess: (session) => {
      setActiveSessionId(session.id);
      queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] });
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) => updateChatSession(sessionId, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteChatSession(sessionId),
    onSuccess: () => {
      setActiveSessionId("");
      queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] });
    },
  });

  async function ensureSession(): Promise<ChatSession> {
    const existing = sessions.find((item) => item.id === activeSessionId);
    if (existing) return existing;
    const created = await createChatSession({ kb_id: selectedKbId });
    setActiveSessionId(created.id);
    await queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] });
    return created;
  }

  async function sendQuestion() {
    const clean = question.trim();
    if (!clean || !selectedKbId || streaming) return;
    setQuestion("");
    setStreamError("");
    setProgress("");
    setStreaming(true);

    try {
      const chatSession = await ensureSession();
      const userMessage: LocalMessage = {
        id: `local-user-${Date.now()}`,
        session_id: chatSession.id,
        role: "user",
        content: clean,
        citations: [],
        created_at: new Date().toISOString(),
      };
      const assistantMessage: LocalMessage = {
        id: `local-assistant-${Date.now()}`,
        session_id: chatSession.id,
        role: "assistant",
        content: "",
        citations: [],
        trace_id: null,
        created_at: new Date().toISOString(),
      };
      setDraftMessages([...serverMessages, userMessage, assistantMessage]);

      await streamChatAnswer(chatSession.id, clean, {
        onProgress: (payload) => setProgress(payload.message ?? payload.stage ?? ""),
        onToken: (content) => {
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id ? { ...item, content: item.content + content } : item,
            ),
          );
        },
        onDone: (payload) => {
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id
                ? { ...item, id: payload.message_id, citations: payload.citations, trace_id: payload.trace_id }
                : item,
            ),
          );
        },
        onError: (payload) => {
          setStreamError(payload.message ?? "问答失败");
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["chat-messages", chatSession.id] });
      await queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] });
      setDraftMessages([]);
    } catch {
      setStreamError("问答请求失败，请检查模型与知识库状态。");
    } finally {
      setStreaming(false);
      setProgress("");
    }
  }

  function renameSession(session: ChatSession) {
    const title = window.prompt("重命名会话", session.title)?.trim();
    if (title) renameMutation.mutate({ sessionId: session.id, title });
  }

  return (
    <section className="-m-4 flex min-h-[calc(100vh-3.5rem)] flex-col overflow-hidden bg-default-50 sm:-m-6 lg:h-[calc(100vh-3.5rem)] lg:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-divider bg-background lg:w-[280px] lg:border-b-0 lg:border-r">
        <div className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-sm font-semibold">智能问答</h1>
              <p className="mt-1 text-xs text-default-500">单 KB 会话与引用问答</p>
            </div>
            <Tooltip content="新建会话">
              <Button
                isIconOnly
                size="sm"
                variant="flat"
                isDisabled={!selectedKbId || createMutation.isPending}
                onPress={() => createMutation.mutate()}
                aria-label="新建会话"
              >
                <Plus size={16} aria-hidden="true" />
              </Button>
            </Tooltip>
          </div>
          <Select
            label="查询知识库"
            placeholder={loadingKbs ? "加载中" : "选择知识库"}
            size="sm"
            selectedKeys={selectedKbId ? new Set([selectedKbId]) : new Set([])}
            onSelectionChange={(keys) => {
              setSelectedKbId(firstKey(keys, ""));
              setActiveSessionId("");
            }}
            isDisabled={loadingKbs || knowledgeBases.length === 0 || streaming}
          >
            {knowledgeBases.map((kb) => (
              <SelectItem key={kb.id} textValue={kb.name}>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate">{kb.name}</span>
                  <Chip size="sm" variant="flat">
                    {kb.type === "wiki" ? "Wiki KB" : "Source KB"}
                  </Chip>
                </div>
              </SelectItem>
            ))}
          </Select>
        </div>
        <Divider />
        <ScrollShadow className="max-h-56 flex-1 p-3 lg:max-h-none">
          {loadingSessions ? (
            <div className="grid min-h-32 place-items-center">
              <Spinner size="sm" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="grid min-h-32 place-items-center rounded-md border border-dashed border-divider px-4 py-8 text-center">
              <div>
                <Bot className="mx-auto mb-3 text-default-300" size={28} aria-hidden="true" />
                <p className="text-sm font-medium text-default-600">暂无会话</p>
                <p className="mt-1 text-xs leading-5 text-default-500">选择知识库后新建会话或直接提问。</p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  active={session.id === activeSessionId}
                  onSelect={() => setActiveSessionId(session.id)}
                  onRename={() => renameSession(session)}
                  onDelete={() => deleteMutation.mutate(session.id)}
                />
              ))}
            </div>
          )}
        </ScrollShadow>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-divider bg-background px-4 sm:px-6">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">{activeKb?.name ?? "选择知识库，开始提问"}</h2>
            <p className="mt-0.5 truncate text-xs text-default-500">Dense + Sparse + GraphRAG，Top-8 证据回答。</p>
          </div>
          <Chip color={activeKb?.status === "active" ? "primary" : "default"} variant="flat">
            {activeKb?.status === "active" ? "可检索" : "不可检索"}
          </Chip>
        </div>

        <ScrollShadow className="flex-1">
          <div className="mx-auto flex min-h-[420px] w-full max-w-4xl flex-col gap-4 px-4 py-6 sm:px-6 lg:min-h-[calc(100vh-12rem)]">
            {loadingMessages && activeSessionId ? (
              <div className="grid flex-1 place-items-center">
                <Spinner size="sm" />
              </div>
            ) : messages.length === 0 ? (
              <div className="grid flex-1 place-items-center text-center">
                <div>
                  <span className="mx-auto grid size-14 place-items-center rounded-md bg-primary/10 text-primary">
                    <Bot size={28} aria-hidden="true" />
                  </span>
                  <h3 className="mt-4 text-lg font-semibold">开始单 KB 问答</h3>
                  <p className="mt-2 max-w-md text-sm leading-6 text-default-500">
                    回答会流式返回，并在底部列出进入上下文的来源引用。
                  </p>
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <MessageBubble key={message.id} message={message} onOpenWikiPage={onOpenWikiPage} />
              ))
            )}
          </div>
        </ScrollShadow>

        <div className="border-t border-divider bg-background px-4 py-4 sm:px-6">
          <div className="mx-auto max-w-4xl">
            {progress || streamError ? (
              <div className="mb-2 flex items-center justify-between gap-3 text-xs">
                <span className={streamError ? "text-danger" : "text-default-500"}>
                  {streamError || progress}
                </span>
                {streaming ? <Spinner size="sm" /> : null}
              </div>
            ) : null}
            <div className="flex items-end gap-3">
              <Textarea
                minRows={1}
                maxRows={5}
                placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                variant="bordered"
                value={question}
                onValueChange={setQuestion}
                isDisabled={!selectedKbId || activeKb?.status !== "active" || streaming}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendQuestion();
                  }
                }}
                classNames={{ inputWrapper: "min-h-11" }}
              />
              <Button
                isIconOnly
                color="primary"
                className="h-11 w-11 shrink-0"
                isDisabled={!question.trim() || !selectedKbId || activeKb?.status !== "active" || streaming}
                isLoading={streaming}
                onPress={sendQuestion}
                aria-label="发送问题"
              >
                <Send size={18} aria-hidden="true" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function SessionRow({
  session,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  session: ChatSession;
  active: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  return (
    <div className={`flex items-center gap-2 rounded-md border px-2 py-2 ${active ? "border-primary bg-primary/5" : "border-transparent hover:bg-default-100"}`}>
      <button className="min-w-0 flex-1 text-left" type="button" onClick={onSelect}>
        <p className="truncate text-sm font-medium">{session.title}</p>
        <p className="mt-0.5 text-xs text-default-500">{new Date(session.updated_at).toLocaleString()}</p>
      </button>
      <Dropdown placement="bottom-end">
        <DropdownTrigger>
          <Button isIconOnly size="sm" variant="light" aria-label="会话操作">
            <MoreHorizontal size={16} aria-hidden="true" />
          </Button>
        </DropdownTrigger>
        <DropdownMenu aria-label="会话操作">
          <DropdownItem key="rename" startContent={<PenLine size={16} aria-hidden="true" />} onPress={onRename}>
            重命名
          </DropdownItem>
          <DropdownItem key="delete" color="danger" startContent={<Trash2 size={16} aria-hidden="true" />} onPress={onDelete}>
            删除
          </DropdownItem>
        </DropdownMenu>
      </Dropdown>
    </div>
  );
}

function MessageBubble({
  message,
  onOpenWikiPage,
}: {
  message: LocalMessage;
  onOpenWikiPage?: (pageId: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[86%] rounded-md border px-4 py-3 ${isUser ? "border-primary/20 bg-primary text-primary-foreground" : "border-divider bg-background"}`}>
        <div className="whitespace-pre-wrap text-sm leading-6">{message.content || " "}</div>
        {!isUser && message.citations.length > 0 ? (
          <div className="mt-3 space-y-2 border-t border-divider pt-3">
            {message.citations.map((citation) => (
              <CitationRow key={`${message.id}-${citation.id}`} citation={citation} onOpenWikiPage={onOpenWikiPage} />
            ))}
          </div>
        ) : null}
        {!isUser && message.trace_id ? (
          <p className="mt-2 truncate text-[11px] text-default-400">trace_id: {message.trace_id}</p>
        ) : null}
      </div>
    </article>
  );
}

function CitationRow({
  citation,
  onOpenWikiPage,
}: {
  citation: Citation;
  onOpenWikiPage?: (pageId: string) => void;
}) {
  const canOpenWiki = citation.source_type === "wiki_page" && citation.wiki_page_id && onOpenWikiPage;
  return (
    <button
      type="button"
      className="w-full rounded-md border border-divider bg-default-50 px-3 py-2 text-left disabled:cursor-default"
      disabled={!canOpenWiki}
      onClick={() => {
        if (canOpenWiki) onOpenWikiPage(citation.wiki_page_id as string);
      }}
    >
      <div className="flex items-center gap-2">
        {citation.source_type === "wiki_page" ? (
          <Network size={14} className="shrink-0 text-primary" aria-hidden="true" />
        ) : (
          <FileText size={14} className="shrink-0 text-default-500" aria-hidden="true" />
        )}
        <span className="shrink-0 text-xs font-semibold">[{citation.id}]</span>
        <span className="truncate text-xs font-medium">{citation.title || citation.filename || "来源片段"}</span>
      </div>
      {citation.header_path?.length ? (
        <p className="mt-1 truncate text-[11px] text-default-500">{citation.header_path.join(" / ")}</p>
      ) : null}
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-default-600">{citation.snippet}</p>
    </button>
  );
}
