/**
 * Shared Vite SSR test harness for Node scripts under web/scripts/.
 * Resolves the package root relative to this file so tests work in CI,
 * local checkouts, and Grok sandboxes (no hardcoded /workspace).
 */
import { createServer } from "vite";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

/** @returns {Promise<import('vite').ViteDevServer>} */
export async function createViteTestServer() {
  return createServer({
    server: { middlewareMode: true },
    appType: "custom",
    root: webRoot,
    // Keep cache inside the package (writable in CI and local).
    cacheDir: join(webRoot, "node_modules/.vite-test"),
  });
}
