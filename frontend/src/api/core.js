import axios from "axios";

export { axios };

const ENV_BACKEND_URL = String(import.meta.env?.VITE_BACKEND_URL || "").trim();

export function stripTrailingSlash(url) {
  return String(url || "").trim().replace(/\/+$/, "");
}

export function isSupabaseProjectUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (!normalized) {
    return false;
  }

  try {
    const { hostname } = new URL(normalized);
    return String(hostname || "").toLowerCase().endsWith(".supabase.co");
  } catch {
    return false;
  }
}

export function assertBackendApiUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (!normalized) {
    throw new Error("Backend URL is empty. Please set VITE_BACKEND_URL.");
  }

  if (isSupabaseProjectUrl(normalized)) {
    throw new Error(
      "Backend URL points to Supabase, but /api/v1/extract is served by the FastAPI backend. Use http://127.0.0.1:8000 or the active trycloudflare URL.",
    );
  }

  return normalized;
}

export function backendApiV1Base() {
  return apiV1Base(ENV_BACKEND_URL);
}

export function apiV1Base(url) {
  const normalized = assertBackendApiUrl(url);
  if (/\/api\/v\d+$/i.test(normalized)) {
    return normalized;
  }
  return `${normalized}/api/v1`;
}

export function isOpenAIChatCompletionsUrl(url) {
  const normalized = stripTrailingSlash(url);
  return /\/v\d+\/chat\/completions$/i.test(normalized) || /\/open\/api\/v\d+$/i.test(normalized);
}

export function openAIChatCompletionsUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (/\/v\d+\/chat\/completions$/i.test(normalized)) {
    return normalized;
  }
  if (/\/open\/api\/v\d+$/i.test(normalized)) {
    return `${normalized}/chat/completions`;
  }
  return normalized;
}

export function openAIModelsUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (/\/v\d+\/chat\/completions$/i.test(normalized)) {
    return normalized.replace(/\/chat\/completions$/i, "/models");
  }
  if (/\/open\/api\/v\d+$/i.test(normalized)) {
    return `${normalized}/models`;
  }
  return `${normalized}/models`;
}

export function isEcnuModelBaseUrl(url) {
  return /https?:\/\/chat\.ecnu\.edu\.cn\/open\/api\/v\d+$/i.test(stripTrailingSlash(url));
}

export function proxyEcnuModelsUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (/https?:\/\/chat\.ecnu\.edu\.cn\/open\/api\/v\d+$/i.test(normalized)) {
    return `/model-proxy${new URL(normalized).pathname}/models`;
  }
  if (/https?:\/\/chat\.ecnu\.edu\.cn\/open\/api\/v\d+\/chat\/completions$/i.test(normalized)) {
    return `/model-proxy${new URL(normalized).pathname.replace(/\/chat\/completions$/i, "/models")}`;
  }
  if (/\/models$/i.test(normalized)) {
    return normalized;
  }
  return `${normalized}/models`;
}

export function proxyEcnuChatCompletionsUrl(url) {
  const normalized = stripTrailingSlash(url);
  if (/https?:\/\/chat\.ecnu\.edu\.cn\/open\/api\/v\d+$/i.test(normalized)) {
    return `/model-proxy${new URL(normalized).pathname}/chat/completions`;
  }
  if (/https?:\/\/chat\.ecnu\.edu\.cn\/open\/api\/v\d+\/chat\/completions$/i.test(normalized)) {
    return `/model-proxy${new URL(normalized).pathname}`;
  }
  if (/\/chat\/completions$/i.test(normalized)) {
    return normalized;
  }
  return normalized;
}

export function buildOpenAIHeaders(settings) {
  const headers = { "Content-Type": "application/json" };
  if (settings.api_key) {
    headers.Authorization = `Bearer ${settings.api_key}`;
  }
  return headers;
}

export function buildHeaders(settings) {
  const headers = {};
  if (settings.auth_token) {
    headers.Authorization = `Bearer ${settings.auth_token}`;
  }
  if (settings.api_key) {
    headers["X-API-Key"] = settings.api_key;
  }
  if (settings.secret_key) headers["X-API-Secret"] = settings.secret_key;
  return headers;
}

