import { create } from "zustand";

import type { AuthResponse, User, Workspace, WorkspaceMember } from "../api/m1";

type AuthState = {
  user: User | null;
  workspace: Workspace | null;
  membership: WorkspaceMember | null;
  setAuth: (auth: AuthResponse) => void;
  setWorkspace: (workspace: Workspace) => void;
  logout: () => void;
};

function readJson<T>(key: string): T | null {
  const value = localStorage.getItem(key);
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: readJson<User>("openwiki.user"),
  workspace: readJson<Workspace>("openwiki.workspace"),
  membership: readJson<WorkspaceMember>("openwiki.membership"),
  setAuth: (auth) => {
    localStorage.setItem("openwiki.access_token", auth.tokens.access_token);
    localStorage.setItem("openwiki.refresh_token", auth.tokens.refresh_token);
    localStorage.setItem("openwiki.user", JSON.stringify(auth.user));
    if (auth.workspace) {
      localStorage.setItem("openwiki.workspace", JSON.stringify(auth.workspace));
    }
    if (auth.membership) {
      localStorage.setItem("openwiki.membership", JSON.stringify(auth.membership));
    }
    set({
      user: auth.user,
      workspace: auth.workspace ?? null,
      membership: auth.membership ?? null,
    });
  },
  setWorkspace: (workspace) => {
    localStorage.setItem("openwiki.workspace", JSON.stringify(workspace));
    set({ workspace });
  },
  logout: () => {
    [
      "openwiki.access_token",
      "openwiki.refresh_token",
      "openwiki.user",
      "openwiki.workspace",
      "openwiki.membership",
    ].forEach((key) => localStorage.removeItem(key));
    set({ user: null, workspace: null, membership: null });
  },
}));
