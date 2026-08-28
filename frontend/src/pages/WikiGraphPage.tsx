import { Alert, Button, Card, CardBody, Chip, Divider, Select, SelectItem, Skeleton } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import * as echarts from "echarts";
import { Network, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { listKnowledgeBases } from "../api/m1";
import { getWikiGraph, type WikiGraph, type WikiGraphNode } from "../api/m3";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";

export function WikiGraphPage({ onOpenPage }: { onOpenPage: (pageId: string) => void }) {
  const [kbId, setKbId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [relationType, setRelationType] = useState("");
  const { data: wikiKbs = [] } = useQuery({
    queryKey: ["kbs", "wiki"],
    queryFn: () => listKnowledgeBases({ type: "wiki" }),
  });
  useEffect(() => {
    if (!kbId && wikiKbs.length > 0) setKbId(wikiKbs[0].id);
  }, [kbId, wikiKbs]);
  const graphQuery = useQuery({
    queryKey: ["wiki-graph", kbId, entityType, relationType],
    queryFn: () => getWikiGraph({ kbId, entity_type: entityType || undefined, relation_type: relationType || undefined }),
    enabled: Boolean(kbId),
    retry: false,
  });
  const graph = graphQuery.data;
  const entityTypes = useMemo(() => unique(graph?.nodes.map((node) => node.entity_type) ?? []), [graph?.nodes]);
  const relationTypes = useMemo(() => unique(graph?.edges.map((edge) => edge.relation_type) ?? []), [graph?.edges]);
  const selectedKb = wikiKbs.find((kb) => kb.id === kbId);

  return (
    <section className="space-y-5">
      <PageHeader
        title="知识图谱"
        description="从 Wiki Reduce 阶段沉淀的实体关系网络"
        action={
          <Button variant="flat" startContent={<RefreshCw size={16} aria-hidden="true" />} onPress={() => graphQuery.refetch()}>
            刷新
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Card shadow="sm" className="min-w-0">
          <CardBody className="p-0">
            <div className="grid gap-3 border-b border-divider p-3 md:grid-cols-3">
              <Select aria-label="选择 Wiki KB" placeholder="选择 Wiki KB" selectedKeys={kbId ? new Set([kbId]) : new Set([])} onSelectionChange={(keys) => setKbId(firstKey(keys, ""))}>
                {wikiKbs.map((kb) => (
                  <SelectItem key={kb.id}>{kb.name}</SelectItem>
                ))}
              </Select>
              <Select aria-label="实体类型" placeholder="全部实体类型" selectedKeys={entityType ? new Set([entityType]) : new Set([])} onSelectionChange={(keys) => setEntityType(firstKey(keys, ""))}>
                {entityTypes.map((type) => (
                  <SelectItem key={type}>{type}</SelectItem>
                ))}
              </Select>
              <Select aria-label="关系类型" placeholder="全部关系类型" selectedKeys={relationType ? new Set([relationType]) : new Set([])} onSelectionChange={(keys) => setRelationType(firstKey(keys, ""))}>
                {relationTypes.map((type) => (
                  <SelectItem key={type}>{type}</SelectItem>
                ))}
              </Select>
            </div>
            {graphQuery.isLoading ? <Skeleton className="h-[calc(100vh-15rem)] min-h-[520px] rounded-none" /> : null}
            {graphQuery.isError ? <div className="p-5"><Alert color="warning" variant="flat">图谱暂不可用，可能正在重建或尚未生成。</Alert></div> : null}
            {!graphQuery.isLoading && !graphQuery.isError ? (
              <GraphCanvas graph={graph ?? { nodes: [], edges: [] }} onOpenPage={onOpenPage} />
            ) : null}
          </CardBody>
        </Card>
        <Card shadow="sm">
          <CardBody className="gap-4">
            <div>
              <div className="text-xs text-default-500">当前 Wiki</div>
              <div className="mt-1 font-semibold">{selectedKb?.name ?? "未选择"}</div>
            </div>
            <Divider />
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Metric label="节点" value={String(graph?.nodes.length ?? 0)} />
              <Metric label="关系" value={String(graph?.edges.length ?? 0)} />
            </div>
            <Divider />
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Network size={16} aria-hidden="true" />
                节点
              </div>
              <div className="max-h-[calc(100vh-26rem)] space-y-2 overflow-auto">
                {(graph?.nodes ?? []).map((node) => (
                  <NodeRow key={node.id} node={node} onOpenPage={onOpenPage} />
                ))}
                {(graph?.nodes ?? []).length === 0 ? <div className="text-sm text-default-500">暂无节点</div> : null}
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </section>
  );
}

function GraphCanvas({ graph, onOpenPage }: { graph: WikiGraph; onOpenPage: (pageId: string) => void }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      tooltip: {},
      animationDurationUpdate: 400,
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          force: { repulsion: 180, edgeLength: 120 },
          label: { show: true, formatter: "{b}", fontSize: 12 },
          data: graph.nodes.map((node) => ({
            id: node.id,
            name: node.name,
            value: node.entity_type,
            symbolSize: node.entity_type === "tech" ? 54 : 44,
            itemStyle: { color: colorForType(node.entity_type) },
            wiki_page_id: node.wiki_page_id,
          })),
          links: graph.edges.map((edge) => ({
            source: edge.source_entity_id,
            target: edge.target_entity_id,
            label: { show: true, formatter: edge.relation_type, fontSize: 11 },
            lineStyle: { width: 1.4, opacity: 0.7 },
          })),
          edgeSymbol: ["none", "arrow"],
          emphasis: { focus: "adjacency" },
        },
      ],
    });
    chart.on("click", (params) => {
      const data = params.data as { wiki_page_id?: string | null } | undefined;
      if (params.dataType === "node" && data?.wiki_page_id) onOpenPage(data.wiki_page_id);
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [graph, onOpenPage]);
  return <div ref={ref} className="h-[calc(100vh-15rem)] min-h-[520px]" aria-label="知识图谱" />;
}

function NodeRow({ node, onOpenPage }: { node: WikiGraphNode; onOpenPage: (pageId: string) => void }) {
  return (
    <div className="rounded-md border border-divider px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-sm font-medium">{node.name}</span>
        <Chip size="sm" variant="flat">{node.entity_type}</Chip>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-xs text-default-400">{node.slug}</span>
        {node.wiki_page_id ? (
          <Button size="sm" variant="light" onPress={() => onOpenPage(String(node.wiki_page_id))}>
            打开
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-default-50 px-3 py-2">
      <div className="text-xs text-default-500">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function colorForType(type: string) {
  const colors: Record<string, string> = {
    person: "#2563eb",
    org: "#059669",
    product: "#c2410c",
    place: "#7c3aed",
    tech: "#0f766e",
    event: "#b45309",
    other: "#52525b",
  };
  return colors[type] ?? colors.other;
}
