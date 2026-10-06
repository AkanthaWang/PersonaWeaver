import { createClient } from "@supabase/supabase-js";

const ENV_SUPABASE_URL = String(import.meta.env?.VITE_SUPABASE_URL || "").trim();
const supabaseUrl = ENV_SUPABASE_URL || "";

const supabaseKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  import.meta.env.VITE_SUPABASE_KEY ||
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  (typeof process !== "undefined" ? process.env.SUPABASE_PUBLISHABLE_KEY || process.env.SUPABASE_KEY : undefined);

if (!supabaseKey) {
  console.warn("Missing Supabase key. Set VITE_SUPABASE_PUBLISHABLE_KEY in frontend_vue/.env.local.");
}

if (!supabaseUrl) {
  console.warn("Missing Supabase URL. Set VITE_SUPABASE_URL in frontend_vue/.env.local.");
}

// 输出当前使用的 Supabase URL 以便快速排查指向问题（若未配置则为空）
// eslint-disable-next-line no-console
console.info("Supabase URL ->", supabaseUrl || "(not set)");

export const supabase = supabaseKey && supabaseUrl ? createClient(supabaseUrl, supabaseKey) : null;

export function getSupabaseClient() {
  if (!supabase) {
    throw new Error("Supabase 未配置。请在 frontend_vue/.env.local 中设置 VITE_SUPABASE_URL 与 VITE_SUPABASE_PUBLISHABLE_KEY，然后重启开发服务器。");
  }
  return supabase;
}

export async function ensureAnonymousSession() {
  const client = getSupabaseClient();
  const { data: sessionData, error: sessionError } = await client.auth.getSession();
  if (sessionError) {
    throw sessionError;
  }
  if (sessionData?.session) {
    return sessionData.session;
  }

  const { data, error } = await client.auth.signInAnonymously();
  if (error) {
    throw error;
  }
  return data?.session || null;
}

export async function testSupabaseConnection() {
  const client = getSupabaseClient();
  const { data, error } = await client.from("users").select("*");

  if (error) {
    console.error("连接失败:", error.message);
    return { ok: false, data: null, error };
  }

  console.log("连接成功!", data);
  return { ok: true, data, error: null };
}
