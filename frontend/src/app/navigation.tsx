import type { Key } from "react";
import {
  BookOpen,
  Database,
  FileText,
  MessageSquare,
  Network,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "../api/m1";

export type RouteKey = "kbs" | "wiki" | "graph" | "chat" | "members" | "settings" | "audit";

export const roleLabel: Record<Role, string> = {
  admin: "管理员",
  editor: "编辑者",
  viewer: "查看者",
};

export const navSections: Array<{
  title: string;
  items: Array<{ key: RouteKey; label: string; icon: LucideIcon; adminOnly?: boolean }>;
}> = [
  {
    title: "知识管理",
    items: [
      { key: "kbs", label: "知识库", icon: Database },
      { key: "wiki", label: "Wiki 浏览器", icon: BookOpen },
      { key: "graph", label: "知识图谱", icon: Network },
    ],
  },
  {
    title: "智能问答",
    items: [
      { key: "chat", label: "问答对话", icon: MessageSquare },
    ],
  },
  {
    title: "系统管理",
    items: [
      { key: "members", label: "团队成员", icon: Users, adminOnly: true },
      { key: "settings", label: "模型设置", icon: Settings, adminOnly: true },
      { key: "audit", label: "审计日志", icon: FileText, adminOnly: true },
    ],
  },
];

export const demoAccounts: Array<{ username: string; password: string; label: string }> = [
  { username: "admin", password: "password123", label: "管理员 admin" },
  { username: "editor", password: "password123", label: "编辑者 editor" },
  { username: "viewer", password: "password123", label: "查看者 viewer" },
];

export function firstKey(keys: "all" | Iterable<Key>, fallback: string) {
  if (keys === "all") return fallback;
  return String(Array.from(keys)[0] ?? fallback);
}

export function sectionTitle(route: RouteKey) {
  return navSections.flatMap((section) => section.items).find((item) => item.key === route)?.label ?? "OpenWiki";
}
