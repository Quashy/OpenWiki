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
import { Database, GitBranch, Plus, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { createKnowledgeBase, listKnowledgeBases, listOllamaModels, type KnowledgeBase, type KnowledgeBaseType } from "../api/m1";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";

export function KnowledgeBasePage({ canManage }: { canManage: boolean }) {
  const [open, setOpen] = useState(false);
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
      <KbSection title="源知识库（Source KB）" icon={Database} items={sourceKbs} empty="还没有源知识库" isLoading={isLoading} />
      <KbSection title="Wiki 知识库（Wiki KB）" icon={GitBranch} items={wikiKbs} empty="还没有 Wiki 知识库" isLoading={isLoading} />
      <CreateKbModal open={open} onClose={() => setOpen(false)} sourceKbs={sourceKbs} onDone={() => queryClient.invalidateQueries({ queryKey: ["kbs"] })} />
    </section>
  );
}

function KbSection({
  title,
  icon: Icon,
  items,
  empty,
  isLoading,
}: {
  title: string;
  icon: LucideIcon;
  items: KnowledgeBase[];
  empty: string;
  isLoading: boolean;
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
              <Card key={kb.id} shadow="none" className="border border-divider">
                <CardHeader className="items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold">{kb.name}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-default-500">{kb.description || "暂无描述"}</p>
                  </div>
                  <Chip color={kb.status === "active" ? "success" : "default"} size="sm" variant="flat">
                    {kb.status}
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
  const [sourceId, setSourceId] = useState("");
  const [autoIngest, setAutoIngest] = useState(false);
  const { data: models = [] } = useQuery({ queryKey: ["ollama-models"], queryFn: listOllamaModels, enabled: open });
  const queryClient = useQueryClient();
  const createMutation = useMutation({
    mutationFn: () =>
      createKnowledgeBase(
        type === "document"
          ? { type, name, description, embedding_model_tag: modelTag }
          : { type, name, description, embedding_model_tag: modelTag, source_knowledge_base_ids: [sourceId], wiki_config: { auto_ingest: autoIngest } },
      ),
    onSuccess: () => {
      onDone();
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      onClose();
      setName("");
      setDescription("");
      setSourceId("");
      setModelTag("");
    },
  });
  const usableModels = models.filter((model) => model.usable_for_v1);

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
              <Select label="绑定 Source KB" selectedKeys={sourceId ? new Set([sourceId]) : new Set([])} onSelectionChange={(keys) => setSourceId(firstKey(keys, ""))}>
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
          <Button color="primary" isLoading={createMutation.isPending} onPress={() => createMutation.mutate()}>
            创建
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
