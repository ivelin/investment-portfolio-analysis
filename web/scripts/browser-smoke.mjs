#!/usr/bin/env node
/**
 * Lightweight headless load + screenshot for http://127.0.0.1:8080 (or argv URL).
 * Does not try to "play" the app — just proves the page loads and captures a PNG
 * the agent can Read. Exit 0 on success, 1 on navigation failure, 2 if console errors.
 *
 * Screenshots default under web/screenshots/ (package-relative) so they live on
 * the project volume and stay readable by agent tools.
 */
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const url = process.argv[2] || "http://127.0.0.1:8080/";
const outPng =
  process.argv[3] || join(root, "screenshots/app-builder-preview.png");
const timeoutMs = Number(process.env.BROWSER_SMOKE_TIMEOUT_MS || 45000);

mkdirSync(dirname(outPng), { recursive: true });

const consoleErrors = [];
const pageErrors = [];

const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err?.message || err)));

  const resp = await page.goto(url, {
    waitUntil: "networkidle",
    timeout: timeoutMs,
  });
  const status = resp?.status() ?? 0;
  await page.waitForTimeout(1000);
  await page.screenshot({ path: outPng, fullPage: true });
  console.log(JSON.stringify({ ok: status >= 200 && status < 400, status, outPng }));

  if (status < 200 || status >= 400) process.exit(1);
  if (pageErrors.length || consoleErrors.length) {
    console.error("pageErrors", pageErrors);
    console.error("consoleErrors", consoleErrors.slice(0, 10));
    process.exit(2);
  }
} finally {
  await browser.close();
}
