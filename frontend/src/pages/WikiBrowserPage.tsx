import {
  Alert,
  Button,
  Chip,
  Divider,
  Input,
  Progress,
  ScrollShadow,
  Select,
  SelectItem,
  Skeleton,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronRight, FileText, GitBranch, RefreshCw, Search, Sparkles } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useMemo, useState } from "react";

import { listKnowledgeBases } from "../api/m1";
import { getTask, type Task } from "../api/m2";
import {
  getWikiPage,
  ingestWiki,
  listWikiPages,
  rebuildWiki,
  type WikiPage,
  type WikiPageSummary,
  type WikiPageTreeNode,
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
            <Select size="sm" aria-label="页面类型" placeholder="全部类型" selectedKeys={pageType ? new Set([pageType]) : new Set([])} onSelectionChange={(keys) => setPageType(firstKey(keys, "") as WikiPageType | "")}>
              {(Object.keys(pageTypeLabel) as WikiPageType[]).map((type) => (
                <SelectItem key={type}>{pageTypeLabel[type]}</SelectItem>
              ))}
            </Select>
          </div>
          <Divider />
          {activeTask ? <TaskProgress task={activeTask} /> : null}
          <ScrollShadow className="h-[calc(100vh-23rem)] min-h-80 p-3">
            {pagesQuery.isLoading ? <LoadingTree /> : null}
            {pagesQuery.isError ? <Alert color="warning" variant="flat">Wiki 暂不可浏览，可能正在重建或尚未生成。</Alert> : null}
            {!pagesQuery.isLoading && !pagesQuery.isError && pages.length === 0 ? <EmptyTree currentKb={currentKb?.name} /> : null}
            {!pagesQuery.isLoading && !pagesQuery.isError && pages.length > 0 ? (
              <TreeList nodes={pagesQuery.data?.tree ?? []} selectedPageId={selectedPageId} onSelect={setPageId} />
            ) : null}
          </ScrollShadow>
        </aside>

        <main className="min-w-0 rounded-md border border-divider bg-background">
          {selectedPage.isLoading ? <LoadingPage /> : null}
          {selectedPage.isError ? <div className="p-5"><Alert color="warning" variant="flat">页面不可用，请从目录中选择其他页面。</Alert></div> : null}
          {!selectedPage.isLoading && !selectedPage.isError && selectedPage.data ? (
            <WikiReader page={selectedPage.data} pages={pages} onOpenSlug={(slug) => {
              const next = pages.find((item) => item.slug === slug);
              if (next) setPageId(next.id);
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

function TreeList({ nodes, selectedPageId, onSelect }: { nodes: WikiPageTreeNode[]; selectedPageId: string | null; onSelect: (pageId: string) => void }) {
  return (
    <div className="space-y-3">
      {nodes.map((node) => (
        <div key={node.path.join("/")}>
          <div className="mb-1 text-xs font-semibold text-default-400">{node.name}</div>
          <PageLinks pages={node.pages} selectedPageId={selectedPageId} onSelect={onSelect} />
          {node.children.map((child) => (
            <div key={child.path.join("/")} className="mt-2 border-l border-divider pl-3">
              <div className="mb-1 text-xs text-default-400">{child.name}</div>
              <PageLinks pages={child.pages} selectedPageId={selectedPageId} onSelect={onSelect} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function PageLinks({ pages, selectedPageId, onSelect }: { pages: WikiPageSummary[]; selectedPageId: string | null; onSelect: (pageId: string) => void }) {
  return (
    <div className="space-y-1">
      {pages.map((page) => (
        <button
          key={page.id}
          className={`flex min-h-9 w-full items-center gap-2 rounded-md px-2 text-left text-sm transition-colors ${selectedPageId === page.id ? "bg-primary-50 text-primary" : "hover:bg-default-100"}`}
          type="button"
          onClick={() => onSelect(page.id)}
        >
          {page.page_type === "source" ? <FileText size={14} aria-hidden="true" /> : <BookOpen size={14} aria-hidden="true" />}
          <span className="min-w-0 flex-1 truncate">{page.title}</span>
          <ChevronRight size={13} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
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
  return (
    <article className="min-w-0">
      <header className="border-b border-divider px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Chip size="sm" variant="flat">{pageTypeLabel[page.page_type]}</Chip>
          <Chip size="sm" variant="flat">{page.source_refs.length} 个来源</Chip>
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
  );
}

function MarkdownView({ content, pages, onOpenSlug }: { content: string; pages: WikiPageSummary[]; onOpenSlug: (slug: string) => void }) {
  const knownSlugs = useMemo(() => new Set(pages.map((page) => page.slug)), [pages]);
  return (
    <>
      {content.split(/\r?\n/).map((line, index) => {
        if (!line.trim()) return <div key={index} className="h-3" />;
        if (line.startsWith("### ")) return <h3 key={index} className="mt-5 text-base font-semibold">{renderInline(line.slice(4), knownSlugs, onOpenSlug)}</h3>;
        if (line.startsWith("## ")) return <h2 key={index} className="mt-6 text-lg font-semibold">{renderInline(line.slice(3), knownSlugs, onOpenSlug)}</h2>;
        if (line.startsWith("- ")) return <p key={index} className="pl-4 text-sm leading-7 before:mr-2 before:content-['-']">{renderInline(line.slice(2), knownSlugs, onOpenSlug)}</p>;
        return <p key={index} className="text-sm leading-7 text-default-700">{renderInline(line, knownSlugs, onOpenSlug)}</p>;
      })}
    </>
  );
}

function renderInline(text: string, knownSlugs: Set<string>, onOpenSlug: (slug: string) => void): ReactNode[] {
  const parts: ReactNode[] = [];
  const linkRe = /\[\[([^|\]]+)\|([^\]]+)\]\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = linkRe.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(<Fragment key={`t-${lastIndex}`}>{text.slice(lastIndex, match.index)}</Fragment>);
    const slug = match[1];
    const label = match[2];
    parts.push(
      <button
        key={`${slug}-${match.index}`}
        className="inline-flex align-baseline font-medium text-primary underline decoration-primary-200 underline-offset-2 disabled:text-default-500 disabled:no-underline"
        type="button"
        disabled={!knownSlugs.has(slug)}
        onClick={() => onOpenSlug(slug)}
      >
        {label}
      </button>,
    );
    lastIndex = linkRe.lastIndex;
  }
  if (lastIndex < text.length) parts.push(<Fragment key={`t-${lastIndex}`}>{text.slice(lastIndex)}</Fragment>);
  return parts;
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
