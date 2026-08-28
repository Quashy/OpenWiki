import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  Chip,
  Divider,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Progress,
  Select,
  SelectItem,
  Skeleton,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
  Tabs,
  Textarea,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  Database,
  Eye,
  FileText,
  GitBranch,
  Link2,
  Plus,
  RefreshCw,
  Save,
  Scissors,
  Search,
  Tag as TagIcon,
  Trash2,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  bindSourceKnowledgeBase,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBase,
  listKnowledgeBases,
  listOllamaModels,
  unbindSourceKnowledgeBase,
  updateKnowledgeBase,
  type ChunkingConfig,
  type KnowledgeBase,
  type KnowledgeBaseType,
  type WikiConfig,
} from "../api/m1";
import {
  createTag,
  deleteDocument,
  deleteTag,
  getDocument,
  listDocuments,
  listTags,
  previewChunks,
  retryDocument,
  updateTag,
  uploadDocuments,
  type Chunk,
  type ChunkPreviewItem,
  type Document,
  type DocumentStatus,
  type Tag,
} from "../api/m2";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";
import { useAuthStore } from "../stores/authStore";

type EditableStatus = "active" | "disabled";

const defaultChunking: ChunkingConfig = {
  chunk_size: 512,
  chunk_overlap: 80,
  strategy: "header_aware",
};

const defaultWikiConfig: WikiConfig = {
  auto_ingest: false,
  llm_timeout_seconds: 60,
  llm_max_retries: 3,
  temperature: 0.7,
};

const documentStatusTone: Record<DocumentStatus, "default" | "primary" | "success" | "danger"> = {
  pending: "default",
  running: "primary",
  completed: "success",
  failed: "danger",
};

