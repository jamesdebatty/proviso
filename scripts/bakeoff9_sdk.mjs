#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import {
  lstat,
  mkdir,
  readFile,
  readlink,
  readdir,
  realpath,
  rename,
  rm,
  unlink,
  writeFile,
} from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import process from "node:process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

export const SDK_VERSION = "0.3.233";
export const FRAGMENT_SCHEMA = "bakeoff9-sdk-fragment/1";
export const RESULT_SCHEMA = "bakeoff9-sdk-result/1";
export const TOOL_SURFACE = Object.freeze(["Bash", "Read", "Edit", "Write", "Grep", "Glob"]);
export const SETTING_SOURCES = Object.freeze(["project"]);
export const DECLARED_SETTINGS = Object.freeze({ autoMemoryEnabled: false });
export const PERMISSION_MODE = "bypassPermissions";

const ENV_ALLOWLIST = Object.freeze([
  "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
  "TZ", "TMPDIR", "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
]);
const LIVE_AUTH_ENV = "CLAUDE_CODE_OAUTH_TOKEN";
const DEFAULT_BASE_URLS = new Set(["", "https://api.anthropic.com", "https://api.anthropic.com/"]);
const LOOPBACK = /^(?:https?:\/\/)(?:127\.0\.0\.1|localhost|\[?::1\]?)(?::\d+)?\/?$/i;
const AUTH_NAME = /(TOKEN|SECRET|CREDENTIAL|PASSWORD|SESSION_ID|OAUTH|API_KEY|APIKEY|AUTHORIZATION)/i;
const REMINDER = /<system-reminder>[\s\S]*?<\/system-reminder>/gi;
const SECRET_PATTERNS = [
  /sk-ant-[A-Za-z0-9_-]+/gi,
  /\b(?:Bearer|Basic)\s+[A-Za-z0-9._/+=-]+/gi,
  /\bgh[pousr]_[A-Za-z0-9]{16,}\b/g,
  /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/g,
];
const ASSIGNMENT_SECRET = /\b([a-z][a-z0-9]*(?:[_-][a-z0-9]+)*[_-](?:token|key|secret|password)|api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|authorization|x-api-key|client[_-]?secret)\b\s*[:=]\s*\S+/gi;
const FLAG_SECRET = /(^|\s)(--?(?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|authorization|x-api-key|client[_-]?secret))(?:=|\s+)\S+/gi;
const FORBIDDEN_PROVIDER_ENV = /(?:ANTHROPIC_API_KEY|CLAUDE_API_KEY|ANTHROPIC_BASE_URL|BEDROCK|VERTEX|FOUNDRY|GOOGLE_APPLICATION_CREDENTIALS|GOOGLE_CLOUD_PROJECT|AWS_ACCESS|AWS_SECRET|AWS_SESSION|AWS_PROFILE|CLAUDE_CODE_USE_)/i;
const TREE_STABLE_PARALLEL_TOOLS = new Set(["Bash", "Read", "Grep", "Glob"]);
const SANDBOX_EXEC = "/usr/bin/sandbox-exec";
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sanitizeText(value) {
  let text = String(value ?? "");
  text = text.replace(REMINDER, "<withheld:system-reminder>");
  for (const pattern of SECRET_PATTERNS) text = text.replace(pattern, "<redacted>");
  text = text.replace(ASSIGNMENT_SECRET, "$1=<redacted>");
  text = text.replace(FLAG_SECRET, "$1$2 <redacted>");
  return text;
}

export function declaredConfiguration() {
  return {
    sdk_version: SDK_VERSION,
    generator: "claude-agent-sdk-query",
    streaming_query: true,
    tool_surface_option: "tools",
    tool_surface: [...TOOL_SURFACE],
    setting_sources: [...SETTING_SOURCES],
    settings: { ...DECLARED_SETTINGS },
    system_prompt: "preset-or-per-fixture-string",
    can_use_tool: false,
    permission_mode: PERMISSION_MODE,
    dangerous_skip_permissions: true,
    thinking_override: false,
    hooks: ["PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionDenied", "PostToolBatch"],
    containment: {
      pre_tool_path_guard: true,
      bash_wrapper: "macos-sandbox-exec",
      native_sdk_sandbox: false,
      network: "deny",
      writes: "workspace-and-private-temp-only",
    },
  };
}

export function permissionOptions() {
  return {
    permissionMode: PERMISSION_MODE,
    allowDangerouslySkipPermissions: true,
  };
}

