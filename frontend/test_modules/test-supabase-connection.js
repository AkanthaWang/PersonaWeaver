import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { createClient } from "@supabase/supabase-js";

function readEnvValue(content, key) {
  const line = content
    .split(/\r?\n/)
    .find((item) => item.trim().startsWith(`${key}=`));
  if (!line) return "";
  return line.slice(line.indexOf("=") + 1).trim();
}

async function main() {
  const envPath = resolve(process.cwd(), ".env.local");
  if (!existsSync(envPath)) {
    console.error("连接失败: 未找到 .env.local 文件");
    process.exitCode = 1;
    return;
  }

  const envContent = readFileSync(envPath, "utf8");
  const supabaseUrl =
    readEnvValue(envContent, "VITE_SUPABASE_URL") || readEnvValue(envContent, "SUPABASE_URL");
  const supabaseKey =
    readEnvValue(envContent, "VITE_SUPABASE_PUBLISHABLE_KEY") ||
    readEnvValue(envContent, "VITE_SUPABASE_KEY") ||
    readEnvValue(envContent, "VITE_SUPABASE_ANON_KEY");

  if (!supabaseUrl) {
    console.error("连接失败: .env.local 缺少 VITE_SUPABASE_URL");
    process.exitCode = 1;
    return;
  }

  if (!supabaseKey) {
    console.error("连接失败: .env.local 缺少 VITE_SUPABASE_PUBLISHABLE_KEY");
    process.exitCode = 1;
    return;
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  const { data, error } = await supabase.from("users").select("user_id, username, email").limit(5);

  if (error) {
    console.error("连接失败:", error.message);
    process.exitCode = 1;
    return;
  }

  console.log("连接成功! users 表可访问。");
  console.log("示例数据条数:", data.length);
  console.log(data);
}

main().catch((error) => {
  console.error("连接失败:", error?.message || error);
  process.exitCode = 1;
});


//运行指令: node .\test_modules\test-supabase-connection.js
    