export function KnowledgeBasePage({ canManage, onOpenWiki }: { canManage: boolean; onOpenWiki?: (kbId: string) => void }) {
  const [openCreate, setOpenCreate] = useState(false);
  const [settingsKbId, setSettingsKbId] = useState<string | null>(null);
  const [sourceKbId, setSourceKbId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { membership } = useAuthStore();
  const canEditDocuments = membership?.role === "admin" || membership?.role === "editor";
  const { data = [], isLoading } = useQuery({ queryKey: ["kbs"], queryFn: () => listKnowledgeBases() });
  const sourceKbs = data.filter((kb) => kb.type === "document");
  const wikiKbs = data.filter((kb) => kb.type === "wiki");
  const activeSourceKb = sourceKbs.find((kb) => kb.id === sourceKbId);

  if (activeSourceKb) {
    return (
      <>
        <SourceKbView
          kb={activeSourceKb}
          canManageKb={canManage}
          canEditDocuments={canEditDocuments}
          onBack={() => setSourceKbId(null)}
          onOpenSettings={() => setSettingsKbId(activeSourceKb.id)}
        />
        <KbDetailModal kbId={settingsKbId} sourceKbs={sourceKbs} canManage={canManage} onClose={() => setSettingsKbId(null)} />
      </>
    );
  }

  return (
    <section className="space-y-6">
      <PageHeader
        title="知识库"
        description="管理源文档和自动生成的 Wiki 知识库"
        action={
          canManage ? (
            <Button color="primary" startContent={<Plus size={16} aria-hidden="true" />} onPress={() => setOpenCreate(true)}>
              创建知识库
            </Button>
          ) : null
        }
      />
      <KbSection
        title="源知识库（Source KB）"
        icon={Database}
        items={sourceKbs}
        empty="还没有源知识库"
        isLoading={isLoading}
        onOpen={setSourceKbId}
        actionLabel="打开文档"
      />
      <KbSection
        title="Wiki 知识库（Wiki KB）"
        icon={GitBranch}
        items={wikiKbs}
        empty="还没有 Wiki 知识库"
        isLoading={isLoading}
        onOpen={(kbId) => onOpenWiki?.(kbId) ?? setSettingsKbId(kbId)}
        actionLabel="打开 Wiki"
      />
      <CreateKbModal open={openCreate} onClose={() => setOpenCreate(false)} sourceKbs={sourceKbs} onDone={() => queryClient.invalidateQueries({ queryKey: ["kbs"] })} />
      <KbDetailModal kbId={settingsKbId} sourceKbs={sourceKbs} canManage={canManage} onClose={() => setSettingsKbId(null)} />
    </section>
  );
}

function KbSection({
  title,
  icon: Icon,
  items,
  empty,
  isLoading,
  onOpen,
  actionLabel,
}: {
  title: string;
  icon: LucideIcon;
  items: KnowledgeBase[];
  empty: string;
  isLoading: boolean;
  onOpen: (kbId: string) => void;
  actionLabel: string;
}) {
  return (
    <Card shadow="sm">
      <CardHeader className="flex items-center gap-2">
        <Icon size={18} aria-hidden="true" />
        <h2 className="text-sm font-semibold">{title}</h2>
      </CardHeader>
      <Divider />
      <CardBody>
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label={`${title}加载中`}>
            {Array.from({ length: 3 }).map((_, index) => (
              <Card key={index} shadow="none" className="border border-divider">
                <CardBody className="gap-4 p-4">
                  <Skeleton className="h-4 w-3/5 rounded-md" />
                  <Skeleton className="h-3 w-full rounded-md" />
                  <Skeleton className="h-3 w-4/5 rounded-md" />
                </CardBody>
              </Card>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="grid min-h-28 place-items-center text-sm text-default-500">{empty}</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((kb) => (
              <Card key={kb.id} shadow="none" isPressable className="border border-divider text-left transition-colors hover:border-primary-200" onPress={() => onOpen(kb.id)}>
                <CardHeader className="items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold">{kb.name}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-default-500">{kb.description || "暂无描述"}</p>
                  </div>
                  <Chip color={kb.status === "active" ? "success" : "default"} size="sm" variant="flat">
                    {kbStatusLabel(kb.status)}
                  </Chip>
                </CardHeader>
                <CardBody className="gap-3 pt-0 text-sm text-default-500">
                  <MetaLine label="Embedding" value={kb.embedding_model_tag} />
                  <MetaLine label="维度" value={String(kb.embedding_dim)} />
                  <MetaLine label={kb.type === "wiki" ? "绑定 Source" : "文档数"} value={String(kb.type === "wiki" ? (kb.bound_source_kbs?.length ?? 0) : (kb.document_count ?? 0))} />
                  <Button className="mt-2" size="sm" variant="flat" startContent={<Eye size={15} aria-hidden="true" />} onPress={() => onOpen(kb.id)}>
                    {actionLabel}
                  </Button>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function SourceKbView({
  kb,
  canManageKb,
  canEditDocuments,
  onBack,
  onOpenSettings,
}: {
  kb: KnowledgeBase;
  canManageKb: boolean;
  canEditDocuments: boolean;
  onBack: () => void;
  onOpenSettings: () => void;
}) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [tagId, setTagId] = useState("");
  const [status, setStatus] = useState<DocumentStatus | "">("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [tagManagerOpen, setTagManagerOpen] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const { data: tags = [] } = useQuery({ queryKey: ["tags", kb.id], queryFn: () => listTags(kb.id) });
  const { data: documents = [], isLoading } = useQuery({
    queryKey: ["documents", kb.id, query, tagId, status],
    queryFn: () => listDocuments({ kbId: kb.id, q: query || undefined, tag_id: tagId || undefined, status }),
    refetchInterval: (result) => (result.state.data?.some((item) => item.status === "pending" || item.status === "running") ? 2000 : false),
  });
  const retryMutation = useMutation({
    mutationFn: retryDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", kb.id] }),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", kb.id] });
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
    },
  });
  const chunking = kb.chunking_config ?? defaultChunking;
  const selectedDocument = documents.find((document) => document.id === documentId);

  if (documentId) {
    return <DocumentDetailView documentId={documentId} fallback={selectedDocument} onBack={() => setDocumentId(null)} />;
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Button className="mb-3 px-0" variant="light" startContent={<ChevronLeft size={16} aria-hidden="true" />} onPress={onBack}>
            知识库
          </Button>
          <h1 className="text-xl font-semibold">{kb.name}</h1>
          <p className="mt-1 text-sm text-default-500">{kb.description || "暂无描述"}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <Chip variant="flat">{kb.document_count ?? 0} 篇文档</Chip>
            <Chip variant="flat">Embedding: {kb.embedding_model_tag}</Chip>
            <Chip variant="flat">chunk {chunking.chunk_size}/{chunking.chunk_overlap}</Chip>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManageKb ? <Button variant="flat" startContent={<Save size={16} aria-hidden="true" />} onPress={onOpenSettings}>设置</Button> : null}
          {canManageKb ? <Button variant="flat" startContent={<Scissors size={16} aria-hidden="true" />} onPress={() => setPreviewOpen(true)}>分块预览</Button> : null}
          {canEditDocuments ? <Button color="primary" startContent={<Upload size={16} aria-hidden="true" />} onPress={() => setUploadOpen(true)}>上传文档</Button> : null}
        </div>
      </div>

      <Card shadow="sm">
        <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="flex items-center gap-2 font-semibold">
            <FileText size={18} aria-hidden="true" />
            文档列表
          </div>
          <div className="grid w-full gap-2 md:ml-auto md:w-auto md:grid-cols-[220px_160px_150px_auto]">
            <Input size="sm" placeholder="搜索文件名" value={query} onValueChange={setQuery} startContent={<Search size={15} aria-hidden="true" />} />
            <Select size="sm" aria-label="标签筛选" placeholder="全部标签" selectedKeys={tagId ? new Set([tagId]) : new Set([])} onSelectionChange={(keys) => setTagId(firstKey(keys, ""))}>
              {tags.map((tag) => <SelectItem key={tag.id}>{tag.name}</SelectItem>)}
            </Select>
            <Select size="sm" aria-label="状态筛选" placeholder="全部状态" selectedKeys={status ? new Set([status]) : new Set([])} onSelectionChange={(keys) => setStatus(firstKey(keys, "") as DocumentStatus | "")}>
              <SelectItem key="pending">待处理</SelectItem>
              <SelectItem key="running">处理中</SelectItem>
              <SelectItem key="completed">已完成</SelectItem>
              <SelectItem key="failed">失败</SelectItem>
            </Select>
            {canEditDocuments ? <Button size="sm" variant="flat" startContent={<TagIcon size={15} aria-hidden="true" />} onPress={() => setTagManagerOpen(true)}>标签</Button> : null}
          </div>
        </CardHeader>
        <Divider />
        <CardBody className="p-0">
          <Table removeWrapper aria-label="文档列表">
            <TableHeader>
              <TableColumn>文件名</TableColumn>
              <TableColumn>标签</TableColumn>
              <TableColumn align="center">分块</TableColumn>
              <TableColumn>大小</TableColumn>
              <TableColumn>上传者</TableColumn>
              <TableColumn>状态</TableColumn>
              <TableColumn>上传时间</TableColumn>
              <TableColumn>操作</TableColumn>
            </TableHeader>
            <TableBody isLoading={isLoading} emptyContent="暂无文档">
              {documents.map((document) => (
                <TableRow key={document.id}>
                  <TableCell>
                    <button className="flex max-w-72 items-center gap-2 text-left font-medium text-foreground hover:text-primary" type="button" onClick={() => setDocumentId(document.id)}>
                      <FileText size={16} className={document.filename.endsWith(".md") ? "text-primary" : "text-default-500"} aria-hidden="true" />
                      <span className="truncate">{document.filename}</span>
                    </button>
                    {document.error_message ? <div className="mt-1 max-w-72 truncate text-xs text-danger">{document.error_message}</div> : null}
                  </TableCell>
                  <TableCell>
                    <div className="flex max-w-52 flex-wrap gap-1">
                      {(document.tags ?? []).length > 0 ? document.tags?.map((tag) => <Chip key={tag.id} size="sm" variant="flat">{tag.name}</Chip>) : <span className="text-default-400">-</span>}
                    </div>
                  </TableCell>
                  <TableCell>{document.chunk_count}</TableCell>
                  <TableCell>{formatBytes(document.file_size)}</TableCell>
                  <TableCell className="max-w-28 truncate">{document.created_by_username}</TableCell>
                  <TableCell><Chip color={documentStatusTone[document.status]} size="sm" variant="flat">{documentStatusLabel(document.status)}</Chip></TableCell>
                  <TableCell className="whitespace-nowrap">{formatDate(document.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {document.status === "failed" ? (
                        <Button size="sm" variant="flat" isIconOnly aria-label="重试" isLoading={retryMutation.isPending} onPress={() => retryMutation.mutate(document.id)}>
                          <RefreshCw size={15} aria-hidden="true" />
                        </Button>
                      ) : null}
                      {canEditDocuments ? (
                        <Button size="sm" variant="light" color="danger" isIconOnly aria-label="删除" isLoading={deleteMutation.isPending} onPress={() => deleteMutation.mutate(document.id)}>
                          <Trash2 size={15} aria-hidden="true" />
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardBody>
      </Card>

      <UploadDocumentModal kbId={kb.id} tags={tags} open={uploadOpen} onClose={() => setUploadOpen(false)} />
      <ChunkPreviewModal kb={kb} open={previewOpen} onClose={() => setPreviewOpen(false)} />
      <TagManagerModal kbId={kb.id} tags={tags} open={tagManagerOpen} onClose={() => setTagManagerOpen(false)} />
    </section>
  );
}

function UploadDocumentModal({ kbId, tags, open, onClose }: { kbId: string; tags: Tag[]; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const uploadMutation = useMutation({
    mutationFn: () => uploadDocuments({ kbId, files, tagIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      setFiles([]);
      setTagIds([]);
      onClose();
    },
  });

  function addFiles(nextFiles: FileList | null) {
    if (nextFiles) setFiles((current) => [...current, ...Array.from(nextFiles)]);
  }

  return (
    <Modal isOpen={open} onOpenChange={(nextOpen) => !nextOpen && onClose()} placement="center" size="2xl" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader>上传文档</ModalHeader>
        <ModalBody className="gap-4">
          <label
            className="grid min-h-36 cursor-pointer place-items-center rounded-lg border-2 border-dashed border-divider px-6 py-8 text-center transition-colors hover:border-primary hover:bg-primary-50"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              addFiles(event.dataTransfer.files);
            }}
          >
            <input className="sr-only" type="file" multiple accept=".md,.txt" onChange={(event) => addFiles(event.currentTarget.files)} />
            <span className="grid gap-2">
              <Upload className="mx-auto text-default-400" size={34} aria-hidden="true" />
              <span className="font-medium">点击或拖拽文件到此处上传</span>
              <span className="text-xs text-default-500">仅支持 .md / .txt，单文件最大 10MB</span>
            </span>
          </label>
          {files.length > 0 ? (
            <div className="space-y-2">
              {files.map((file, index) => (
                <div key={`${file.name}-${index}`} className="flex items-center gap-3 rounded-md border border-divider px-3 py-2 text-sm">
                  <FileText size={16} className="text-primary" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{file.name}</span>
                  <span className="text-default-500">{formatBytes(file.size)}</span>
                  <Button size="sm" variant="light" isIconOnly aria-label="移除文件" onPress={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}>
                    <X size={15} aria-hidden="true" />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}
          <Select label="标签（可选）" selectionMode="multiple" selectedKeys={new Set(tagIds)} onSelectionChange={(keys) => setTagIds(keys === "all" ? tags.map((tag) => tag.id) : Array.from(keys).map(String))}>
            {tags.map((tag) => <SelectItem key={tag.id}>{tag.name}</SelectItem>)}
          </Select>
          {uploadMutation.isPending ? <Progress isIndeterminate aria-label="上传中" size="sm" /> : null}
          {uploadMutation.isError ? <Alert color="danger" variant="flat">上传失败，请检查文件类型、大小或是否重复。</Alert> : null}
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose}>取消</Button>
          <Button color="primary" isDisabled={files.length === 0} isLoading={uploadMutation.isPending} onPress={() => uploadMutation.mutate()}>开始上传</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function DocumentDetailView({ documentId, fallback, onBack }: { documentId: string; fallback?: Document; onBack: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
    refetchInterval: (result) => (result.state.data?.status === "running" || result.state.data?.status === "pending" ? 2000 : false),
  });
  const document = data ?? fallback;

  return (
    <section className="space-y-5">
      <div>
        <Button className="mb-3 px-0" variant="light" startContent={<ChevronLeft size={16} aria-hidden="true" />} onPress={onBack}>返回文档列表</Button>
        <h1 className="text-xl font-semibold">{document?.filename ?? "文档详情"}</h1>
        <p className="mt-1 text-sm text-default-500">{document ? `${formatBytes(document.file_size)} · ${document.chunk_count} 个分块 · 上传于 ${formatDate(document.created_at)}` : "正在加载文档"}</p>
      </div>
      {isError ? <Alert color="danger" variant="flat">文档加载失败。</Alert> : null}
      {isLoading && !data ? (
        <Card><CardBody><Skeleton className="h-72 w-full rounded-lg" /></CardBody></Card>
      ) : data ? (
        <Tabs aria-label="文档详情">
          <Tab key="preview" title="原文预览">
            <Card shadow="sm"><CardBody><pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap break-words text-sm leading-7 text-foreground">{data.content}</pre></CardBody></Card>
          </Tab>
          <Tab key="chunks" title={`分块列表 (${data.chunks.length})`}>
            <div className="space-y-3">{data.chunks.length > 0 ? data.chunks.map((chunk) => <ChunkCard key={chunk.id} chunk={chunk} />) : <Card><CardBody className="grid min-h-32 place-items-center text-sm text-default-500">该文档暂无分块数据</CardBody></Card>}</div>
          </Tab>
        </Tabs>
      ) : null}
    </section>
  );
}

function ChunkPreviewModal({ kb, open, onClose }: { kb: KnowledgeBase; open: boolean; onClose: () => void }) {
  const chunking = kb.chunking_config ?? defaultChunking;
  const [content, setContent] = useState("");
  const [contentType, setContentType] = useState<"markdown" | "text">("markdown");
  const [previewItems, setPreviewItems] = useState<ChunkPreviewItem[]>([]);
  const trimmedContent = content.trim();
  const previewMutation = useMutation({
    mutationFn: () => previewChunks({ kbId: kb.id, content: trimmedContent, content_type: contentType, chunking_config: chunking }),
    onSuccess: setPreviewItems,
  });

  return (
    <Modal isOpen={open} onOpenChange={(nextOpen) => !nextOpen && onClose()} size="3xl" placement="center" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader>分块预览</ModalHeader>
        <ModalBody className="gap-4">
          <div className="grid gap-3 md:grid-cols-[1fr_160px]">
            <Textarea
              minRows={8}
              label="输入文本"
              placeholder={"粘贴 Markdown 或 TXT 内容进行分块试算。\n\n# 一级标题\n\n正文内容...\n\n## 二级标题\n\n更多正文..."}
              value={content}
              onValueChange={setContent}
            />
            <div className="space-y-3">
              <Select label="内容类型" selectedKeys={new Set([contentType])} onSelectionChange={(keys) => setContentType(firstKey(keys, "markdown") as "markdown" | "text")}>
                <SelectItem key="markdown">Markdown</SelectItem>
                <SelectItem key="text">TXT</SelectItem>
              </Select>
              <MetaItem label="Chunk" value={`${chunking.chunk_size}/${chunking.chunk_overlap}`} />
              <Button fullWidth variant="flat" isLoading={previewMutation.isPending} isDisabled={trimmedContent.length === 0} onPress={() => previewMutation.mutate()}>刷新预览</Button>
            </div>
          </div>
          {previewMutation.isError ? <Alert color="danger" variant="flat">分块预览失败，请检查输入内容后重试。</Alert> : null}
          <div className="text-sm text-default-500">共 {previewItems.length} 个 chunk</div>
          <div className="max-h-96 space-y-3 overflow-auto">
            {trimmedContent.length === 0 ? (
              <Card shadow="none" className="border border-dashed border-divider">
                <CardBody className="grid min-h-28 place-items-center text-sm text-default-500">输入内容后预览分块结果</CardBody>
              </Card>
            ) : previewItems.map((chunk) => <ChunkPreviewCard key={`${chunk.seq}-${chunk.start_pos}`} chunk={chunk} />)}
          </div>
        </ModalBody>
        <ModalFooter><Button variant="light" onPress={onClose}>关闭</Button></ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function ChunkPreviewCard({ chunk }: { chunk: ChunkPreviewItem }) {
  return (
    <Card shadow="none" className="border border-divider">
      <CardBody className="gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-default-400">#{String(chunk.seq).padStart(3, "0")}</span>
          {chunk.header_path.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1 text-primary">
              {chunk.header_path.map((item, index) => <span key={`${item}-${index}`} className="inline-flex items-center gap-1">{index > 0 ? <span className="text-default-300">/</span> : null}{item}</span>)}
            </div>
          ) : <span className="text-default-400">无标题路径</span>}
        </div>
        <p className="whitespace-pre-wrap break-words text-sm leading-7">{chunk.content}</p>
        <div className="text-xs text-default-400">位置：{chunk.start_pos} - {chunk.end_pos} · {chunk.char_count} 字符</div>
      </CardBody>
    </Card>
  );
}

function TagManagerModal({ kbId, tags, open, onClose }: { kbId: string; tags: Tag[]; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<Tag | null>(null);
  const createMutation = useMutation({ mutationFn: () => createTag(kbId, name), onSuccess: () => refresh() });
  const updateMutation = useMutation({ mutationFn: () => updateTag(kbId, String(editing?.id), name), onSuccess: () => refresh() });
  const deleteMutation = useMutation({ mutationFn: (targetTagId: string) => deleteTag(kbId, targetTagId), onSuccess: () => refresh() });

  function refresh() {
    setName("");
    setEditing(null);
    queryClient.invalidateQueries({ queryKey: ["tags", kbId] });
    queryClient.invalidateQueries({ queryKey: ["documents", kbId] });
  }

  return (
    <Modal isOpen={open} onOpenChange={(nextOpen) => !nextOpen && onClose()} placement="center">
      <ModalContent>
        <ModalHeader>标签管理</ModalHeader>
        <ModalBody className="gap-4">
          <div className="grid gap-2 md:grid-cols-[1fr_auto]">
            <Input label={editing ? "重命名标签" : "新建标签"} value={name} onValueChange={setName} maxLength={64} />
            <Button className="self-end" color="primary" isDisabled={!name.trim()} isLoading={createMutation.isPending || updateMutation.isPending} onPress={() => (editing ? updateMutation.mutate() : createMutation.mutate())}>
              {editing ? "保存" : "新建"}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <Chip key={tag.id} variant="flat" endContent={<button className="ml-1 text-danger" type="button" aria-label={`删除 ${tag.name}`} onClick={() => deleteMutation.mutate(tag.id)}><X size={12} aria-hidden="true" /></button>}>
                <button type="button" onClick={() => { setEditing(tag); setName(tag.name); }}>{tag.name}</button>
              </Chip>
            ))}
          </div>
          {(createMutation.isError || updateMutation.isError || deleteMutation.isError) ? <Alert color="danger" variant="flat">标签操作失败，请检查是否重名。</Alert> : null}
        </ModalBody>
        <ModalFooter><Button variant="light" onPress={onClose}>关闭</Button></ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function CreateKbModal({ open, onClose, sourceKbs, onDone }: { open: boolean; onClose: () => void; sourceKbs: KnowledgeBase[]; onDone: () => void }) {
  const [type, setType] = useState<KnowledgeBaseType>("document");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [modelTag, setModelTag] = useState("");
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [autoIngest, setAutoIngest] = useState(false);
  const { data: models = [] } = useQuery({ queryKey: ["ollama-models"], queryFn: listOllamaModels, enabled: open });
  const queryClient = useQueryClient();
  const createMutation = useMutation({
    mutationFn: () => createKnowledgeBase(type === "document" ? { type, name, description, embedding_model_tag: modelTag } : { type, name, description, embedding_model_tag: modelTag, source_knowledge_base_ids: sourceIds, wiki_config: { auto_ingest: autoIngest } }),
    onSuccess: () => {
      onDone();
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      onClose();
      setName("");
      setDescription("");
      setSourceIds([]);
      setModelTag("");
    },
  });
  const usableModels = models.filter((model) => model.usable_for_v1);
  const canCreate = Boolean(name.trim() && modelTag && (type === "document" || sourceIds.length > 0));

  return (
    <Modal isOpen={open} onOpenChange={(nextOpen) => !nextOpen && onClose()} placement="center" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader>创建知识库</ModalHeader>
        <ModalBody className="gap-4">
          <Select label="知识库类型" selectedKeys={new Set([type])} onSelectionChange={(keys) => setType(firstKey(keys, "document") as KnowledgeBaseType)}>
            <SelectItem key="document">源知识库（Source KB）</SelectItem>
            <SelectItem key="wiki">Wiki 知识库（Wiki KB）</SelectItem>
          </Select>
          <Input label="名称" value={name} onValueChange={setName} isRequired />
          <Textarea label="描述" value={description} onValueChange={setDescription} />
          <Select label="Embedding 模型" placeholder="选择 1024 维可用模型" selectedKeys={modelTag ? new Set([modelTag]) : new Set([])} onSelectionChange={(keys) => setModelTag(firstKey(keys, ""))}>
            {usableModels.map((model) => <SelectItem key={model.tag}>{model.tag}</SelectItem>)}
          </Select>
          {type === "wiki" ? (
            <>
              <Select label="绑定 Source KB" placeholder="选择一个或多个源知识库" selectionMode="multiple" selectedKeys={new Set(sourceIds)} onSelectionChange={(keys) => setSourceIds(keys === "all" ? sourceKbs.map((kb) => kb.id) : Array.from(keys).map(String))}>
                {sourceKbs.map((kb) => <SelectItem key={kb.id}>{kb.name}</SelectItem>)}
              </Select>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={autoIngest} onChange={(event) => setAutoIngest(event.currentTarget.checked)} />上传新文档后自动更新 Wiki</label>
            </>
          ) : null}
          {createMutation.isError ? <Alert color="danger" variant="flat">创建失败，请检查模型或绑定配置。</Alert> : null}
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose}>取消</Button>
          <Button color="primary" isLoading={createMutation.isPending} isDisabled={!canCreate} onPress={() => createMutation.mutate()}>创建</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function KbDetailModal({ kbId, sourceKbs, canManage, onClose }: { kbId: string | null; sourceKbs: KnowledgeBase[]; canManage: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<EditableStatus>("active");
  const [chunkSize, setChunkSize] = useState("512");
  const [chunkOverlap, setChunkOverlap] = useState("80");
  const [autoIngest, setAutoIngest] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState("60");
  const [maxRetries, setMaxRetries] = useState("3");
  const [temperature, setTemperature] = useState("0.7");
  const [sourceToBind, setSourceToBind] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { data: kb, isLoading } = useQuery({ queryKey: ["kb", kbId], queryFn: () => getKnowledgeBase(String(kbId)), enabled: Boolean(kbId) });

  useEffect(() => {
    if (!kb) return;
    const chunking = kb.chunking_config ?? defaultChunking;
    const wikiConfig = kb.wiki_config ?? defaultWikiConfig;
    setName(kb.name);
    setDescription(kb.description);
    setStatus(kb.status === "disabled" ? "disabled" : "active");
    setChunkSize(String(chunking.chunk_size));
    setChunkOverlap(String(chunking.chunk_overlap));
    setAutoIngest(wikiConfig.auto_ingest);
    setTimeoutSeconds(String(wikiConfig.llm_timeout_seconds ?? defaultWikiConfig.llm_timeout_seconds));
    setMaxRetries(String(wikiConfig.llm_max_retries ?? defaultWikiConfig.llm_max_retries));
    setTemperature(String(wikiConfig.temperature ?? defaultWikiConfig.temperature));
    setSourceToBind("");
    setConfirmDelete(false);
  }, [kb]);

  const refreshKb = () => {
    queryClient.invalidateQueries({ queryKey: ["kbs"] });
    queryClient.invalidateQueries({ queryKey: ["kb", kbId] });
  };
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!kb) throw new Error("KB 未加载");
      const payload = kb.type === "document"
        ? { name, description, status, chunking_config: { chunk_size: Number(chunkSize), chunk_overlap: Number(chunkOverlap), strategy: "header_aware" as const } }
        : { name, description, status, wiki_config: { auto_ingest: autoIngest, llm_timeout_seconds: Number(timeoutSeconds), llm_max_retries: Number(maxRetries), temperature: Number(temperature) } };
      return updateKnowledgeBase(kb.id, payload);
    },
    onSuccess: refreshKb,
  });
  const deleteMutation = useMutation({ mutationFn: () => { if (!kb) throw new Error("KB 未加载"); return deleteKnowledgeBase(kb.id); }, onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["kbs"] }); onClose(); } });
  const bindMutation = useMutation({ mutationFn: () => { if (!kb || !sourceToBind) throw new Error("绑定参数不完整"); return bindSourceKnowledgeBase(kb.id, sourceToBind); }, onSuccess: () => { setSourceToBind(""); refreshKb(); } });
  const unbindMutation = useMutation({ mutationFn: (sourceKbId: string) => { if (!kb) throw new Error("KB 未加载"); return unbindSourceKnowledgeBase(kb.id, sourceKbId); }, onSuccess: refreshKb });
  const boundIds = new Set(kb?.bound_source_kbs?.map((source) => source.id) ?? []);
  const bindCandidates = sourceKbs.filter((source) => source.id !== kb?.id && !boundIds.has(source.id));

  return (
    <Modal isOpen={Boolean(kbId)} onOpenChange={(open) => !open && onClose()} size="3xl" placement="center" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader className="flex items-center gap-2">{kb?.type === "wiki" ? <GitBranch size={18} aria-hidden="true" /> : <Database size={18} aria-hidden="true" />}{kb?.name ?? "知识库详情"}</ModalHeader>
        <ModalBody className="gap-5">
          {isLoading || !kb ? <Skeleton className="h-72 w-full rounded-lg" /> : (
            <>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                <Input label="名称" value={name} onValueChange={setName} isReadOnly={!canManage} isRequired />
                <Select label="状态" selectedKeys={new Set([status])} onSelectionChange={(keys) => setStatus(firstKey(keys, "active") as EditableStatus)} isDisabled={!canManage}>
                  <SelectItem key="active">启用</SelectItem>
                  <SelectItem key="disabled">停用</SelectItem>
                </Select>
              </div>
              <Textarea label="描述" value={description} onValueChange={setDescription} isReadOnly={!canManage} />
              <div className="grid gap-3 text-sm md:grid-cols-3">
                <MetaItem label="类型" value={kb.type === "document" ? "Source KB" : "Wiki KB"} />
                <MetaItem label="Embedding" value={`${kb.embedding_model_tag} · ${kb.embedding_dim}`} />
                <MetaItem label="Digest" value={kb.embedding_model_digest} truncate />
              </div>
              {kb.type === "document" ? (
                <Card shadow="none" className="border border-divider">
                  <CardHeader className="py-3 text-sm font-semibold">分块配置</CardHeader>
                  <Divider />
                  <CardBody className="grid gap-3 md:grid-cols-3">
                    <Input label="分块大小" type="number" value={chunkSize} onValueChange={setChunkSize} isReadOnly={!canManage} />
                    <Input label="Overlap" type="number" value={chunkOverlap} onValueChange={setChunkOverlap} isReadOnly={!canManage} />
                    <Input label="策略" value="header_aware" isReadOnly />
                  </CardBody>
                </Card>
              ) : (
                <Card shadow="none" className="border border-divider">
                  <CardHeader className="py-3 text-sm font-semibold">Wiki 配置与 Source 绑定</CardHeader>
                  <Divider />
                  <CardBody className="gap-4">
                    <div className="grid gap-3 md:grid-cols-3">
                      <Input label="LLM 超时秒数" type="number" value={timeoutSeconds} onValueChange={setTimeoutSeconds} isReadOnly={!canManage} />
                      <Input label="最大重试" type="number" value={maxRetries} onValueChange={setMaxRetries} isReadOnly={!canManage} />
                      <Input label="温度" type="number" value={temperature} onValueChange={setTemperature} isReadOnly={!canManage} />
                    </div>
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={autoIngest} disabled={!canManage} onChange={(event) => setAutoIngest(event.currentTarget.checked)} />上传新文档后自动更新 Wiki</label>
                    <div className="flex flex-wrap gap-2">{(kb.bound_source_kbs ?? []).map((source) => <Chip key={source.id} variant="flat">{source.name}</Chip>)}</div>
                    {canManage ? (
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
                        <Select label="新增绑定" placeholder="选择 Source KB" selectedKeys={sourceToBind ? new Set([sourceToBind]) : new Set([])} onSelectionChange={(keys) => setSourceToBind(firstKey(keys, ""))} isDisabled={bindCandidates.length === 0}>
                          {bindCandidates.map((source) => <SelectItem key={source.id}>{source.name}</SelectItem>)}
                        </Select>
                        <Button className="self-end" variant="flat" startContent={<Link2 size={15} aria-hidden="true" />} isDisabled={!sourceToBind} isLoading={bindMutation.isPending} onPress={() => bindMutation.mutate()}>绑定</Button>
                      </div>
                    ) : null}
                    {canManage && (kb.bound_source_kbs ?? []).length > 0 ? <div className="flex flex-wrap gap-2">{(kb.bound_source_kbs ?? []).map((source) => <Button key={source.id} size="sm" variant="light" onPress={() => unbindMutation.mutate(source.id)}>解绑 {source.name}</Button>)}</div> : null}
                  </CardBody>
                </Card>
              )}
              {(saveMutation.isError || deleteMutation.isError || bindMutation.isError || unbindMutation.isError) ? <Alert color="danger" variant="flat">操作失败，请检查权限、参数或绑定关系后重试。</Alert> : null}
              {confirmDelete ? <Alert color="danger" variant="flat">删除会移除该知识库及相关绑定，请再次点击确认删除。</Alert> : null}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {canManage && kb ? <Button color="danger" variant="flat" startContent={<Trash2 size={15} aria-hidden="true" />} isLoading={deleteMutation.isPending} onPress={() => confirmDelete ? deleteMutation.mutate() : setConfirmDelete(true)}>删除</Button> : null}
          <Button variant="light" onPress={onClose}>关闭</Button>
          {canManage && kb ? <Button color="primary" startContent={<Save size={15} aria-hidden="true" />} isDisabled={!name.trim()} isLoading={saveMutation.isPending} onPress={() => saveMutation.mutate()}>保存</Button> : null}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function ChunkCard({ chunk }: { chunk: Chunk }) {
  return (
    <Card shadow="none" className="border border-divider">
      <CardBody className="gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-default-400">#{String(chunk.seq).padStart(3, "0")}</span>
          {chunk.header_path.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1 text-primary">
              {chunk.header_path.map((item, index) => <span key={`${item}-${index}`} className="inline-flex items-center gap-1">{index > 0 ? <span className="text-default-300">/</span> : null}{item}</span>)}
            </div>
          ) : <span className="text-default-400">无标题路径</span>}
        </div>
        <p className="whitespace-pre-wrap break-words text-sm leading-7">{chunk.content}</p>
        <div className="text-xs text-default-400">位置：{chunk.start_pos} - {chunk.end_pos} · {chunk.end_pos - chunk.start_pos} 字符</div>
      </CardBody>
    </Card>
  );
}

function MetaLine({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-3"><span>{label}</span><span className="truncate font-medium text-foreground">{value}</span></div>;
}

function MetaItem({ label, value, truncate = false }: { label: string; value: string; truncate?: boolean }) {
  return (
    <div className="min-w-0 rounded-md border border-divider bg-default-50 px-3 py-2">
      <div className="text-xs text-default-500">{label}</div>
      <div className={truncate ? "truncate font-medium" : "font-medium"}>{value}</div>
    </div>
  );
}

function kbStatusLabel(status: KnowledgeBase["status"]) {
  const labels: Record<KnowledgeBase["status"], string> = { active: "启用", building: "构建中", disabled: "停用", embedding_incompatible: "模型不兼容" };
  return labels[status];
}

function documentStatusLabel(status: DocumentStatus) {
  const labels: Record<DocumentStatus, string> = { pending: "待处理", running: "处理中", completed: "已完成", failed: "失败" };
  return labels[status];
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