function schemeString(value) {
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function sandboxProfile(workspace, privateTemp) {
  const deniedReads = [
    "/Users", "/Volumes", "/Applications", "/private/tmp", "/tmp",
    "/private/var", "/var", "/opt",
  ].map((path) => `(subpath ${schemeString(path)})`).join(" ");
  const allowedReads = [
    "/private/var/db", "/private/var/select", "/opt/homebrew", workspace, privateTemp,
  ].map((path) => `(subpath ${schemeString(path)})`).join(" ");
  return [
    "(version 1)", "(deny default)", "(allow process*)", "(allow signal)",
    "(allow sysctl-read)", "(allow mach-lookup)", "(allow ipc-posix-shm)",
    "(allow file-read-metadata)", "(allow file-read*)",
    `(deny file-read* ${deniedReads})`, `(allow file-read* ${allowedReads})`,
    `(allow file-write* (subpath ${schemeString(workspace)}) (subpath ${schemeString(privateTemp)}))`,
    "(deny network*)", "",
  ].join("\n");
}

export async function createSandboxRuntime(workspace, privateTemp) {
  if (!existsSync(SANDBOX_EXEC)) throw new Error(`${SANDBOX_EXEC} is unavailable`);
  const root = await realpath(resolve(workspace));
  const temp = await realpath(resolve(privateTemp));
  if (inside(root, temp)) throw new Error("private sandbox temp must be outside the workspace");
  if (inside(REPO_ROOT, temp)) throw new Error("private sandbox temp must be outside the repository");
  const unique = sha256(`${process.pid}:${Date.now()}:${Math.random()}`).slice(0, 20);
  const profile = resolve(temp, `bakeoff9-${unique}.sb`);
  await writeFile(profile, sandboxProfile(root, temp), { mode: 0o600, flag: "wx" });
  if (!existsSync(profile)) throw new Error("sandbox profile was not created");
  return { executable: SANDBOX_EXEC, profile, workspace: root, private_temp: temp };
}

export function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'"'"'`)}'`;
}

export function wrapBashCommand(command, runtime) {
  if (!runtime?.profile || !runtime?.private_temp || !existsSync(runtime.profile)) {
    throw new Error("Bash sandbox profile is unavailable");
  }
  return [
    "/usr/bin/env", `TMPDIR=${shellQuote(runtime.private_temp + sep)}`,
    runtime.executable, "-f", shellQuote(runtime.profile),
    "/bin/bash", "--noprofile", "--norc", "-c", shellQuote(command),
  ].join(" ");
}

export function bashHookOutput(toolInput, runtime) {
  return {
    continue: true,
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      updatedInput: { ...toolInput, command: wrapBashCommand(toolInput.command, runtime) },
    },
  };
}

export function isLoopback(baseUrl) {
  return LOOPBACK.test(String(baseUrl ?? ""));
}

export function assertAuthBoundary(mode, env = process.env, baseUrl = env.ANTHROPIC_BASE_URL ?? "") {
  const hasApiKey = Object.entries(env).some(([name, value]) =>
    Boolean(value) && /(?:^|_)ANTHROPIC_API_KEY$|^CLAUDE_API_KEY$/i.test(name));
  if (mode === "live") {
    if (hasApiKey) throw new Error("live mode refuses API-key authentication; subscription auth only");
    if (!DEFAULT_BASE_URLS.has(String(baseUrl))) {
      throw new Error("live mode refuses a non-default ANTHROPIC_BASE_URL");
    }
    for (const [name, value] of Object.entries(env)) {
      if (!value || name === LIVE_AUTH_ENV || name === "ANTHROPIC_MODEL" || name === "ANTHROPIC_DEFAULT_OPUS_MODEL") continue;
      if (FORBIDDEN_PROVIDER_ENV.test(name)) {
        throw new Error(`live mode refuses alternate-provider or credential environment: ${name}`);
      }
    }
    return;
  }
  if (mode === "preflight") {
    if (!isLoopback(baseUrl)) throw new Error("preflight requires a loopback ANTHROPIC_BASE_URL");
    return;
  }
  if (mode !== "fake") throw new Error(`unknown mode: ${mode}`);
}

