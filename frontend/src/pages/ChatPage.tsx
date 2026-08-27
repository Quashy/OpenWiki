import {
  Button,
  Chip,
  Divider,
  ScrollShadow,
  Select,
  SelectItem,
  Spinner,
  Textarea,
  Tooltip,
} from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { Bot, FileSearch, MessageSquare, PenLine, Plus, Send, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { listKnowledgeBases } from "../api/m1";
import { firstKey } from "../app/navigation";

const recommendedQuestions = [
  "这个知识库的核心结论是什么？",
  "有哪些关键概念和来源引用？",
  "哪些内容存在冲突或缺口？",
  "帮我按主题整理相关页面",
];

export function ChatPage() {
  const [selectedKbId, setSelectedKbId] = useState("");
  const { data: knowledgeBases = [], isLoading } = useQuery({
    queryKey: ["kbs", "chat"],
    queryFn: () => listKnowledgeBases(),
  });
  const activeKb = useMemo(() => knowledgeBases.find((kb) => kb.id === selectedKbId), [knowledgeBases, selectedKbId]);
  const canAsk = Boolean(activeKb);

  return (
    <section className="-m-4 flex min-h-[calc(100vh-3.5rem)] flex-col overflow-hidden bg-default-50 sm:-m-6 lg:h-[calc(100vh-3.5rem)] lg:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-divider bg-background lg:w-[260px] lg:border-b-0 lg:border-r">
        <div className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-sm font-semibold">智能问答</h1>
              <p className="mt-1 text-xs text-default-500">单 KB 会话与引用问答</p>
            </div>
            <Tooltip content="M4 启用新建会话">
              <Button isIconOnly size="sm" variant="flat" isDisabled aria-label="新建会话">
                <Plus size={16} aria-hidden="true" />
              </Button>
            </Tooltip>
          </div>
          <Select
            label="查询知识库"
            placeholder={isLoading ? "加载中" : "选择知识库"}
            size="sm"
            selectedKeys={selectedKbId ? new Set([selectedKbId]) : new Set([])}
            onSelectionChange={(keys) => setSelectedKbId(firstKey(keys, ""))}
            isDisabled={isLoading || knowledgeBases.length === 0}
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
        <ScrollShadow className="max-h-44 flex-1 p-3 lg:max-h-none">
          <div className="grid min-h-32 place-items-center rounded-lg border border-dashed border-divider px-4 py-8 text-center">
            <div>
              <MessageSquare className="mx-auto mb-3 text-default-300" size={28} aria-hidden="true" />
              <p className="text-sm font-medium text-default-600">暂无会话</p>
              <p className="mt-1 text-xs leading-5 text-default-500">M4 接入后显示历史会话、重命名和删除操作。</p>
            </div>
          </div>
        </ScrollShadow>
        <div className="border-t border-divider p-3">
          <Button fullWidth variant="flat" startContent={<PenLine size={16} aria-hidden="true" />} isDisabled>
            新建会话
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-divider bg-background px-4 sm:px-6">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">{activeKb?.name ?? "选择知识库，开始提问"}</h2>
            <p className="mt-0.5 truncate text-xs text-default-500">向量 + BM25 + GraphRAG 三路混合检索；回答附带来源引用。</p>
          </div>
          <Chip color={canAsk ? "primary" : "default"} variant="flat">
            {canAsk ? "已选择 KB" : "M4 启用"}
          </Chip>
        </div>

        <ScrollShadow className="flex-1">
          <div className="mx-auto flex min-h-[420px] w-full max-w-3xl flex-col px-4 py-8 sm:px-6 lg:min-h-[calc(100vh-12rem)]">
            <div className="mt-auto grid place-items-center text-center">
              <span className="grid size-14 place-items-center rounded-full bg-primary/10 text-primary">
                <Bot size={28} aria-hidden="true" />
              </span>
              <h3 className="mt-4 text-lg font-semibold">智能问答将在 M4 接入真实会话</h3>
              <p className="mt-2 max-w-md text-sm leading-6 text-default-500">
                当前保留原型布局：左侧会话列表、知识库选择、右侧对话区、底部输入栏。M1 不调用未交付的 Chat API。
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {recommendedQuestions.map((question) => (
                <Button key={question} variant="flat" className="h-auto justify-start whitespace-normal py-3 text-left" isDisabled>
                  <Sparkles className="shrink-0 text-default-400" size={16} aria-hidden="true" />
                  <span>{question}</span>
                </Button>
              ))}
            </div>
          </div>
        </ScrollShadow>

        <div className="border-t border-divider bg-background px-4 py-4 sm:px-6">
          <div className="mx-auto flex max-w-3xl items-end gap-3">
            <Textarea
              minRows={1}
              maxRows={5}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              variant="bordered"
              isDisabled
              startContent={<FileSearch className="mt-2 shrink-0 text-default-400" size={16} aria-hidden="true" />}
              classNames={{ inputWrapper: "min-h-11" }}
            />
            <Button isIconOnly color="primary" className="h-11 w-11 shrink-0" isDisabled aria-label="发送问题">
              {isLoading ? <Spinner size="sm" color="white" /> : <Send size={18} aria-hidden="true" />}
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-default-500">单 KB 问答、SSE 流式输出、引用跳转将在 M4 启用。</p>
        </div>
      </div>
    </section>
  );
}