export function createAuthError(message, code) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export async function sha256(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(String(text || ""));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function createId(prefix = "id") {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}_${crypto.randomUUID().replace(/-/g, "")}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function createShortId(prefix = "id") {
  // 生成格式为 prefix_XXXX 的短 ID（8-10 个字母数字）
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    const uuid = crypto.randomUUID().replace(/-/g, "");
    return `${prefix}_${uuid.substring(0, 8)}`;
  }
  const timestamp = Date.now().toString(36).substring(2, 6);
  const random = Math.random().toString(36).substring(2, 8);
  return `${prefix}_${timestamp}${random}`;
}

export function isDisabledStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "禁用" || normalized === "disabled" || normalized === "inactive";
}

export async function resolveCurrentUserId(supabase, token) {
  const tokenValue = String(token || "").trim();
  
  if (!tokenValue) {
    throw createAuthError("登录态已失效，请重新登录", "AUTH_INVALID_TOKEN");
  }

  const { data: sessionRow, error: sessionError } = await supabase
    .from("auth_sessions")
    .select("user_id")
    .eq("access_token_jti", tokenValue)
    .maybeSingle();

  if (sessionError || !sessionRow?.user_id) {
    throw createAuthError("登录态已失效，请重新登录", "AUTH_INVALID_TOKEN");
  }

  return sessionRow.user_id;
}

export async function hashFile(file) {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function pickFirst(row, keys) {
  for (const key of keys || []) {
    const value = row?.[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return value;
    }
  }
  return "";
}

export function normalizeOptionalText(value) {
  const cleaned = String(value || "").trim();
  return cleaned || null;
}

export function formatUnknownError(error) {
  if (error instanceof Error) {
    return error.message || "未知错误";
  }

  if (typeof error === "string") {
    return error || "未知错误";
  }

  const objectLikeError = error && typeof error === "object" ? error : null;
  if (objectLikeError) {
    const message = String(objectLikeError.message || "").trim();
    const details = String(objectLikeError.details || "").trim();
    const hint = String(objectLikeError.hint || "").trim();
    const code = String(objectLikeError.code || "").trim();

    const parts = [message, details, hint, code ? `code=${code}` : ""].filter(Boolean);
    if (parts.length > 0) {
      return parts.join(" | ");
    }

    try {
      return JSON.stringify(objectLikeError);
    } catch {
      return "未知错误";
    }
  }

  return String(error || "未知错误");
}

export function assertRemoteFileUrl(fileUrl) {
  const raw = String(fileUrl || "").trim();
  if (!raw) {
    throw new Error("上传失败：未生成 OSS 文件地址");
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`上传失败：文件地址格式无效 (${raw})`);
  }

  const protocol = String(parsed.protocol || "").toLowerCase();
  if (protocol !== "http:" && protocol !== "https:") {
    throw new Error(`上传失败：文件地址必须是 http/https (${raw})`);
  }

  const hostname = String(parsed.hostname || "").toLowerCase();
  const isLocalHost = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  if (isLocalHost) {
    throw new Error(`上传失败：文件地址指向本地环境，已阻止入库 (${raw})`);
  }
}

export function detectSourceType(file) {
  const fileName = String(file?.name || "").toLowerCase();
  if (fileName.endsWith(".epub")) return "epub";
  if (fileName.endsWith(".txt")) return "txt";
  if (fileName.endsWith(".pdf")) return "pdf";
  if (/\.(png|jpe?g|webp|gif|bmp|tiff)$/.test(fileName)) return "image";
  return "txt";
}

export function taskProgressFromStatus(status) {
  if (status.includes("完成") || status.includes("done") || status.includes("completed")) return 100;
  if (status.includes("解析中") || status.includes("processing") || status.includes("parsing")) return 55;
  if (status.includes("失败") || status.includes("failed")) return 0;
  return 10;
}

export function taskStageFromStatus(status) {
  if (status.includes("完成") || status.includes("done") || status.includes("completed")) return "done";
  if (status.includes("解析中") || status.includes("processing") || status.includes("parsing")) return "parse";
  if (status.includes("失败") || status.includes("failed")) return "error";
  return "queued";
}