export function buildChildEnv(mode, parent, baseUrl, preflightHome = null, rawBodyDir = null, sandboxTempDir = null) {
  assertAuthBoundary(mode, parent, baseUrl);
  const child = {};
  for (const name of ENV_ALLOWLIST) if (parent[name] != null) child[name] = parent[name];
  if (mode === "live" && parent[LIVE_AUTH_ENV]) child[LIVE_AUTH_ENV] = parent[LIVE_AUTH_ENV];
  child.DISABLE_TELEMETRY = "1";
  child.DISABLE_ERROR_REPORTING = "1";
  child.DISABLE_AUTOUPDATER = "1";
  child.DISABLE_NON_ESSENTIAL_MODEL_CALLS = "1";
  child.CLAUDE_AGENT_SDK_CLIENT_APP = "clause-bakeoff/9";
  if (mode !== "fake") {
    if (!sandboxTempDir || !isAbsolute(sandboxTempDir)) {
      throw new Error("child process requires an absolute sandbox temp directory");
    }
    child.TMPDIR = sandboxTempDir.endsWith(sep) ? sandboxTempDir : sandboxTempDir + sep;
  }
  if (mode === "preflight") {
    if (!preflightHome || !isAbsolute(preflightHome)) throw new Error("preflight requires an isolated absolute HOME");
    child.HOME = preflightHome;
    child.ANTHROPIC_BASE_URL = baseUrl;
    child.ANTHROPIC_API_KEY = "sk-ant-dummy-capture-not-a-real-key";
  }
  if (mode === "live") {
    if (!rawBodyDir || !isAbsolute(rawBodyDir)) throw new Error("live mode requires an absolute raw body directory");
    child.CLAUDE_CODE_ENABLE_TELEMETRY = "1";
    child.OTEL_LOGS_EXPORTER = "console";
    child.OTEL_METRICS_EXPORTER = "";
    child.OTEL_LOG_RAW_API_BODIES = `file:${rawBodyDir}`;
  }
  for (const [name, value] of Object.entries(child)) {
    if (AUTH_NAME.test(name) && name !== "ANTHROPIC_API_KEY" && name !== LIVE_AUTH_ENV && value) {
      throw new Error(`auth-shaped environment variable reached child: ${name}`);
    }
  }
  return child;
}

async function containedPath(workspace, candidate) {
  const root = await realpath(resolve(workspace));
  const lexical = isAbsolute(candidate) ? resolve(candidate) : resolve(root, candidate);
  if (!inside(root, lexical)) return false;
  let probe = lexical;
  while (!existsSync(probe)) {
    const parent = dirname(probe);
    if (parent === probe) return false;
    probe = parent;
  }
  const physical = await realpath(probe);
  return inside(root, physical);
}

export async function toolContainmentProblems(input, workspace) {
  const name = String(input?.tool_name ?? "");
  const value = input?.tool_input && typeof input.tool_input === "object" ? input.tool_input : {};
  const problems = [];
  if (name === "Bash") {
    const command = typeof value.command === "string" ? value.command : "";
    if (!command) problems.push("Bash command is missing");
    return problems;
  }
  const key = name === "Read" || name === "Edit" || name === "Write" ? "file_path"
    : name === "Grep" || name === "Glob" ? "path" : null;
  if (!key) return problems;
  const candidate = value[key];
  if (candidate == null && (name === "Grep" || name === "Glob")) return problems;
  if (typeof candidate !== "string" || !candidate) return [`${name} ${key} is missing`];
  if (!await containedPath(workspace, candidate)) problems.push(`${name} path escapes the workspace`);
  return problems;
}

export async function preToolDecision(input, workspace) {
  const problems = await toolContainmentProblems(input, workspace);
  if (!problems.length) return { allowed: true, output: { continue: true } };
  return {
    allowed: false,
    problems,
    output: {
      continue: true,
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: "tool target is outside the isolated trial workspace",
      },
    },
  };
}

