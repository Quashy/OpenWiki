import {
  Button,
  Chip,
  Divider,
  Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownTrigger,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
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
  ExternalLink,
  FileText,
  Hash,
  MoreHorizontal,
  Network,
  PenLine,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listKnowledgeBases } from "../api/m1";
import { listWikiPages, type WikiPageSummary } from "../api/m3";
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
import { MarkdownRenderer } from "../components/MarkdownRenderer";

type LocalMessage = ChatMessage | {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  trace_id?: string | null;
  status?: string;
  error?: string;
  created_at: string;
};

export function ChatPage({ onOpenWikiPage }: { onOpenWikiPage?: (pageId: string) => void }) {
  const queryClient = useQueryClient();
  const [selectedKbId, setSelectedKbId] = useState("");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [question, setQuestion] = useState("");
  const [draftMessages, setDraftMessages] = useState<LocalMessage[]>([]);
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
        status: "正在准备回答...",
        created_at: new Date().toISOString(),
      };
      setDraftMessages([...serverMessages, userMessage, assistantMessage]);

      let receivedStreamError = false;
      await streamChatAnswer(chatSession.id, clean, {
        onProgress: (payload) => {
          const nextStatus = payload.message ?? payload.stage ?? "";
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id ? { ...item, status: nextStatus } : item,
            ),
          );
        },
        onToken: (content) => {
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id ? { ...item, content: item.content + content, status: "" } : item,
            ),
          );
        },
        onDone: (payload) => {
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id
                ? { ...item, id: payload.message_id, citations: payload.citations, trace_id: payload.trace_id, status: "", error: "" }
                : item,
            ),
          );
        },
        onError: (payload) => {
          const message = payload.message ?? "问答失败";
          receivedStreamError = true;
          setDraftMessages((current) =>
            current.map((item) =>
              item.id === assistantMessage.id ? { ...item, status: "", error: message } : item,
            ),
          );
        },
      });
      if (receivedStreamError) return;
      await queryClient.invalidateQueries({ queryKey: ["chat-messages", chatSession.id] });
      await queryClient.invalidateQueries({ queryKey: ["chat-sessions", selectedKbId] });
      setDraftMessages([]);
    } catch {
      setStreamError("问答请求失败，请检查模型与知识库状态。");
    } finally {
      setStreaming(false);
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
            {streamError ? (
              <div className="mb-2 flex items-center justify-between gap-3 text-xs">
                <span className="text-danger">{streamError}</span>
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
  const status = !isUser && "status" in message ? message.status : "";
  const error = !isUser && "error" in message ? message.error : "";
  const visibleCitations = useMemo(
    () => citationsReferencedByAnswer(message.content, message.citations),
    [message.content, message.citations],
  );
  const [activeCitationId, setActiveCitationId] = useState<number | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const citationRefs = useRef(new Map<number, HTMLButtonElement>());
  const clearHighlightTimer = useRef<number | null>(null);
  const citationById = useMemo(() => new Map(visibleCitations.map((citation) => [citation.id, citation])), [visibleCitations]);
  const activateCitation = useCallback((citationId: number, scroll = false) => {
    setActiveCitationId(citationId);
    if (scroll) {
      citationRefs.current.get(citationId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      if (clearHighlightTimer.current) window.clearTimeout(clearHighlightTimer.current);
      clearHighlightTimer.current = window.setTimeout(() => setActiveCitationId(null), 1600);
    }
  }, []);
  const answerMarkdown = useMemo(() => linkAnswerCitations(message.content, citationById), [message.content, citationById]);
  const renderCitationLink = useCallback(
    (citationId: number, children: ReactNode) => {
      const citation = citationById.get(citationId);
      if (!citation) return <span>{children}</span>;
      const active = activeCitationId === citationId;
      return (
        <button
          type="button"
          className={`mx-0.5 inline-flex min-h-5 min-w-5 translate-y-[-0.18em] items-center justify-center rounded-full border px-1 text-[11px] font-semibold leading-none transition-colors focus:outline-none focus:ring-2 focus:ring-primary/35 ${
            active
              ? "border-primary bg-primary text-primary-foreground"
              : "border-primary/30 bg-primary/10 text-primary hover:border-primary hover:bg-primary/15"
          }`}
          aria-label={`查看引用 ${citationId}：${citationTitle(citation)}`}
          onClick={() => activateCitation(citationId, true)}
          onMouseEnter={() => activateCitation(citationId)}
          onMouseLeave={() => setActiveCitationId(null)}
          onFocus={() => activateCitation(citationId)}
          onBlur={() => setActiveCitationId(null)}
        >
          {children}
        </button>
      );
    },
    [activeCitationId, activateCitation, citationById],
  );

  useEffect(() => {
    return () => {
      if (clearHighlightTimer.current) window.clearTimeout(clearHighlightTimer.current);
    };
  }, []);

  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[86%] rounded-md border px-4 py-3 ${isUser ? "border-primary/20 bg-primary text-primary-foreground" : "border-divider bg-background"}`}>
        {!isUser && (status || error) ? (
          <div className={`mb-2 flex items-center gap-2 rounded-md px-3 py-2 text-xs ${error ? "bg-danger/10 text-danger" : "bg-default-100 text-default-500"}`}>
            {status ? <Spinner size="sm" /> : null}
            <span>{error || status}</span>
          </div>
        ) : null}
        {isUser ? (
          <div className="whitespace-pre-wrap text-sm leading-6">{message.content || " "}</div>
        ) : (
          <div className="text-sm leading-6">
            <MarkdownRenderer content={answerMarkdown || " "} variant="chat" renderCitationLink={renderCitationLink} />
          </div>
        )}
        {!isUser && visibleCitations.length > 0 ? (
          <div className="mt-3 space-y-2 border-t border-divider pt-3">
            {visibleCitations.map((citation) => (
              <CitationRow
                key={`${message.id}-${citation.id}`}
                citation={citation}
                active={activeCitationId === citation.id}
                refCallback={(element) => {
                  if (element) citationRefs.current.set(citation.id, element);
                  else citationRefs.current.delete(citation.id);
                }}
                onFocusCitation={() => activateCitation(citation.id)}
                onBlurCitation={() => setActiveCitationId(null)}
                onOpenCitation={() => setSelectedCitation(citation)}
              />
            ))}
          </div>
        ) : null}
        {!isUser && message.trace_id ? (
          <p className="mt-2 truncate text-[11px] text-default-400">trace_id: {message.trace_id}</p>
        ) : null}
      </div>
      {!isUser ? (
        <CitationDetailDrawer
          citation={selectedCitation}
          onClose={() => setSelectedCitation(null)}
          onOpenWikiPage={onOpenWikiPage}
        />
      ) : null}
    </article>
  );
}

function CitationRow({
  citation,
  active,
  refCallback,
  onFocusCitation,
  onBlurCitation,
  onOpenCitation,
}: {
  citation: Citation;
  active: boolean;
  refCallback: (element: HTMLButtonElement | null) => void;
  onFocusCitation: () => void;
  onBlurCitation: () => void;
  onOpenCitation: () => void;
}) {
  return (
    <button
      ref={refCallback}
      type="button"
      className={`w-full rounded-md border px-3 py-2 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 ${
        active ? "border-primary bg-primary/10 shadow-sm" : "border-divider bg-default-50 hover:border-primary/40 hover:bg-default-100"
      }`}
      onClick={onOpenCitation}
      onMouseEnter={onFocusCitation}
      onMouseLeave={onBlurCitation}
      onFocus={onFocusCitation}
      onBlur={onBlurCitation}
      aria-label={`打开引用 ${citation.id} 详情`}
    >
      <div className="flex min-w-0 items-center gap-2">
        <SourceIcon citation={citation} />
        <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${active ? "bg-primary text-primary-foreground" : "bg-default-200 text-default-700"}`}>
          {citation.id}
        </span>
        <span className="min-w-0 flex-1 truncate text-xs font-medium">{citationTitle(citation)}</span>
        <Chip size="sm" variant="flat" color={citation.source_type === "wiki_page" ? "primary" : "default"}>
          {sourceTypeLabel(citation)}
        </Chip>
      </div>
      {citation.header_path?.length ? (
        <p className="mt-1 truncate text-[11px] text-default-500">{citation.header_path.join(" / ")}</p>
      ) : null}
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-default-600">{citation.snippet}</p>
    </button>
  );
}

function CitationDetailDrawer({
  citation,
  onClose,
  onOpenWikiPage,
}: {
  citation: Citation | null;
  onClose: () => void;
  onOpenWikiPage?: (pageId: string) => void;
}) {
  const canOpenWiki = citation?.source_type === "wiki_page" && citation.wiki_page_id && onOpenWikiPage;
  const pagesQuery = useQuery({
    queryKey: ["citation-wiki-pages", citation?.kb_id],
    queryFn: () => listWikiPages({ kbId: String(citation?.kb_id) }),
    enabled: Boolean(citation?.kb_id && citation.source_type === "wiki_page" && onOpenWikiPage),
    retry: false,
  });
  const wikiPages = pagesQuery.data?.items ?? [];
  const wikiPageBySlug = useMemo(
    () => new Map(wikiPages.map((page: WikiPageSummary) => [page.slug, page.id])),
    [wikiPages],
  );
  const openWikiSlug = useCallback(
    (slug: string) => {
      const pageId = wikiPageBySlug.get(slug);
      if (!pageId || !onOpenWikiPage) return;
      onOpenWikiPage(pageId);
      onClose();
    },
    [onClose, onOpenWikiPage, wikiPageBySlug],
  );

  return (
    <Modal
      isOpen={Boolean(citation)}
      onOpenChange={(open) => !open && onClose()}
      size="lg"
      scrollBehavior="inside"
      classNames={{
        wrapper: "items-stretch justify-end p-0 sm:p-3",
        base: "m-0 h-full max-h-full rounded-none sm:h-[calc(100vh-1.5rem)] sm:max-h-[calc(100vh-1.5rem)] sm:rounded-l-md sm:rounded-r-none",
      }}
    >
      <ModalContent>
        {citation ? (
          <>
            <ModalHeader className="flex items-start gap-3">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-default-100">
                <SourceIcon citation={citation} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{citationTitle(citation)}</span>
                <span className="mt-1 flex items-center gap-2 text-xs font-normal text-default-500">
                  <span>引用 {citation.id}</span>
                  <span>·</span>
                  <span>{sourceTypeLabel(citation)}</span>
                </span>
              </span>
            </ModalHeader>
            <ModalBody className="gap-4">
              {citation.header_path?.length ? (
                <section>
                  <h3 className="text-xs font-semibold text-default-500">路径</h3>
                  <p className="mt-1 rounded-md bg-default-100 px-3 py-2 text-sm leading-6 text-default-700">
                    {citation.header_path.join(" / ")}
                  </p>
                </section>
              ) : null}
              <section>
                <h3 className="text-xs font-semibold text-default-500">片段</h3>
                <div className="mt-1 rounded-md border border-divider bg-default-50 px-3 py-2">
                  <MarkdownRenderer
                    content={citation.snippet}
                    variant="citation"
                    pages={wikiPages}
                    onOpenSlug={openWikiSlug}
                  />
                </div>
              </section>
              <section className="grid gap-2 text-xs text-default-500">
                <MetaLine label="KB" value={citation.kb_id} />
                <MetaLine label="Chunk" value={citation.chunk_id} />
                <MetaLine label="文档" value={citation.document_id} />
                <MetaLine label="Wiki 页面" value={citation.wiki_page_id} />
              </section>
            </ModalBody>
            <ModalFooter>
              <Button variant="light" onPress={onClose}>关闭</Button>
              {canOpenWiki ? (
                <Button
                  color="primary"
                  startContent={<ExternalLink size={16} aria-hidden="true" />}
                  onPress={() => {
                    onOpenWikiPage(citation.wiki_page_id as string);
                    onClose();
                  }}
                >
                  打开 Wiki 页面
                </Button>
              ) : null}
            </ModalFooter>
          </>
        ) : null}
      </ModalContent>
    </Modal>
  );
}

function SourceIcon({ citation }: { citation: Citation }) {
  return citation.source_type === "wiki_page" ? (
    <Network size={14} className="shrink-0 text-primary" aria-hidden="true" />
  ) : (
    <FileText size={14} className="shrink-0 text-default-500" aria-hidden="true" />
  );
}

function MetaLine({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md bg-default-50 px-3 py-2">
      <Hash size={13} className="shrink-0 text-default-400" aria-hidden="true" />
      <span className="shrink-0 font-medium text-default-600">{label}</span>
      <span className="min-w-0 truncate font-mono">{value}</span>
    </div>
  );
}

function citationTitle(citation: Citation) {
  return citation.title || citation.filename || "来源片段";
}

function linkAnswerCitations(content: string, citationById: Map<number, Citation>) {
  if (!content || citationById.size === 0) return content;
  return content.replace(/\[(\d+)\]/g, (raw, idText: string) => {
    const citationId = Number(idText);
    if (!citationById.has(citationId)) return raw;
    return `[${idText}](citation:${citationId})`;
  });
}

function citationsReferencedByAnswer(content: string, citations: Citation[]) {
  const referencedIds = citationIdsInText(content);
  return citations.filter((citation) => referencedIds.has(citation.id));
}

function citationIdsInText(content: string) {
  return new Set([...content.matchAll(/\[(\d+)\]/g)].map((match) => Number(match[1])));
}

function sourceTypeLabel(citation: Citation) {
  return citation.source_type === "wiki_page" ? "Wiki" : "文档";
}
