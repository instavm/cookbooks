#!/usr/bin/env node

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const cliPath = path.join(__dirname, "../node_modules/@anthropic-ai/claude-agent-sdk/cli.js");
const dnsPatchPath = path.join(__dirname, "claude-code-dns-patch.cjs");

const child = spawn(
  process.execPath,
  ["--require", dnsPatchPath, cliPath, ...process.argv.slice(2)],
  {
    stdio: "inherit",
    env: process.env,
  },
);

const forwardSignal = (signal) => {
  if (!child.killed) {
    child.kill(signal);
  }
};

process.on("SIGINT", () => forwardSignal("SIGINT"));
process.on("SIGTERM", () => forwardSignal("SIGTERM"));

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