function nonnegativeInteger(value) {
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

function responseText(response) {
  if (typeof response === "string") return response;
  if (!response || typeof response !== "object") return "";
  const pieces = [];
  if (typeof response.stdout === "string") pieces.push(response.stdout);
  if (typeof response.stderr === "string") pieces.push(response.stderr);
  if (typeof response.error === "string") pieces.push(response.error);
  if (typeof response.content === "string") pieces.push(response.content);
  if (Array.isArray(response.content)) {
    for (const block of response.content) {
      if (block && typeof block === "object" && typeof block.text === "string") pieces.push(block.text);
    }
  }
  return pieces.join("\n");
}

export function parseTestCounts(output) {
  const text = String(output ?? "");
  const values = { failed: 0, skipped: 0, expected_failures: 0 };
  const sum = (regex) => [...text.matchAll(regex)].reduce((total, match) => total + Number(match[1]), 0);
  values.skipped = Math.max(
    sum(/(?:^|[,(\s])(\d+)\s+skipped\b/gim),
    sum(/\bskipped\s*=\s*(\d+)/gim),
  );
  values.expected_failures = Math.max(
    sum(/(?:^|[,(\s])(\d+)\s+xfailed\b/gim),
    sum(/\bexpected failures?\s*=\s*(\d+)/gim),
    sum(/\bexpected_failures?\s*=\s*(\d+)/gim),
  );
  values.failed = Math.max(
    sum(/(?:^|[,(\s])(\d+)\s+failed\b/gim),
    sum(/\bfailures?\s*=\s*(\d+)/gim) + sum(/\berrors?\s*=\s*(\d+)/gim),
  );
  return values;
}

export function parseBashResult(response, { failure = false } = {}) {
  const text = responseText(response);
  const explicit = response && typeof response === "object"
    ? nonnegativeInteger(response.exit_code ?? response.exitCode ?? response.code)
    : undefined;
  const exitMatch = text.match(/(?:^|\b)(?:Error:\s*)?Exit code\s+(-?\d+)\b/i)
    ?? text.match(/<bash_metadata>[\s\S]*?<exit_code>(-?\d+)<\/exit_code>/i);
  let exitCode = explicit ?? (exitMatch ? Number(exitMatch[1]) : undefined);
  if (exitCode == null && !failure && response && typeof response === "object") {
    const backgrounded = response.backgroundTaskId || response.backgroundedByUser || response.timedOutAfterMs;
    if (response.interrupted === false && !backgrounded) exitCode = 0;
  }
  const counts = parseTestCounts(text);
  return {
    exit_code: Number.isInteger(exitCode) ? exitCode : null,
    ...counts,
    output_chars: text.length,
    ambiguous: !Number.isInteger(exitCode),
  };
}

function inside(parent, candidate) {
  const rel = relative(parent, candidate);
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== "..");
}

async function walk(root, current, output) {
  const entries = await readdir(current, { withFileTypes: true });
  entries.sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    if (entry.name === ".git") continue;
    const absolute = resolve(current, entry.name);
    const rel = relative(root, absolute).split(sep).join("/");
    const stat = await lstat(absolute);
    if (stat.isDirectory()) {
      await walk(root, absolute, output);
    } else if (stat.isSymbolicLink()) {
      output[rel] = sha256(`symlink:${await readlink(absolute)}`);
    } else if (stat.isFile()) {
      output[rel] = sha256(await readFile(absolute));
    }
  }
}

export async function snapshotWorkspace(workspace) {
  const root = resolve(workspace);
  const files = {};
  await walk(root, root, files);
  return { tree_sha256: sha256(canonical(files)), files };
}

export function diffSnapshots(before, after) {
  const changed = [];
  const paths = new Set([...Object.keys(before.files), ...Object.keys(after.files)]);
  for (const path of [...paths].sort()) {
    if (before.files[path] === after.files[path]) continue;
    changed.push({
      path: sanitizeText(path),
      change: before.files[path] == null ? "created" : after.files[path] == null ? "deleted" : "modified",
      before_sha256: before.files[path] ?? null,
      after_sha256: after.files[path] ?? null,
    });
  }
  return changed;
}

async function atomicJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temp = `${path}.tmp-${process.pid}-${createHash("sha256").update(String(Math.random())).digest("hex").slice(0, 12)}`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, { flag: "wx", mode: 0o600 });
  await rename(temp, path);
}

export class BoundaryRecorder {
  constructor({ workspace, fragmentDir, notify = null }) {
    this.workspace = resolve(workspace);
    this.fragmentDir = resolve(fragmentDir);
    if (inside(this.workspace, this.fragmentDir)) {
      throw new Error("trajectory fragment directory must be outside the trial workspace");
    }
    this.sequence = 0;
    this.pending = new Map();
    this.ambiguous = [];
    this.queue = Promise.resolve();
    this.notify = notify;
    this.executedToolCount = 0;
    this.deniedToolCount = 0;
  }

