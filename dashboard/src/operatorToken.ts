// Operator token for write calls (X-Operator-Token). Stored in localStorage,
// which can be missing or throw (private mode, blocked storage): never crash.
const KEY = "operatorToken";

export function getOperatorToken(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setOperatorToken(token: string): void {
  try {
    if (token) window.localStorage.setItem(KEY, token);
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable: the token lasts only until the page reloads.
  }
}