export function taskStepFromStatus(status, fileName) {
  if (status.includes("完成") || status.includes("done") || status.includes("completed")) {
    return `${fileName || "文件"} 解析完成`;
  }
  if (status.includes("解析中") || status.includes("processing") || status.includes("parsing")) {
    return `正在解析 ${fileName || "文件"}`;
  }
  if (status.includes("失败") || status.includes("failed")) {
    return `${fileName || "文件"} 解析失败`;
  }
  return `${fileName || "文件"} 已入队，等待解析`;
}

export function buildUserScopedQuery({
  supabase,
  table,
  select,
  userId,
  bookId,
  limit = 0,
  orders = [],
  extraEquals = [],
}) {
  let query = supabase
    .from(table)
    .select(select)
    .eq("user_id", userId);

  if (bookId) {
    query = query.eq("book_id", bookId);
  }

  for (const [field, value] of extraEquals) {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      query = query.eq(field, value);
    }
  }

  for (const [field, ascending] of orders) {
    query = query.order(field, { ascending: Boolean(ascending) });
  }

  const numericLimit = Number(limit || 0);
  if (numericLimit > 0) {
    query = query.limit(numericLimit);
  }

  return query;
}

export async function loadLatestSourceFilesByBookId(supabase, bookIds) {
  const { data, error } = await supabase
    .from("source_files")
    .select("id, book_id, file_name, file_url, parse_status, created_at, updated_at")
    .in("book_id", bookIds)
    .order("created_at", { ascending: false });

  if (error) {
    if (isMissingRelationError(error, "source_files")) {
      return new Map();
    }
    throw error;
  }

  const latestByBookId = new Map();
  for (const item of data || []) {
    if (!latestByBookId.has(item.book_id)) {
      latestByBookId.set(item.book_id, item);
    }
  }

  return latestByBookId;
}

export function normalizeUploadStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized || normalized === "待解析" || normalized === "pending" || normalized === "queued") {
    return "待解析";
  }
  if (normalized.includes("解析中") || normalized.includes("processing") || normalized.includes("parsing")) {
    return "解析中";
  }
  if (normalized.includes("完成") || normalized.includes("done") || normalized.includes("completed")) {
    return "已完成";
  }
  if (normalized.includes("失败") || normalized.includes("failed") || normalized.includes("error")) {
    return "失败";
  }
  return String(status || "待解析");
}

export function isMissingRelationError(error, relationName) {
  const message = String(error?.message || "").toLowerCase();
  if (!message) {
    return false;
  }

  return message.includes("relation") && message.includes(String(relationName || "").toLowerCase());
}

export function normalizeTaskStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) {
    return "pending";
  }

  if (normalized.includes("完成") || normalized.includes("done") || normalized.includes("success")) {
    return "completed";
  }
  if (normalized.includes("失败") || normalized.includes("failed") || normalized.includes("error")) {
    return "failed";
  }
  if (normalized.includes("进行") || normalized.includes("running") || normalized.includes("processing")) {
    return "running";
  }
  return "pending";
}

export function taskStatusLabel(status) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "running") return "进行中";
  return "等待中";
}

export function normalizeTaskProgress(progress, status) {
  const numeric = Number(progress);
  if (Number.isFinite(numeric)) {
    return Math.max(0, Math.min(100, Math.round(numeric)));
  }

  if (status === "completed") return 100;
  if (status === "running") return 35;
  if (status === "failed") return 0;
  return 0;
}

export function normalizeNumericProgress(progress, statusLabel) {
  const value = Number(progress);
  if (Number.isFinite(value)) {
    return Math.max(0, Math.min(100, Math.round(value)));
  }
  return taskProgressFromStatus(String(statusLabel || "").toLowerCase());
}

export function summaryNameByType(type) {
  const normalized = String(type || "").trim().toLowerCase();
  if (normalized === "characters") return "角色总表";
  if (normalized === "items") return "物品总表";
  if (normalized === "storyline_events") return "剧情时间线";
  if (normalized === "world_locations") return "世界观/地点表";
  return "汇总结果";
}