  async write(phase, id, body) {
    const sequence = this.sequence++;
    const fragment = { schema: FRAGMENT_SCHEMA, sequence, phase, ...body };
    const problems = durableProblems(fragment);
    if (problems.length) throw new Error(`unsafe fragment: ${problems.join("; ")}`);
    const suffix = sha256(String(id ?? phase)).slice(0, 12);
    const path = resolve(this.fragmentDir, `${String(sequence).padStart(6, "0")}-${phase}-${suffix}.json`);
    await atomicJson(path, fragment);
    if (this.notify) await this.notify(fragment);
    return fragment;
  }

  serialize(task) {
    const run = this.queue.then(task, task);
    this.queue = run.catch(() => {});
    return run;
  }

  pre(input) {
    return this.serialize(async () => {
      const id = String(input.tool_use_id ?? "");
      const before = await snapshotWorkspace(this.workspace);
      const duplicate = this.pending.has(id);
      const name = String(input.tool_name ?? "");
      const mixedParallel = this.pending.size > 0 && (
        !TREE_STABLE_PARALLEL_TOOLS.has(name)
        || [...this.pending.values()].some(
          (value) => !TREE_STABLE_PARALLEL_TOOLS.has(value.name)
        )
      );
      const changedDuringOverlap = [...this.pending.values()].some(
        (value) => diffSnapshots(value.before, before).length > 0
      );
      if (!id || duplicate) this.ambiguous.push("missing or duplicate tool boundary");
      if (mixedParallel) this.ambiguous.push("mixed parallel tool boundary");
      if (changedDuringOverlap) this.ambiguous.push("workspace changed during parallel boundary");
      const ambiguous = !id || duplicate || mixedParallel || changedDuringOverlap;
      const command = input.tool_name === "Bash" && input.tool_input && typeof input.tool_input.command === "string"
        ? sanitizeText(input.tool_input.command) : null;
      const cwd = relative(this.workspace, resolve(input.cwd || this.workspace)).split(sep).join("/") || ".";
      this.pending.set(id, { before, command, cwd, name });
      return this.write("start", id, {
        tool: sanitizeText(input.tool_name ?? ""),
        tool_use_sha256: sha256(id),
        command,
        cwd: sanitizeText(cwd),
        tree_sha256: before.tree_sha256,
        ambiguous,
      });
    });
  }

  post(input, failure = false) {
    return this.serialize(async () => {
      const id = String(input.tool_use_id ?? "");
      const pending = this.pending.get(id);
      const after = await snapshotWorkspace(this.workspace);
      const parsed = input.tool_name === "Bash"
        ? parseBashResult(failure ? input.error : input.tool_response, { failure }) : null;
      const edits = pending ? diffSnapshots(pending.before, after) : [];
      const concurrentMutation = this.pending.size > 1 && edits.length > 0;
      const ambiguous = !pending || Boolean(parsed?.ambiguous) || concurrentMutation;
      if (!pending) this.ambiguous.push("unpaired tool boundary");
      if (parsed?.ambiguous) this.ambiguous.push("unknown Bash exit status");
      if (concurrentMutation) this.ambiguous.push("parallel command changed the workspace");
      this.pending.delete(id);
      this.executedToolCount += 1;
      return this.write(failure ? "failure" : "finish", id, {
        tool: sanitizeText(input.tool_name ?? pending?.name ?? ""),
        tool_use_sha256: sha256(id),
        command: pending?.command ?? null,
        cwd: sanitizeText(pending?.cwd ?? "."),
        tree_before_sha256: pending?.before.tree_sha256 ?? null,
        tree_after_sha256: after.tree_sha256,
        edits,
        bash: parsed,
        duration_ms: nonnegativeInteger(input.duration_ms) ?? null,
        ambiguous,
      });
    });
  }

  denied(input) {
    return this.serialize(async () => {
      const id = String(input.tool_use_id ?? "");
      const pending = this.pending.get(id);
      if (!pending) return null;
      const after = await snapshotWorkspace(this.workspace);
      return this.closeDenied(id, pending, after, input.tool_name);
    });
  }

  async closeDenied(id, pending, after, toolName = null) {
    const edits = diffSnapshots(pending.before, after);
    const ambiguous = edits.length > 0;
    if (ambiguous) this.ambiguous.push("denied tool changed the workspace");
    this.pending.delete(id);
    this.deniedToolCount += 1;
    return this.write("denied", id, {
      tool: sanitizeText(toolName ?? pending.name ?? ""),
      tool_use_sha256: sha256(id),
      command: pending.command,
      cwd: sanitizeText(pending.cwd),
      tree_before_sha256: pending.before.tree_sha256,
      tree_after_sha256: after.tree_sha256,
      edits,
      ambiguous,
    });
  }

