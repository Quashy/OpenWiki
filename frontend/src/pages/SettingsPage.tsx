import { Alert, Button, Card, CardBody, CardHeader, Chip, Divider, Input, Select, SelectItem, Table, TableBody, TableCell, TableColumn, TableHeader, TableRow } from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

import { getLlmConfig, getOllamaConfig, listOllamaModels, probeOllamaModel, testLlmConfig, updateLlmConfig, updateOllamaConfig } from "../api/m1";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: llm } = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const { data: ollama } = useQuery({ queryKey: ["ollama-config"], queryFn: getOllamaConfig });
  const { data: models = [] } = useQuery({ queryKey: ["ollama-models"], queryFn: listOllamaModels });
  const [apiKey, setApiKey] = useState("");
  const [probeTag, setProbeTag] = useState("");
  const [probeResult, setProbeResult] = useState("");
  const [llmForm, setLlmForm] = useState({
    provider: "openai" as "openai" | "deepseek",
    model: "gpt-4o-mini",
    base_url: "https://api.openai.com/v1",
    temperature: 0.7,
    max_tokens: 4096,
    timeout_seconds: 60,
  });
  const [ollamaUrl, setOllamaUrl] = useState("http://host.docker.internal:11434");

  useEffect(() => {
    if (llm) {
      setLlmForm({
        provider: llm.provider,
        model: llm.model,
        base_url: llm.base_url,
        temperature: llm.temperature,
        max_tokens: llm.max_tokens,
        timeout_seconds: llm.timeout_seconds,
      });
    }
  }, [llm]);

  useEffect(() => {
    if (ollama) setOllamaUrl(ollama.base_url);
  }, [ollama]);

  const saveLlm = useMutation({
    mutationFn: () => updateLlmConfig({ ...llmForm, api_key: apiKey || undefined }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["llm-config"] }),
  });
  const llmTest = useMutation({ mutationFn: testLlmConfig });
  const saveOllama = useMutation({
    mutationFn: () => updateOllamaConfig(ollamaUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ollama-config"] });
      queryClient.invalidateQueries({ queryKey: ["ollama-models"] });
    },
  });
  const probe = useMutation({
    mutationFn: () => probeOllamaModel(probeTag),
    onSuccess: (result) => setProbeResult(`${result.tag}: ${result.usable_for_v1 ? "可用于 v1" : result.unusable_reason}`),
  });

  return (
    <section className="space-y-5">
      <PageHeader title="模型设置" description="配置全局 LLM 和本地 Ollama embedding 模型发现。" />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card shadow="sm">
          <CardHeader className="gap-2">
            <KeyRound size={18} aria-hidden="true" />
            <h2 className="font-semibold">LLM 配置</h2>
          </CardHeader>
          <Divider />
          <CardBody className="gap-4">
            <Select
              label="提供商"
              selectedKeys={new Set([llmForm.provider])}
              onSelectionChange={(keys) => setLlmForm((current) => ({ ...current, provider: firstKey(keys, "openai") as "openai" | "deepseek" }))}
            >
              <SelectItem key="openai">OpenAI</SelectItem>
              <SelectItem key="deepseek">DeepSeek</SelectItem>
            </Select>
            <Input label="模型" value={llmForm.model} onValueChange={(model) => setLlmForm((current) => ({ ...current, model }))} />
            <Input label="Base URL" value={llmForm.base_url} onValueChange={(base_url) => setLlmForm((current) => ({ ...current, base_url }))} />
            <Input label="API Key" type="password" placeholder={llm?.api_key_masked || "未配置"} value={apiKey} onValueChange={setApiKey} />
            <div className="grid gap-3 md:grid-cols-3">
              <Input label="温度" type="number" value={String(llmForm.temperature)} onValueChange={(value) => setLlmForm((current) => ({ ...current, temperature: Number(value) }))} />
              <Input label="Max Tokens" type="number" value={String(llmForm.max_tokens)} onValueChange={(value) => setLlmForm((current) => ({ ...current, max_tokens: Number(value) }))} />
              <Input label="超时秒数" type="number" value={String(llmForm.timeout_seconds)} onValueChange={(value) => setLlmForm((current) => ({ ...current, timeout_seconds: Number(value) }))} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button color="primary" isLoading={saveLlm.isPending} onPress={() => saveLlm.mutate()}>
                保存
              </Button>
              <Button variant="flat" isLoading={llmTest.isPending} onPress={() => llmTest.mutate()}>
                测试连通性
              </Button>
            </div>
            {llmTest.data ? (
              <Alert color={llmTest.data.ok ? "success" : "warning"} variant="flat">
                {llmTest.data.message}
              </Alert>
            ) : null}
          </CardBody>
        </Card>

        <Card shadow="sm">
          <CardHeader className="gap-2">
            <Bot size={18} aria-hidden="true" />
            <h2 className="font-semibold">Ollama Embedding</h2>
          </CardHeader>
          <Divider />
          <CardBody className="gap-4">
            <Input label="Ollama 地址" value={ollamaUrl} onValueChange={setOllamaUrl} />
            <div className="grid gap-3 md:grid-cols-[auto_minmax(220px,1fr)_auto]">
              <Button color="primary" isLoading={saveOllama.isPending} onPress={() => saveOllama.mutate()}>
                保存地址
              </Button>
              <Input label="探测模型 Tag" value={probeTag} onValueChange={setProbeTag} />
              <Button variant="flat" isLoading={probe.isPending} onPress={() => probe.mutate()}>
                探测
              </Button>
            </div>
            {probeResult ? <Chip>{probeResult}</Chip> : null}
            <Table aria-label="Ollama 模型列表" shadow="none">
              <TableHeader>
                <TableColumn>Tag</TableColumn>
                <TableColumn>能力</TableColumn>
                <TableColumn>维度</TableColumn>
                <TableColumn>v1 可用</TableColumn>
              </TableHeader>
              <TableBody emptyContent="未发现模型">
                {models.map((model) => (
                  <TableRow key={model.tag}>
                    <TableCell>{model.tag}</TableCell>
                    <TableCell>{model.capabilities.join(", ") || "-"}</TableCell>
                    <TableCell>{model.embedding_dim ?? "-"}</TableCell>
                    <TableCell>
                      <Chip color={model.usable_for_v1 ? "success" : "warning"} size="sm" variant="flat">
                        {model.usable_for_v1 ? "可用" : model.unusable_reason}
                      </Chip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      </div>
    </section>
  );
}

