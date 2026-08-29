import {
  Alert,
  Button,
  Chip,
  Divider,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Progress,
  ScrollShadow,
  Select,
  SelectItem,
  Skeleton,
  Tab,
  Tabs,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, ChevronDown, ChevronRight, ExternalLink, FileText, GitBranch, Home, Layers3, Link2, LocateFixed, PanelRightOpen, RefreshCw, Search, Sparkles } from "lucide-react";
import { type MutableRefObject, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { listKnowledgeBases } from "../api/m1";
import { getDocument, getTask, type DocumentDetail, type Task } from "../api/m2";
import {
  getWikiPageSources,
  getWikiPage,
  ingestWiki,
  listWikiPages,
  rebuildWiki,
  type WikiPage,
  type WikiPageSource,
  type WikiPageSummary,
  type WikiPageType,
} from "../api/m3";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";
import { useAuthStore } from "../stores/authStore";

const pageTypeLabel: Record<WikiPageType, string> = {
  index: "索引",
  source: "来源",
  entity: "实体",
  concept: "概念",
  overview: "综述",
  analysis: "分析",
};

const pageTypeFilters: Array<{ key: WikiPageType | ""; label: string }> = [
  { key: "", label: "全部" },
  { key: "entity", label: "实体" },
  { key: "concept", label: "概念" },
  { key: "source", label: "来源" },
  { key: "analysis", label: "分析" },
];

export function WikiBrowserPage({ initialKbId, initialPageId }: { initialKbId?: string | null; initialPageId?: string | null }) {
  const { membership } = useAuthStore();
  const canIngest = membership?.role === "admin" || membership?.role === "editor";
  const [kbId, setKbId] = useState("");
  const [query, setQuery] = useState("");
  const [pageType, setPageType] = useState<WikiPageType | "">("");
  const [pageId, setPageId] = useState<string | null>(initialPageId ?? null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: wikiKbs = [], isLoading: loadingKbs } = useQuery({
    queryKey: ["kbs", "wiki"],
    queryFn: () => listKnowledgeBases({ type: "wiki" }),
  });

  useEffect(() => {
    if (!kbId && wikiKbs.length > 0) setKbId(wikiKbs[0].id);
  }, [kbId, wikiKbs]);

  useEffect(() => {
    if (initialKbId) setKbId(initialKbId);
  }, [initialKbId]);

  useEffect(() => {
    if (initialPageId) setPageId(initialPageId);
  }, [initialPageId]);

  const pagesQuery = useQuery({
    queryKey: ["wiki-pages", kbId, query, pageType],
    queryFn: () => listWikiPages({ kbId, q: query || undefined, page_type: pageType }),
    enabled: Boolean(kbId),
    retry: false,
  });
  const pages = pagesQuery.data?.items ?? [];
  const allPagesQuery = useQuery({
    queryKey: ["wiki-pages", kbId, "all"],
    queryFn: () => listWikiPages({ kbId }),
    enabled: Boolean(kbId),
    retry: false,
  });
  const allPages = allPagesQuery.data?.items ?? pages;
  const selectedPageId = pageId ?? pages[0]?.id ?? null;
  const selectedPage = useQuery({
    queryKey: ["wiki-page", selectedPageId],
    queryFn: () => getWikiPage(String(selectedPageId)),
    enabled: Boolean(selectedPageId),
    retry: false,
  });
  const taskQuery = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(String(taskId)),
    enabled: Boolean(taskId),
    refetchInterval: (result) => (result.state.data?.status === "pending" || result.state.data?.status === "running" ? 1500 : false),
  });
  const activeTask = taskQuery.data;

  useEffect(() => {
    if (activeTask?.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["wiki-pages", kbId] });
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
    }
  }, [activeTask?.status, kbId, queryClient]);

  const ingestMutation = useMutation({
    mutationFn: () => ingestWiki(kbId),
    onSuccess: (result) => setTaskId(result.task_id),
  });
  const rebuildMutation = useMutation({
    mutationFn: () => rebuildWiki(kbId),
    onSuccess: (result) => {
      setTaskId(result.task_id);
      queryClient.invalidateQueries({ queryKey: ["wiki-pages", kbId] });
    },
  });
  const currentKb = wikiKbs.find((item) => item.id === kbId);

  return (
    <section className="space-y-5">
      <PageHeader
        title="Wiki 浏览器"
        description="按目录浏览自动生成的 Wiki 页面，双链可直接跳转"
        action={
          canIngest && kbId ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="flat" startContent={<RefreshCw size={16} aria-hidden="true" />} isLoading={rebuildMutation.isPending} onPress={() => rebuildMutation.mutate()}>
                全量重建
              </Button>
              <Button color="primary" startContent={<Sparkles size={16} aria-hidden="true" />} isLoading={ingestMutation.isPending} onPress={() => ingestMutation.mutate()}>
                生成/更新
              </Button>
            </div>
          ) : null
        }
      />

      <div className="grid min-h-[calc(100vh-10rem)] gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="min-w-0 rounded-md border border-divider bg-background">
          <div className="space-y-3 p-3">
            <Select
              aria-label="选择 Wiki KB"
              placeholder={loadingKbs ? "加载中" : "选择 Wiki KB"}
              selectedKeys={kbId ? new Set([kbId]) : new Set([])}
              onSelectionChange={(keys) => {
                setKbId(firstKey(keys, ""));
                setPageId(null);
              }}
            >
              {wikiKbs.map((kb) => (
                <SelectItem key={kb.id}>{kb.name}</SelectItem>
              ))}
            </Select>
            <Input size="sm" placeholder="搜索页面" value={query} onValueChange={setQuery} startContent={<Search size={15} aria-hidden="true" />} />
            <div className="grid grid-cols-5 gap-1 rounded-md bg-default-100 p-1" role="group" aria-label="页面类型筛选">
              {pageTypeFilters.map((filter) => (
                <Button
                  key={filter.key || "all"}
                  className="h-8 min-w-0 px-1 text-xs"
                  color={pageType === filter.key ? "primary" : "default"}
                  variant={pageType === filter.key ? "solid" : "light"}
                  onPress={() => setPageType(filter.key)}
                >
                  {filter.label}
                </Button>
              ))}
            </div>
          </div>
          <Divider />
          {activeTask ? <TaskProgress task={activeTask} /> : null}
          <ScrollShadow className="h-[calc(100vh-23rem)] min-h-80 p-3">
            {pagesQuery.isLoading ? <LoadingTree /> : null}
            {pagesQuery.isError ? <Alert color="warning" variant="flat">Wiki 暂不可浏览，可能正在重建或尚未生成。</Alert> : null}
            {!pagesQuery.isLoading && !pagesQuery.isError && pages.length === 0 ? <EmptyTree currentKb={currentKb?.name} /> : null}
            {!pagesQuery.isLoading && !pagesQuery.isError && pages.length > 0 ? (
              <WikiNavTree
                pages={pages}
                selectedPageId={selectedPageId}
                query={query}
                pageType={pageType}
                onSelect={setPageId}
                onClearFilters={() => {
                  setQuery("");
                  setPageType("");
                }}
              />
            ) : null}
          </ScrollShadow>
        </aside>

        <main className="min-w-0 rounded-md border border-divider bg-background">
          {selectedPage.isLoading ? <LoadingPage /> : null}
          {selectedPage.isError ? <div className="p-5"><Alert color="warning" variant="flat">页面不可用，请从目录中选择其他页面。</Alert></div> : null}
          {!selectedPage.isLoading && !selectedPage.isError && selectedPage.data ? (
            <WikiReader page={selectedPage.data} pages={allPages} onOpenSlug={(slug) => {
              const next = allPages.find((item) => item.slug === slug);
              if (next) {
                setPageId(next.id);
                if (!pages.some((item) => item.id === next.id)) {
                  setQuery("");
                  setPageType("");
                }
              }
            }} />
          ) : null}
          {!selectedPage.isLoading && !selectedPage.isError && !selectedPage.data ? (
            <div className="grid h-full min-h-96 place-items-center text-sm text-default-500">选择左侧页面开始浏览</div>
          ) : null}
        </main>
      </div>
    </section>
  );
}

