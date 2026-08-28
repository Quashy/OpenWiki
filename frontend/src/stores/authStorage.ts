export const authStorageKeys = {
  accessToken: "openwiki.access_token",
  refreshToken: "openwiki.refresh_token",
  user: "openwiki.user",
  workspace: "openwiki.workspace",
  membership: "openwiki.membership",
} as const;

export function clearStoredAuth() {
  Object.values(authStorageKeys).forEach((key) => localStorage.removeItem(key));
}

export function getStoredAccessToken() {
  return localStorage.getItem(authStorageKeys.accessToken);
}