  batch(input) {
    return this.serialize(async () => {
      const snapshot = await snapshotWorkspace(this.workspace);
      const unresolved = [...this.pending.entries()];
      for (const [id, pending] of unresolved) {
        await this.closeDenied(id, pending, snapshot);
      }
      return this.write("batch", "batch", {
        tool_count: Array.isArray(input.tool_calls) ? input.tool_calls.length : null,
        pending_count: this.pending.size,
        denied_count: unresolved.length,
        tree_sha256: snapshot.tree_sha256,
        ambiguous: false,
      });
    });
  }

  async settled() {
    await this.queue;
    if (this.pending.size) this.ambiguous.push("unfinished tool boundary");
    return {
      fragment_count: this.sequence,
      ambiguous: [...new Set(this.ambiguous)],
      executed_tool_count: this.executedToolCount,
      denied_tool_count: this.deniedToolCount,
    };
  }
}

export function durableProblems(value, path = "") {
  const problems = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => problems.push(...durableProblems(item, `${path}[${index}]`)));
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (AUTH_NAME.test(key) && typeof item === "string" && item) problems.push(`${path}/${key}: auth-shaped value`);
      problems.push(...durableProblems(item, `${path}/${key}`));
    }
  } else if (typeof value === "string") {
    if (/<system-reminder>/i.test(value)) problems.push(`${path}: reminder payload`);
    if (sanitizeText(value) !== value) problems.push(`${path}: credential-shaped text`);
  }
  return problems;
}

export function validateRequest(request) {
  if (!request || typeof request !== "object" || Array.isArray(request)) throw new Error("request must be an object");
  const mode = request.mode;
  if (!new Set(["live", "preflight", "fake"]).has(mode)) throw new Error("mode must be live, preflight, or fake");
  for (const name of ["workspace", "fragment_dir"]) {
    if (typeof request[name] !== "string" || !isAbsolute(request[name])) throw new Error(`${name} must be an absolute path`);
  }
  if (typeof request.prompt !== "string" || !request.prompt.trim()) throw new Error("prompt must be a non-empty string");
  if (mode !== "fake") {
    if (typeof request.claude_executable !== "string" || !isAbsolute(request.claude_executable)) {
      throw new Error("claude_executable must be an absolute path");
    }
    if (!existsSync(request.claude_executable)) throw new Error("claude_executable does not exist");
  }
  if (mode === "preflight" && (!request.preflight_home || !isAbsolute(request.preflight_home))) {
    throw new Error("preflight_home must be an isolated absolute path");
  }
  if (mode !== "fake" && (!request.sandbox_temp_dir || !isAbsolute(request.sandbox_temp_dir))) {
    throw new Error("sandbox_temp_dir must be an outside-workspace absolute path");
  }
  if (mode !== "fake") {
    const temp = resolve(request.sandbox_temp_dir);
    if (inside(resolve(request.workspace), temp) || inside(REPO_ROOT, temp)) {
      throw new Error("sandbox_temp_dir must be outside the workspace and repository");
    }
  }
  if (mode === "live" && (!request.raw_body_dir || !isAbsolute(request.raw_body_dir))) {
    throw new Error("raw_body_dir must be an outside-repository absolute path");
  }
  if (!new Set(["intact", "ablated"]).has(request.harness_prompt)) {
    throw new Error("harness_prompt must be intact or ablated");
  }
  if (request.harness_prompt === "ablated" && (!request.system_prompt_file || !isAbsolute(request.system_prompt_file))) {
    throw new Error("ablated mode requires an absolute per-fixture system_prompt_file");
  }
  return request;
}

function hooks(recorder, sandboxRuntime) {
  return {
    PreToolUse: [{ hooks: [async (input) => {
      if (input.tool_name === "Bash") {
        const problems = await toolContainmentProblems(input, recorder.workspace);
        if (problems.length) throw new Error(problems.join("; "));
        await recorder.pre(input);
        return bashHookOutput(input.tool_input, sandboxRuntime);
      }
      const decision = await preToolDecision(input, recorder.workspace);
      if (!decision.allowed) return decision.output;
      await recorder.pre(input);
      return decision.output;
    }] }],
    PostToolUse: [{ hooks: [async (input) => { await recorder.post(input); return { continue: true }; }] }],
    PostToolUseFailure: [{ hooks: [async (input) => { await recorder.post(input, true); return { continue: true }; }] }],
    PermissionDenied: [{ hooks: [async (input) => {
      await recorder.denied(input);
      return { continue: true, hookSpecificOutput: { hookEventName: "PermissionDenied" } };
    }] }],
    PostToolBatch: [{ hooks: [async (input) => { await recorder.batch(input); return { continue: true }; }] }],
  };
}