function TaskProgress({ task }: { task: Task }) {
  return (
    <div className="border-b border-divider px-3 py-3">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-medium">任务：{stageLabel(task.stage)}</span>
        <span className="text-default-500">{task.progress}%</span>
      </div>
      <Progress value={task.progress} size="sm" color={task.status === "failed" ? "danger" : "primary"} aria-label="Wiki 生成进度" />
      {task.error ? <p className="mt-2 text-xs text-danger">{task.error.message}</p> : null}
    </div>
  );
}

function LoadingTree() {
  return <div className="space-y-3">{Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-10 rounded-md" />)}</div>;
}

function EmptyTree({ currentKb }: { currentKb?: string }) {
  return (
    <div className="grid min-h-40 place-items-center text-center text-sm text-default-500">
      <div>
        <GitBranch className="mx-auto mb-2 text-default-300" size={28} aria-hidden="true" />
        <p>{currentKb ? "暂无 Wiki 页面" : "请先创建 Wiki KB"}</p>
      </div>
    </div>
  );
}

type TopicNode = {
  name: string;
  path: string[];
  pages: WikiPageSummary[];
  children: TopicNode[];
};

function WikiNavTree({
  pages,
  selectedPageId,
  query,
  pageType,
  onSelect,
  onClearFilters,
}: {
  pages: WikiPageSummary[];
  selectedPageId: string | null;
  query: string;
  pageType: WikiPageType | "";
  onSelect: (pageId: string) => void;
  onClearFilters: () => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const entryPages = useMemo(() => sortPages(pages.filter((page) => page.page_type === "index" || page.page_type === "overview" || page.page_type === "analysis")), [pages]);
  const sourcePages = useMemo(() => sortPages(pages.filter((page) => page.page_type === "source")), [pages]);
  const topicTree = useMemo(() => buildTopicTree(pages.filter((page) => page.page_type === "entity" || page.page_type === "concept")), [pages]);
  const hasFilters = Boolean(query || pageType);

  function toggle(path: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <nav className="space-y-5" aria-label="Wiki 页面目录">
      {hasFilters ? (
        <div className="rounded-md bg-default-100 px-3 py-2 text-xs text-default-600">
          <div className="flex items-center justify-between gap-2">
            <span>{pages.length} 个匹配页面</span>
            <Button className="h-7 px-2 text-xs" size="sm" variant="light" onPress={onClearFilters}>清除</Button>
          </div>
        </div>
      ) : null}
      {entryPages.length > 0 ? (
        <NavSection title="入口" count={entryPages.length} icon={<Home size={14} aria-hidden="true" />}>
          <PageLinks pages={entryPages} selectedPageId={selectedPageId} onSelect={onSelect} />
        </NavSection>
      ) : null}
      {topicTree.length > 0 ? (
        <NavSection title="主题目录" count={topicTree.reduce((total, node) => total + countTopicPages(node), 0)} icon={<Layers3 size={14} aria-hidden="true" />}>
          <div className="space-y-2">
            {topicTree.map((node) => (
              <TopicBranch key={node.path.join("/")} node={node} collapsed={collapsed} selectedPageId={selectedPageId} onToggle={toggle} onSelect={onSelect} />
            ))}
          </div>
        </NavSection>
      ) : null}
      {sourcePages.length > 0 ? (
        <NavSection
          title="来源文档"
          count={sourcePages.length}
          icon={<FileText size={14} aria-hidden="true" />}
          collapsible
          defaultCollapsed={!sourcePages.some((page) => page.id === selectedPageId)}
          isActive={sourcePages.some((page) => page.id === selectedPageId)}
        >
          <PageLinks pages={sourcePages} selectedPageId={selectedPageId} onSelect={onSelect} />
        </NavSection>
      ) : null}
    </nav>
  );
}

function NavSection({
  title,
  count,
  icon,
  children,
  collapsible = false,
  defaultCollapsed = false,
  isActive = false,
}: {
  title: string;
  count: number;
  icon: ReactNode;
  children: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  isActive?: boolean;
}) {
  const [open, setOpen] = useState(!defaultCollapsed);

  useEffect(() => {
    if (isActive) setOpen(true);
  }, [isActive]);

  if (collapsible) {
    return (
      <section className="space-y-2">
        <button
          className="flex min-h-8 w-full items-center gap-2 rounded-md bg-default-100/80 px-2.5 py-1.5 text-left text-[11px] font-semibold text-default-500 transition-colors hover:bg-default-200/70"
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          {open ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
          {icon}
          <span className="flex-1">{title}</span>
          <span className="rounded-sm bg-background px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-default-400">{count}</span>
        </button>
        {open ? children : null}
      </section>
    );
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 rounded-md bg-default-100/80 px-2.5 py-1.5 text-[11px] font-semibold text-default-500">
        {icon}
        <span className="flex-1">{title}</span>
        <span className="rounded-sm bg-background px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-default-400">{count}</span>
      </div>
      {children}
    </section>
  );
}

function TopicBranch({
  node,
  collapsed,
  selectedPageId,
  onToggle,
  onSelect,
}: {
  node: TopicNode;
  collapsed: Set<string>;
  selectedPageId: string | null;
  onToggle: (path: string) => void;
  onSelect: (pageId: string) => void;
}) {
  const pathKey = node.path.join("/");
  const isCollapsed = collapsed.has(pathKey);
  const total = countTopicPages(node);

  return (
    <div className="space-y-1">
      <button
        className="flex min-h-9 w-full items-center gap-2 rounded-md bg-default-50 px-2.5 text-left text-sm font-semibold text-default-700 transition-colors hover:bg-default-100"
        type="button"
        aria-expanded={!isCollapsed}
        onClick={() => onToggle(pathKey)}
      >
        {isCollapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
        <span className="rounded-sm bg-default-100 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-default-500">{total}</span>
      </button>
      {!isCollapsed ? (
        <div className="space-y-2 border-l border-divider pl-3">
          {node.pages.length > 0 ? <PageLinks pages={node.pages} selectedPageId={selectedPageId} onSelect={onSelect} /> : null}
          {node.children.map((child) => {
            const childKey = child.path.join("/");
            const childCollapsed = collapsed.has(childKey);
            return (
              <div key={childKey} className="space-y-1">
                <button
                  className="flex min-h-8 w-full items-center gap-2 rounded-md px-2 text-left text-[13px] font-medium text-default-600 transition-colors hover:bg-default-100"
                  type="button"
                  aria-expanded={!childCollapsed}
                  onClick={() => onToggle(childKey)}
                >
                  {childCollapsed ? <ChevronRight size={13} aria-hidden="true" /> : <ChevronDown size={13} aria-hidden="true" />}
                  <span className="min-w-0 flex-1 truncate">{child.name}</span>
                  <span className="rounded-sm bg-default-100 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-default-400">{child.pages.length}</span>
                </button>
                {!childCollapsed ? <div className="pl-3"><PageLinks pages={child.pages} selectedPageId={selectedPageId} onSelect={onSelect} /></div> : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function PageLinks({ pages, selectedPageId, onSelect }: { pages: WikiPageSummary[]; selectedPageId: string | null; onSelect: (pageId: string) => void }) {
  return (
    <div className="space-y-1">
      {pages.map((page) => {
        const selected = selectedPageId === page.id;
        return (
          <button
            key={page.id}
            className={`group flex min-h-8 w-full items-center gap-2 rounded-md border-l-3 px-2 text-left text-[13px] leading-5 transition-colors ${
              selected ? "border-primary bg-primary-50 font-medium text-primary" : "border-transparent text-default-600 hover:bg-default-100 hover:text-default-800"
            }`}
            type="button"
            onClick={() => onSelect(page.id)}
          >
            <span className={selected ? "text-primary" : "text-default-400"}>
              {page.page_type === "source" ? <FileText size={13} aria-hidden="true" /> : <BookOpen size={13} aria-hidden="true" />}
            </span>
            <span className="min-w-0 flex-1 truncate">{page.title}</span>
            <span className={`rounded-sm px-1.5 py-0.5 text-[10px] font-medium ${selected ? "bg-primary-100 text-primary" : "bg-default-100 text-default-400"}`}>
              {pageTypeLabel[page.page_type]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function buildTopicTree(pages: WikiPageSummary[]): TopicNode[] {
  const roots = new Map<string, TopicNode>();
  for (const page of sortPages(pages)) {
    const path = page.category_path.length > 0 ? page.category_path.slice(0, 2) : ["未分类"];
    const rootName = path[0] || "未分类";
    const root = roots.get(rootName) ?? { name: rootName, path: [rootName], pages: [], children: [] };
    roots.set(rootName, root);
    if (path.length === 1) {
      root.pages.push(page);
      continue;
    }
    const childName = path[1] || "未分类";
    let child = root.children.find((item) => item.name === childName);
    if (!child) {
      child = { name: childName, path: [rootName, childName], pages: [], children: [] };
      root.children.push(child);
    }
    child.pages.push(page);
  }
  return Array.from(roots.values()).map(sortTopicNode).sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));
}

function sortTopicNode(node: TopicNode): TopicNode {
  return {
    ...node,
    pages: sortPages(node.pages),
    children: node.children.map(sortTopicNode).sort((left, right) => left.name.localeCompare(right.name, "zh-CN")),
  };
}

function countTopicPages(node: TopicNode): number {
  return node.pages.length + node.children.reduce((total, child) => total + countTopicPages(child), 0);
}

function sortPages(pages: WikiPageSummary[]) {
  return [...pages].sort((left, right) => {
    const typeDelta = pageTypeOrder(left.page_type) - pageTypeOrder(right.page_type);
    if (typeDelta !== 0) return typeDelta;
    return left.title.localeCompare(right.title, "zh-CN");
  });
}

function pageTypeOrder(type: WikiPageType) {
  const order: Record<WikiPageType, number> = {
    index: 0,
    overview: 1,
    analysis: 2,
    entity: 3,
    concept: 4,
    source: 5,
  };
  return order[type];
}

function LoadingPage() {
  return (
    <div className="space-y-4 p-5">
      <Skeleton className="h-7 w-1/3 rounded-md" />
      <Skeleton className="h-4 w-2/3 rounded-md" />
      <Skeleton className="h-72 w-full rounded-md" />
    </div>
  );
}

function WikiReader({ page, pages, onOpenSlug }: { page: WikiPage; pages: WikiPageSummary[]; onOpenSlug: (slug: string) => void }) {
  const [sourceOpen, setSourceOpen] = useState(false);

  return (
    <>
      <article className="min-w-0">
        <header className="border-b border-divider px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <Chip size="sm" variant="flat">{pageTypeLabel[page.page_type]}</Chip>
            <Button
              size="sm"
              variant="flat"
              startContent={<PanelRightOpen size={14} aria-hidden="true" />}
              onPress={() => setSourceOpen(true)}
            >
              {page.source_refs.length} 个来源
            </Button>
            <span className="text-xs text-default-400">{formatDate(page.updated_at)}</span>
          </div>
          <h1 className="mt-3 text-2xl font-semibold">{page.title}</h1>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-default-500">{page.summary}</p>
          {page.aliases.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-1">
              {page.aliases.slice(0, 8).map((alias) => (
                <Chip key={alias} size="sm" variant="bordered">{alias}</Chip>
              ))}
            </div>
          ) : null}
        </header>
        <div className="px-5 py-5">
          <MarkdownView content={page.content} pages={pages} onOpenSlug={onOpenSlug} />
        </div>
      </article>
      <WikiSourceDrawer page={page} pages={pages} isOpen={sourceOpen} onClose={() => setSourceOpen(false)} onOpenSlug={onOpenSlug} />
    </>
  );
}

function MarkdownView({ content, pages, onOpenSlug }: { content: string; pages: WikiPageSummary[]; onOpenSlug: (slug: string) => void }) {
  const knownSlugs = useMemo(() => new Set(pages.map((page) => page.slug)), [pages]);
  const renderedContent = useMemo(() => normalizeWikiLinks(content), [content]);
  const components = useMemo(() => markdownComponents(knownSlugs, onOpenSlug), [knownSlugs, onOpenSlug]);

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={wikiUrlTransform}>
      {renderedContent}
    </ReactMarkdown>
  );
}

function wikiUrlTransform(url: string) {
  return url.startsWith("wiki:") ? url : defaultUrlTransform(url);
}

function markdownComponents(knownSlugs: Set<string>, onOpenSlug: (slug: string) => void): Components {
  return {
    h1: ({ children }) => <h1 className="mb-4 mt-1 text-2xl font-semibold leading-tight">{children}</h1>,
    h2: ({ children }) => <h2 className="mb-3 mt-7 border-b border-divider pb-2 text-lg font-semibold">{children}</h2>,
    h3: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold">{children}</h3>,
    h4: ({ children }) => <h4 className="mb-2 mt-4 text-sm font-semibold text-default-700">{children}</h4>,
    p: ({ children }) => <p className="my-3 max-w-4xl text-sm leading-7 text-default-700">{children}</p>,
    ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6 text-sm leading-7 text-default-700">{children}</ul>,
    ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6 text-sm leading-7 text-default-700">{children}</ol>,
    li: ({ children }) => <li className="pl-1">{children}</li>,
    blockquote: ({ children }) => <blockquote className="my-4 border-l-3 border-default-300 pl-4 text-sm text-default-600">{children}</blockquote>,
    strong: ({ children }) => <strong className="font-semibold text-default-900">{children}</strong>,
    em: ({ children }) => <em className="text-default-800">{children}</em>,
    a: ({ href, children }) => {
      if (href?.startsWith("wiki:")) {
        const slug = decodeURIComponent(href.slice(5));
        if (!knownSlugs.has(slug)) {
          return <span className="text-default-500">{children}</span>;
        }
        return (
          <button
            className="inline-flex align-baseline font-medium text-primary underline decoration-primary-200 underline-offset-2 hover:decoration-primary"
            type="button"
            onClick={() => onOpenSlug(slug)}
          >
            {children}
          </button>
        );
      }
      return (
        <a className="font-medium text-primary underline decoration-primary-200 underline-offset-2 hover:decoration-primary" href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    },
    code: ({ className, children }) => (
      <code className={`${className ?? ""} rounded-sm bg-default-100 px-1.5 py-0.5 font-mono text-[0.85em] text-default-800`}>
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="my-4 overflow-x-auto rounded-md border border-divider bg-default-100 p-3 text-sm leading-6 text-default-800">
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto rounded-md border border-divider">
        <table className="min-w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-default-100 text-default-700">{children}</thead>,
    th: ({ children }) => <th className="border-b border-divider px-3 py-2 text-left font-semibold">{children}</th>,
    td: ({ children }) => <td className="border-b border-divider px-3 py-2 align-top text-default-700">{children}</td>,
  };
}

function normalizeWikiLinks(content: string) {
  return content.replace(/\[\[([^|\]\r\n]+)\|([^\]\r\n]+)\]\]/g, (_, slug: string, label: string) => {
    return `[${escapeMarkdownLinkText(label)}](wiki:${encodeURIComponent(slug.trim())})`;
  });
}

function escapeMarkdownLinkText(value: string) {
  return value.replace(/([\\[\]])/g, "\\$1");
}

function WikiSourceDrawer({
  page,
  pages,
  isOpen,
  onClose,
  onOpenSlug,
}: {
  page: WikiPage;
  pages: WikiPageSummary[];
  isOpen: boolean;
  onClose: () => void;
  onOpenSlug: (slug: string) => void;
}) {
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);
  const [originalSource, setOriginalSource] = useState<WikiPageSource | null>(null);
  const [originalChunkId, setOriginalChunkId] = useState<string | null>(null);
  const chunkRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const sourcesQuery = useQuery({
    queryKey: ["wiki-page-sources", page.id],
    queryFn: () => getWikiPageSources(page.id),
    enabled: isOpen,
    retry: false,
  });
  const sources = sourcesQuery.data ?? [];
  const sourcePageByDocument = useMemo(
    () => new Map(pages.filter((item) => item.slug.startsWith("source/")).map((item) => [item.slug.replace("source/", ""), item])),
    [pages],
  );

  useEffect(() => {
    if (isOpen) {
      setActiveChunkId(null);
      setOriginalSource(null);
      setOriginalChunkId(null);
    }
  }, [isOpen, page.id]);

  function focusChunk(chunkId: string) {
    setActiveChunkId(chunkId);
    requestAnimationFrame(() => chunkRefs.current[chunkId]?.scrollIntoView({ block: "center", behavior: "smooth" }));
  }

  return (
    <Modal isOpen={isOpen} onOpenChange={(nextOpen) => !nextOpen && onClose()} size="4xl" placement="center" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader className="flex items-center gap-2">
          {originalSource ? (
            <Button size="sm" variant="light" isIconOnly aria-label="返回来源列表" onPress={() => setOriginalSource(null)}>
              <ArrowLeft size={16} aria-hidden="true" />
            </Button>
          ) : (
            <Link2 size={18} aria-hidden="true" />
          )}
          {originalSource ? "原始文档" : "来源定位"}
        </ModalHeader>
        <ModalBody className="gap-4">
          {originalSource ? (
            <OriginalDocumentTrace source={originalSource} activeChunkId={originalChunkId} />
          ) : (
            <>
              {sourcesQuery.isLoading ? <SourceLoading /> : null}
              {sourcesQuery.isError ? <Alert color="warning" variant="flat">来源加载失败，请稍后重试。</Alert> : null}
              {!sourcesQuery.isLoading && !sourcesQuery.isError && sources.length === 0 ? (
                <Alert color="default" variant="flat">当前页面没有记录来源。</Alert>
              ) : null}
              {!sourcesQuery.isLoading && !sourcesQuery.isError && sources.length > 0 ? (
                <div className="space-y-4">
                  {sources.map((source) => (
                    <WikiSourceGroup
                      key={source.document_id}
                      source={source}
                      sourcePage={sourcePageByDocument.get(source.document_id)}
                      activeChunkId={activeChunkId}
                      chunkRefs={chunkRefs}
                      onFocusChunk={focusChunk}
                      onOpenOriginalDocument={(nextSource, chunkId) => {
                        setOriginalSource(nextSource);
                        setOriginalChunkId(chunkId ?? null);
                      }}
                      onOpenSourcePage={(slug) => {
                        onOpenSlug(slug);
                        onClose();
                      }}
                    />
                  ))}
                </div>
              ) : null}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose}>关闭</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function WikiSourceGroup({
  source,
  sourcePage,
  activeChunkId,
  chunkRefs,
  onFocusChunk,
  onOpenOriginalDocument,
  onOpenSourcePage,
}: {
  source: WikiPageSource;
  sourcePage?: WikiPageSummary;
  activeChunkId: string | null;
  chunkRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  onFocusChunk: (chunkId: string) => void;
  onOpenOriginalDocument: (source: WikiPageSource, chunkId?: string) => void;
  onOpenSourcePage: (slug: string) => void;
}) {
  return (
    <section className="rounded-md border border-divider">
      <div className="flex flex-wrap items-center gap-2 border-b border-divider px-4 py-3">
        <FileText size={16} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{source.filename}</h3>
          <p className="text-xs text-default-500">{statusLabel(source.status)} · {source.document_id}</p>
        </div>
        <Chip size="sm" color={source.precise ? "success" : "warning"} variant="flat">
          {source.precise ? "精确片段" : "文档级来源"}
        </Chip>
        <Chip size="sm" variant="flat">{source.chunks.length} 个片段</Chip>
        <Button
          size="sm"
          color="primary"
          variant="flat"
          startContent={<FileText size={14} aria-hidden="true" />}
          onPress={() => onOpenOriginalDocument(source)}
        >
          打开原始文档
        </Button>
        <Button
          size="sm"
          variant="flat"
          startContent={<ExternalLink size={14} aria-hidden="true" />}
          isDisabled={!sourcePage}
          onPress={() => sourcePage && onOpenSourcePage(sourcePage.slug)}
        >
          查看摘要页
        </Button>
      </div>
      {source.chunks.length > 0 ? (
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap gap-2">
            {source.chunks.map((chunk) => (
              <Button
                key={chunk.id}
                size="sm"
                variant={activeChunkId === chunk.id ? "solid" : "flat"}
                color={activeChunkId === chunk.id ? "primary" : "default"}
                startContent={<LocateFixed size={13} aria-hidden="true" />}
                onPress={() => onFocusChunk(chunk.id)}
              >
                #{chunk.seq + 1}
              </Button>
            ))}
          </div>
          <ScrollShadow className="max-h-[46vh] pr-1">
            <div className="space-y-2">
              {source.chunks.map((chunk) => (
                <div
                  key={chunk.id}
                  ref={(node) => {
                    chunkRefs.current[chunk.id] = node;
                  }}
                  className={`rounded-md border p-3 transition-colors ${
                    activeChunkId === chunk.id ? "border-primary bg-primary-50" : "border-divider bg-background"
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-default-500">
                    <span className="font-medium text-default-700">Chunk #{chunk.seq + 1}</span>
                    <span>{formatChunkRange(chunk.start_pos, chunk.end_pos)}</span>
                    {chunk.header_path.length > 0 ? <span className="truncate">{chunk.header_path.join(" / ")}</span> : null}
                    <Button className="ml-auto" size="sm" variant="light" onPress={() => onOpenOriginalDocument(source, chunk.id)}>
                      在原文中定位
                    </Button>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-default-700">{chunk.content}</p>
                </div>
              ))}
            </div>
          </ScrollShadow>
        </div>
      ) : (
        <p className="px-4 py-5 text-sm text-default-500">该来源文档没有可展示片段。</p>
      )}
    </section>
  );
}

function OriginalDocumentTrace({ source, activeChunkId }: { source: WikiPageSource; activeChunkId: string | null }) {
  const activeChunk = activeChunkId ? source.chunks.find((chunk) => chunk.id === activeChunkId) : null;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["document", source.document_id],
    queryFn: () => getDocument(source.document_id),
    retry: false,
  });

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{data?.filename ?? source.filename}</h3>
          <p className="text-xs text-default-500">
            原始上传文档 · {source.precise ? "精确 chunk 证据" : "文档级来源"}
          </p>
        </div>
        {activeChunk ? <Chip size="sm" color="primary" variant="flat">定位 Chunk #{activeChunk.seq + 1}</Chip> : null}
      </div>
      {isLoading ? <Skeleton className="h-72 rounded-md" /> : null}
      {isError ? <Alert color="warning" variant="flat">原始文档加载失败，请确认文档仍存在且当前团队有访问权限。</Alert> : null}
      {data ? <OriginalDocumentTabs document={data} source={source} activeChunkId={activeChunkId} /> : null}
    </section>
  );
}

function OriginalDocumentTabs({ document, source, activeChunkId }: { document: DocumentDetail; source: WikiPageSource; activeChunkId: string | null }) {
  const activeChunk = activeChunkId ? source.chunks.find((chunk) => chunk.id === activeChunkId) : null;
  return (
    <Tabs aria-label="原始文档溯源">
      <Tab key="raw" title="原文定位">
        <div className="rounded-md border border-divider bg-background p-3">
          <pre className="max-h-[58vh] overflow-auto whitespace-pre-wrap break-words text-sm leading-7 text-foreground">
            {activeChunk ? renderHighlightedSource(document.content, activeChunk.start_pos, activeChunk.end_pos) : document.content}
          </pre>
        </div>
      </Tab>
      <Tab key="chunks" title={`分块列表 (${document.chunks.length})`}>
        <ScrollShadow className="max-h-[58vh] pr-1">
          <div className="space-y-2">
            {document.chunks.map((chunk) => {
              const cited = source.chunks.some((item) => item.id === chunk.id);
              const active = activeChunkId === chunk.id;
              return (
                <div key={chunk.id} className={`rounded-md border p-3 ${active ? "border-primary bg-primary-50" : cited ? "border-success-200 bg-success-50" : "border-divider bg-background"}`}>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-default-500">
                    <span className="font-medium text-default-700">Chunk #{chunk.seq + 1}</span>
                    {cited ? <Chip size="sm" color="success" variant="flat">本页引用</Chip> : null}
                    <span>{formatChunkRange(chunk.start_pos, chunk.end_pos)}</span>
                    {chunk.header_path.length > 0 ? <span className="truncate">{chunk.header_path.join(" / ")}</span> : null}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-default-700">{chunk.content}</p>
                </div>
              );
            })}
          </div>
        </ScrollShadow>
      </Tab>
    </Tabs>
  );
}

function renderHighlightedSource(content: string, start: number, end: number) {
  const safeStart = Math.max(0, Math.min(start, content.length));
  const safeEnd = Math.max(safeStart, Math.min(end, content.length));
  if (safeStart === safeEnd) return content;
  return (
    <>
      {content.slice(0, safeStart)}
      <mark className="rounded-sm bg-warning-100 px-0.5 text-warning-900">{content.slice(safeStart, safeEnd)}</mark>
      {content.slice(safeEnd)}
    </>
  );
}

function SourceLoading() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-24 rounded-md" />
      ))}
    </div>
  );
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "待处理",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
  };
  return labels[status] ?? status;
}

function formatChunkRange(start: number, end: number) {
  return `${start}-${end}`;
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    pending: "排队中",
    extracting: "抽取",
    citing: "引用标注",
    taxonomy: "分类",
    summarizing: "摘要",
    reducing: "归并",
    postprocessing: "后处理",
    completed: "已完成",
    failed: "失败",
  };
  return labels[stage] ?? stage;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
