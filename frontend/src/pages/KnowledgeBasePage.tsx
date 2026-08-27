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
  Select,
  SelectItem,
  Skeleton,
  Switch,
  Textarea,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Eye, GitBranch, Link2, Plus, Save, Trash2, Unlink2, type LucideIcon } from "lucide-react";
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
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";

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

export function KnowledgeBasePage({ canManage }: { canManage: boolean }) {
  const [open, setOpen] = useState(false);
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ["kbs"], queryFn: () => listKnowledgeBases() });
  const sourceKbs = data.filter((kb) => kb.type === "document");
  const wikiKbs = data.filter((kb) => kb.type === "wiki");

  return (
    <section className="space-y-6">
      <PageHeader
        title="知识库"
        description="管理源文档和自动生成的 Wiki 知识库"
        action={
          canManage ? (
            <Button color="primary" startContent={<Plus size={16} aria-hidden="true" />} onPress={() => setOpen(true)}>
              创建知识库
            </Button>
          ) : null
        }
      />
      <KbSection title="源知识库（Source KB）" icon={Database} items={sourceKbs} empty="还没有源知识库" isLoading={isLoading} onOpen={setSelectedKbId} />
      <KbSection title="Wiki 知识库（Wiki KB）" icon={GitBranch} items={wikiKbs} empty="还没有 Wiki 知识库" isLoading={isLoading} onOpen={setSelectedKbId} />
      <CreateKbModal open={open} onClose={() => setOpen(false)} sourceKbs={sourceKbs} onDone={() => queryClient.invalidateQueries({ queryKey: ["kbs"] })} />
      <KbDetailModal kbId={selectedKbId} sourceKbs={sourceKbs} canManage={canManage} onClose={() => setSelectedKbId(null)} />
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
}: {
  title: string;
  icon: LucideIcon;
  items: KnowledgeBase[];
  empty: string;
  isLoading: boolean;
  onOpen: (kbId: string) => void;
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
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-2">
                      <Skeleton className="h-4 w-3/5 rounded-md" />
                      <Skeleton className="h-3 w-full rounded-md" />
                      <Skeleton className="h-3 w-4/5 rounded-md" />
                    </div>
                    <Skeleton className="h-6 w-14 rounded-full" />
                  </div>
                  <div className="space-y-3 pt-2">
                    <Skeleton className="h-3 w-full rounded-md" />
                    <Skeleton className="h-3 w-5/6 rounded-md" />
                    <Skeleton className="h-3 w-2/3 rounded-md" />
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="grid min-h-28 place-items-center text-sm text-default-500">{empty}</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((kb) => (
              <Card key={kb.id} shadow="none" className="border border-divider transition-colors hover:border-primary-200">
                <CardHeader className="items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold">{kb.name}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-default-500">{kb.description || "暂无描述"}</p>
                  </div>
                  <Chip color={kb.status === "active" ? "success" : "default"} size="sm" variant="flat">
                    {statusLabel(kb.status)}
                  </Chip>
                </CardHeader>
                <CardBody className="gap-3 pt-0 text-sm text-default-500">
                  <div className="flex items-center justify-between gap-3">
                    <span>Embedding</span>
                    <Chip size="sm" variant="flat">
                      {kb.embedding_model_tag}
                    </Chip>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>维度</span>
                    <span className="tabular-nums">{kb.embedding_dim}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>{kb.type === "wiki" ? "绑定 Source" : "文档数"}</span>
                    <span className="tabular-nums">{kb.type === "wiki" ? (kb.bound_source_kbs?.length ?? 0) : (kb.document_count ?? 0)}</span>
                  </div>
                  <Button
                    className="mt-2"
                    size="sm"
                    variant="flat"
                    startContent={<Eye size={15} aria-hidden="true" />}
                    onPress={() => onOpen(kb.id)}
                  >
                    查看详情
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
    mutationFn: () =>
      createKnowledgeBase(
        type === "document"
          ? { type, name, description, embedding_model_tag: modelTag }
          : { type, name, description, embedding_model_tag: modelTag, source_knowledge_base_ids: sourceIds, wiki_config: { auto_ingest: autoIngest } },
      ),
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
          <Select
            label="Embedding 模型"
            placeholder="选择 1024 维可用模型"
            selectedKeys={modelTag ? new Set([modelTag]) : new Set([])}
            onSelectionChange={(keys) => setModelTag(firstKey(keys, ""))}
          >
            {usableModels.map((model) => (
              <SelectItem key={model.tag}>{model.tag}</SelectItem>
            ))}
          </Select>
          {type === "wiki" ? (
            <>
              <Select
                label="绑定 Source KB"
                placeholder="选择一个或多个源知识库"
                selectionMode="multiple"
                selectedKeys={new Set(sourceIds)}
                onSelectionChange={(keys) => setSourceIds(keys === "all" ? sourceKbs.map((kb) => kb.id) : Array.from(keys).map(String))}
              >
                {sourceKbs.map((kb) => (
                  <SelectItem key={kb.id}>{kb.name}</SelectItem>
                ))}
              </Select>
              <Switch isSelected={autoIngest} onValueChange={setAutoIngest}>
                上传新文档后自动更新 Wiki
              </Switch>
            </>
          ) : null}
          {createMutation.isError ? (
            <Alert color="danger" variant="flat">
              创建失败，请检查模型或绑定配置。
            </Alert>
          ) : null}
        </ModalBody>
        <ModalFooter>
          <Button variant="light" onPress={onClose}>
            取消
          </Button>
          <Button color="primary" isLoading={createMutation.isPending} isDisabled={!canCreate} onPress={() => createMutation.mutate()}>
            创建
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function KbDetailModal({
  kbId,
  sourceKbs,
  canManage,
  onClose,
}: {
  kbId: string | null;
  sourceKbs: KnowledgeBase[];
  canManage: boolean;
  onClose: () => void;
}) {
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

  const { data: kb, isLoading } = useQuery({
    queryKey: ["kb", kbId],
    queryFn: () => getKnowledgeBase(String(kbId)),
    enabled: Boolean(kbId),
  });

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
      const payload =
        kb.type === "document"
          ? {
              name,
              description,
              status,
              chunking_config: {
                chunk_size: Number(chunkSize),
                chunk_overlap: Number(chunkOverlap),
                strategy: "header_aware" as const,
              },
            }
          : {
              name,
              description,
              status,
              wiki_config: {
                auto_ingest: autoIngest,
                llm_timeout_seconds: Number(timeoutSeconds),
                llm_max_retries: Number(maxRetries),
                temperature: Number(temperature),
              },
            };
      return updateKnowledgeBase(kb.id, payload);
    },
    onSuccess: refreshKb,
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!kb) throw new Error("KB 未加载");
      return deleteKnowledgeBase(kb.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      onClose();
    },
  });

  const bindMutation = useMutation({
    mutationFn: () => {
      if (!kb || !sourceToBind) throw new Error("绑定参数不完整");
      return bindSourceKnowledgeBase(kb.id, sourceToBind);
    },
    onSuccess: () => {
      setSourceToBind("");
      refreshKb();
    },
  });

  const unbindMutation = useMutation({
    mutationFn: (sourceKbId: string) => {
      if (!kb) throw new Error("KB 未加载");
      return unbindSourceKnowledgeBase(kb.id, sourceKbId);
    },
    onSuccess: refreshKb,
  });

  const boundIds = new Set(kb?.bound_source_kbs?.map((source) => source.id) ?? []);
  const bindCandidates = sourceKbs.filter((source) => source.id !== kb?.id && !boundIds.has(source.id));
  const disableSave = !canManage || !name.trim() || saveMutation.isPending;

  return (
    <Modal isOpen={Boolean(kbId)} onOpenChange={(open) => !open && onClose()} size="3xl" placement="center" scrollBehavior="inside">
      <ModalContent>
        <ModalHeader className="flex items-center gap-2">
          {kb?.type === "wiki" ? <GitBranch size={18} aria-hidden="true" /> : <Database size={18} aria-hidden="true" />}
          {kb?.name ?? "知识库详情"}
        </ModalHeader>
        <ModalBody className="gap-5">
          {isLoading || !kb ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full rounded-lg" />
              <Skeleton className="h-24 w-full rounded-lg" />
              <Skeleton className="h-40 w-full rounded-lg" />
            </div>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                <Input label="名称" value={name} onValueChange={setName} isReadOnly={!canManage} isRequired />
                <Select
                  label="状态"
                  selectedKeys={new Set([status])}
                  onSelectionChange={(keys) => setStatus(firstKey(keys, "active") as EditableStatus)}
                  isDisabled={!canManage}
                >
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
                    <Switch isSelected={autoIngest} onValueChange={setAutoIngest} isDisabled={!canManage}>
                      上传新文档后自动更新 Wiki
                    </Switch>
                    <div className="flex flex-wrap gap-2">
                      {(kb.bound_source_kbs ?? []).length > 0 ? (
                        (kb.bound_source_kbs ?? []).map((source) => (
                          <Chip key={source.id} variant="flat" endContent={canManage ? <Unlink2 size={13} aria-hidden="true" /> : undefined}>
                            <button
                              className="inline-flex max-w-44 items-center gap-1 truncate"
                              disabled={!canManage || unbindMutation.isPending}
                              onClick={() => unbindMutation.mutate(source.id)}
                              type="button"
                            >
                              {source.name}
                            </button>
                          </Chip>
                        ))
                      ) : (
                        <span className="text-sm text-default-500">尚未绑定 Source KB</span>
                      )}
                    </div>
                    {canManage ? (
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
                        <Select
                          label="新增绑定"
                          placeholder="选择 Source KB"
                          selectedKeys={sourceToBind ? new Set([sourceToBind]) : new Set([])}
                          onSelectionChange={(keys) => setSourceToBind(firstKey(keys, ""))}
                          isDisabled={bindCandidates.length === 0}
                        >
                          {bindCandidates.map((source) => (
                            <SelectItem key={source.id}>{source.name}</SelectItem>
                          ))}
                        </Select>
                        <Button
                          className="self-end"
                          variant="flat"
                          startContent={<Link2 size={15} aria-hidden="true" />}
                          isDisabled={!sourceToBind}
                          isLoading={bindMutation.isPending}
                          onPress={() => bindMutation.mutate()}
                        >
                          绑定
                        </Button>
                      </div>
                    ) : null}
                  </CardBody>
                </Card>
              )}
              {(saveMutation.isError || deleteMutation.isError || bindMutation.isError || unbindMutation.isError) && (
                <Alert color="danger" variant="flat">
                  操作失败，请检查权限、参数或绑定关系后重试。
                </Alert>
              )}
              {confirmDelete ? (
                <Alert
                  color="danger"
                  variant="flat"
                  endContent={
                    <div className="flex gap-2">
                      <Button size="sm" variant="light" onPress={() => setConfirmDelete(false)}>
                        取消
                      </Button>
                      <Button size="sm" color="danger" isLoading={deleteMutation.isPending} onPress={() => deleteMutation.mutate()}>
                        确认删除
                      </Button>
                    </div>
                  }
                >
                  删除会移除该知识库及相关绑定，请确认。
                </Alert>
              ) : null}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {canManage && kb ? (
            <Button color="danger" variant="flat" startContent={<Trash2 size={15} aria-hidden="true" />} onPress={() => setConfirmDelete(true)}>
              删除
            </Button>
          ) : null}
          <Button variant="light" onPress={onClose}>
            关闭
          </Button>
          {canManage && kb ? (
            <Button color="primary" startContent={<Save size={15} aria-hidden="true" />} isDisabled={disableSave} isLoading={saveMutation.isPending} onPress={() => saveMutation.mutate()}>
              保存
            </Button>
          ) : null}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function MetaItem({ label, value, truncate = false }: { label: string; value: string; truncate?: boolean }) {
  return (
    <div className="min-w-0 rounded-md border border-divider bg-default-50 px-3 py-2">
      <div className="text-xs text-default-500">{label}</div>
      <div className={truncate ? "truncate font-medium" : "font-medium"}>{value}</div>
    </div>
  );
}

function statusLabel(status: KnowledgeBase["status"]) {
  const labels: Record<KnowledgeBase["status"], string> = {
    active: "启用",
    building: "构建中",
    disabled: "停用",
    embedding_incompatible: "模型不兼容",
  };
  return labels[status];
}