function normalizeUsage(result) {
  const usage = result?.usage ?? {};
  const details = usage.output_tokens_details ?? {};
  const normalized = {
    input_tokens: nonnegativeInteger(usage.input_tokens) ?? 0,
    output_tokens: nonnegativeInteger(usage.output_tokens) ?? 0,
    cache_creation_input_tokens: nonnegativeInteger(usage.cache_creation_input_tokens) ?? 0,
    cache_read_input_tokens: nonnegativeInteger(usage.cache_read_input_tokens) ?? 0,
  };
  const thinking = nonnegativeInteger(details.thinking_tokens ?? usage.thinking_tokens);
  if (thinking != null) normalized.thinking_tokens = thinking;
  return normalized;
}

export async function reconcilePermissionDeniedMessage(recorder, message) {
  if (message?.type === "system" && message?.subtype === "permission_denied") {
    await recorder.denied(message);
    return true;
  }
  return false;
}

async function runFake(request, recorder, notify) {
  const fixture = JSON.parse(await readFile(request.fake_fixture, "utf8"));
  for (const message of fixture.sdk_messages ?? []) await notify?.sdkMessage?.(message);
  for (const raw of fixture.request_bodies ?? []) await notify?.rawRequest?.(raw);
  for (const event of fixture.events ?? []) {
    if (event.phase === "pre") await recorder.pre(event);
    else if (event.phase === "post") await recorder.post(event);
    else if (event.phase === "failure") await recorder.post(event, true);
    else if (event.phase === "batch") await recorder.batch(event);
    else if (event.phase === "mutate") {
      const destination = resolve(request.workspace, event.path);
      if (!inside(resolve(request.workspace), destination)) throw new Error("fake mutation escapes workspace");
      await mkdir(dirname(destination), { recursive: true });
      await writeFile(destination, String(event.content ?? ""));
    } else throw new Error(`unknown fake event phase: ${event.phase}`);
  }
  return { subtype: "success", result: String(fixture.response ?? ""), usage: fixture.usage ?? {} };
}

async function runSdk(request, recorder, notify, sandboxRuntime) {
  assertAuthBoundary(request.mode, process.env, request.base_url ?? process.env.ANTHROPIC_BASE_URL ?? "");
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  const systemPrompt = request.harness_prompt === "intact"
    ? { type: "preset", preset: "claude_code" }
    : await readFile(request.system_prompt_file, "utf8");
  const abortController = new AbortController();
  const timeout = request.mode === "preflight"
    ? setTimeout(() => abortController.abort(), request.preflight_timeout_ms ?? 15_000)
    : null;
  const options = {
    abortController,
    cwd: request.workspace,
    model: request.model,
    pathToClaudeCodeExecutable: request.claude_executable,
    systemPrompt,
    tools: [...TOOL_SURFACE],
    settingSources: [...SETTING_SOURCES],
    settings: { ...DECLARED_SETTINGS },
    ...permissionOptions(),
    includePartialMessages: false,
    ...(request.observe_hooks === false ? {} : { hooks: hooks(recorder, sandboxRuntime) }),
    env: buildChildEnv(
      request.mode,
      process.env,
      request.base_url ?? process.env.ANTHROPIC_BASE_URL ?? "",
      request.preflight_home ?? null,
      request.raw_body_dir ?? null,
      request.sandbox_temp_dir ?? null,
    ),
  };
  let result = null;
  try {
    for await (const message of query({ prompt: request.prompt, options })) {
      await reconcilePermissionDeniedMessage(recorder, message);
      if ((message.type === "assistant") || (message.type === "system" && message.subtype === "init")) {
        await notify?.sdkMessage?.(message);
      }
      if (message.type === "result") result = message;
    }
  } catch (error) {
    if (request.mode !== "preflight") throw error;
    result = { subtype: "transport-error", usage: {}, errors: [sanitizeText(error?.message ?? error)] };
  } finally {
    if (timeout) clearTimeout(timeout);
  }
  for (const denial of result?.permission_denials ?? []) await recorder.denied(denial);
  if (!result && request.mode === "preflight") result = { subtype: "transport-error", usage: {} };
  if (!result) throw new Error("SDK query ended without a result");
  return result;
}

