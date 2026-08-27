import { Card, CardBody } from "@heroui/react";
import * as echarts from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { RouteKey } from "../app/navigation";

export function GraphPlaceholder() {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      title: { text: "知识图谱将在 M3 接入真实数据", left: "center", top: "45%" },
      series: [{ type: "graph", data: [], links: [], roam: true }],
    });
    return () => chart.dispose();
  }, []);

  return (
    <Card shadow="sm">
      <CardBody>
        <div ref={ref} className="h-[calc(100vh-11rem)] min-h-96" aria-label="知识图谱空状态" />
      </CardBody>
    </Card>
  );
}

export function MilestonePlaceholder({ title, route }: { title: string; route: RouteKey }) {
  const milestone = useMemo(() => {
    if (route === "wiki" || route === "graph") return "M3";
    if (route === "chat") return "M4";
    return "M5";
  }, [route]);

  return (
    <Card shadow="sm">
      <CardBody className="grid min-h-80 place-items-center text-center">
        <div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-2 text-sm text-default-500">{milestone} 里程碑启用；M1 仅保留导航结构。</p>
        </div>
      </CardBody>
    </Card>
  );
}

