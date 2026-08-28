import { create } from "zustand";

import type { AuthResponse, User, Workspace, WorkspaceMember } from "../api/m1";
import { authStorageKeys, clearStoredAuth, getStoredAccessToken } from "./authStorage";

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

function readInitialAuth() {
  const user = readJson<User>(authStorageKeys.user);
  const accessToken = getStoredAccessToken();
  if (!user || !accessToken) {
    clearStoredAuth();
    return { user: null, workspace: null, membership: null };
  }
  return {
    user,
    workspace: readJson<Workspace>(authStorageKeys.workspace),
    membership: readJson<WorkspaceMember>(authStorageKeys.membership),
  };
}

const initialAuth = readInitialAuth();

export const useAuthStore = create<AuthState>((set) => ({
  user: initialAuth.user,
  workspace: initialAuth.workspace,
  membership: initialAuth.membership,
  setAuth: (auth) => {
    localStorage.setItem(authStorageKeys.accessToken, auth.tokens.access_token);
    localStorage.setItem(authStorageKeys.refreshToken, auth.tokens.refresh_token);
    localStorage.setItem(authStorageKeys.user, JSON.stringify(auth.user));
    if (auth.workspace) {
      localStorage.setItem(authStorageKeys.workspace, JSON.stringify(auth.workspace));
    } else {
      localStorage.removeItem(authStorageKeys.workspace);
    }
    if (auth.membership) {
      localStorage.setItem(authStorageKeys.membership, JSON.stringify(auth.membership));
    } else {
      localStorage.removeItem(authStorageKeys.membership);
    }
    set({
      user: auth.user,
      workspace: auth.workspace ?? null,
      membership: auth.membership ?? null,
    });
  },
  setWorkspace: (workspace) => {
    localStorage.setItem(authStorageKeys.workspace, JSON.stringify(workspace));
    set({ workspace });
  },
  logout: () => {
    clearStoredAuth();
    set({ user: null, workspace: null, membership: null });
  },
}));

window.addEventListener("openwiki.auth.invalid", () => {
  useAuthStore.getState().logout();
});