export async function execute(request, notify = null) {
  validateRequest(request);
  assertAuthBoundary(request.mode, process.env, request.base_url ?? process.env.ANTHROPIC_BASE_URL ?? "");
  const recorder = new BoundaryRecorder({ workspace: request.workspace, fragmentDir: request.fragment_dir, notify });
  let sandboxRuntime = null;
  let result;
  try {
    sandboxRuntime = request.mode === "fake"
      ? null
      : await createSandboxRuntime(request.workspace, request.sandbox_temp_dir);
    result = request.mode === "fake"
      ? await runFake(request, recorder, notify)
      : await runSdk(request, recorder, notify, sandboxRuntime);
  } finally {
    if (sandboxRuntime?.profile) await unlink(sandboxRuntime.profile).catch(() => {});
    if (request.mode !== "fake" && request.sandbox_temp_dir) {
      await rm(request.sandbox_temp_dir, { recursive: true, force: true }).catch(() => {});
    }
  }
  const boundary = await recorder.settled();
  if (boundary.ambiguous.length) throw new Error(`ambiguous trajectory evidence: ${boundary.ambiguous.join("; ")}`);
  if (request.mode === "preflight") {
    return {
      schema: RESULT_SCHEMA,
      response: "",
      usage: normalizeUsage(result),
      capture: {
        surface_verdict: "ungraded",
        mode: request.mode,
        declared_configuration: declaredConfiguration(),
        fragment_count: boundary.fragment_count,
        executed_tool_count: boundary.executed_tool_count,
        denied_tool_count: boundary.denied_tool_count,
        synthetic_status: result?.subtype ?? "transport-error",
      },
    };
  }
  if (result.subtype !== "success" || result.is_error) {
    throw new Error(`SDK query failed: ${sanitizeText((result.errors ?? []).join("; ") || result.subtype)}`);
  }
  return {
    schema: RESULT_SCHEMA,
    response: String(result.result ?? ""),
    usage: normalizeUsage(result),
    capture: {
      surface_verdict: request.mode === "preflight" ? "ungraded" : request.mode === "fake" ? "fake" : request.surface_verdict,
      mode: request.mode,
      declared_configuration: declaredConfiguration(),
      fragment_count: boundary.fragment_count,
      executed_tool_count: boundary.executed_tool_count,
      denied_tool_count: boundary.denied_tool_count,
    },
  };
}

function acknowledgedTransport() {
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const waiting = [];
  lines.on("line", (line) => waiting.shift()?.(line));
  const notify = async (fragment) => {
    process.stdout.write(`${JSON.stringify({ transport: "boundary", fragment })}\n`);
    const line = await new Promise((resolveLine) => waiting.push(resolveLine));
    let acknowledgement;
    try {
      acknowledgement = JSON.parse(line);
    } catch {
      throw new Error("boundary acknowledgement was not JSON");
    }
    if (acknowledgement.ack !== fragment.sequence) {
      throw new Error(`boundary acknowledgement mismatch at sequence ${fragment.sequence}`);
    }
  };
  notify.sdkMessage = async (message) => {
    process.stdout.write(`${JSON.stringify({ transport: "sdk-message", message })}\n`);
  };
  notify.rawRequest = async (raw) => {
    process.stdout.write(`${JSON.stringify({ transport: "raw-request", raw })}\n`);
  };
  notify.close = () => lines.close();
  return notify;
}

async function main(argv) {
  if (argv.includes("--describe")) {
    process.stdout.write(`${JSON.stringify(declaredConfiguration(), null, 2)}\n`);
    return 0;
  }
  const requestIndex = argv.indexOf("--request");
  if (requestIndex < 0 || !argv[requestIndex + 1]) throw new Error("usage: bakeoff9_sdk.mjs --request REQUEST.json");
  const request = JSON.parse(await readFile(argv[requestIndex + 1], "utf8"));
  const transport = acknowledgedTransport();
  try {
    const result = await execute(request, transport);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } finally {
    transport.close();
  }
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`bakeoff9 SDK adapter refused: ${sanitizeText(error?.message ?? error)}\n`);
    process.exitCode = 1;
  });
}
