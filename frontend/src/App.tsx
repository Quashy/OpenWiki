import { Activity, Database, FileCheck2, GitBranch, Server, ShieldCheck } from "lucide-react";

import { HealthBadge } from "./components/HealthBadge";

const lanes = [
  { icon: Database, label: "Source KB", value: "0" },
  { icon: GitBranch, label: "Wiki KB", value: "0" },
  { icon: FileCheck2, label: "Documents", value: "0" },
  { icon: Activity, label: "Tasks", value: "0" },
];

function App() {
  return (
    <main className="min-h-screen bg-[#f7f5f0] text-[#1d2524]">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-5 sm:px-8">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#d8d2c6] pb-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center border border-[#1d2524] bg-[#dfe85f]">
              <ShieldCheck size={22} strokeWidth={1.8} />
            </div>
            <div>
              <h1 className="text-xl font-semibold leading-tight">OpenWiki V2</h1>
              <p className="text-sm text-[#66706a]">工程基线</p>
            </div>
          </div>
          <HealthBadge />
        </header>

        <section className="grid flex-1 gap-5 py-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="flex flex-col justify-between border border-[#d8d2c6] bg-[#fffdf7] p-6">
            <div>
              <div className="mb-10 flex items-center gap-2 text-sm text-[#66706a]">
                <Server size={16} />
                <span>M0 Baseline</span>
              </div>
              <h2 className="max-w-2xl text-4xl font-semibold leading-tight tracking-normal sm:text-5xl">
                内部 LLM Wiki 知识库系统
              </h2>
            </div>

            <div className="mt-12 grid grid-cols-2 gap-px bg-[#d8d2c6] md:grid-cols-4">
              {lanes.map((lane) => (
                <div key={lane.label} className="bg-[#fffdf7] p-4">
                  <lane.icon className="mb-6 text-[#52625a]" size={20} strokeWidth={1.7} />
                  <div className="text-3xl font-semibold tabular-nums">{lane.value}</div>
                  <div className="mt-1 text-sm text-[#66706a]">{lane.label}</div>
                </div>
              ))}
            </div>
          </div>

          <aside className="grid content-start gap-3">
            {[
              ["API", "/api/v1", "统一接口前缀已固定"],
              ["Database", "Alembic", "PostgreSQL 扩展迁移入口"],
              ["Worker", "ARQ", "长任务队列入口"],
              ["Quality", "lint/test", "前后端质量命令"],
            ].map(([title, meta, copy]) => (
              <div key={title} className="border border-[#d8d2c6] bg-[#ffffff] p-4">
                <div className="mb-5 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold uppercase tracking-normal">{title}</h3>
                  <span className="text-xs text-[#66706a]">{meta}</span>
                </div>
                <p className="text-sm leading-6 text-[#3f4a46]">{copy}</p>
              </div>
            ))}
          </aside>
        </section>
      </div>
    </main>
  );
}

export default App;

