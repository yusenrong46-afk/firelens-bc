/** Local browser rehearsals must never target a provider-backed remote app. */
export function localBrowserOrigin(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
    || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("FIRELENS_E2E_BASE_URL must be a plain HTTP loopback origin without credentials, query or fragment");
  }
  return url.origin;
}
