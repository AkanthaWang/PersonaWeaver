import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import axios from "axios";

function readEnvFile(envPath) {
  const env = {};
  const content = readFileSync(envPath, "utf8");

  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const index = trimmed.indexOf("=");
    if (index <= 0) {
      continue;
    }

    const key = trimmed.slice(0, index).trim();
    const value = trimmed.slice(index + 1).trim();
    env[key] = value;
  }

  return env;
}

function getArgValue(flag) {
  const argv = process.argv.slice(2);
  const index = argv.findIndex((item) => item === flag);
  if (index < 0) return "";
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) return "";
  return String(value).trim();
}

function getValue(env, keys) {
  for (const key of keys) {
    const value = env[key];
    if (value && String(value).trim()) {
      return String(value).trim();
    }
  }
  return "";
}

function stripTrailingSlash(url) {
  return String(url || "").trim().replace(/\/+$/, "");
}

function safeJsonStringify(value) {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

async function checkHealth(baseUrl, path) {
  const url = `${baseUrl}${path}`;
  try {
    const res = await axios.get(url, {
      timeout: 10000,
      validateStatus: () => true,
    });

    const ok = res.status >= 200 && res.status < 300;
    const bodyText =
      typeof res.data === "string" ? res.data : safeJsonStringify(res.data);

    return {
      path,
      url,
      ok,
      status: res.status,
      detail: bodyText,
    };
  } catch (error) {
    return {
      path,
      url,
      ok: false,
      status: 0,
      detail: error?.message || String(error),
    };
  }
}

async function main() {
  const cwd = process.cwd();
  const envPath = resolve(cwd, ".env.local");
  const env = existsSync(envPath) ? readEnvFile(envPath) : {};

  const inputBaseUrl = getArgValue("--base-url") || getValue(env, ["VITE_BACKEND_URL", "BACKEND_URL"]);
  const baseUrl = stripTrailingSlash(inputBaseUrl);

  if (!baseUrl) {
    console.error("后端连接测试失败: 缺少 VITE_BACKEND_URL 或 --base-url 参数");
    process.exitCode = 1;
    return;
  }

  console.log("后端连接参数:");
  console.log(`- base_url: ${baseUrl}`);

  const targets = ["/health", "/api/v1/health"];
  const results = await Promise.all(targets.map((path) => checkHealth(baseUrl, path)));

  for (const item of results) {
    console.log(`\n[${item.ok ? "OK" : "FAIL"}] GET ${item.path}`);
    console.log(`- url: ${item.url}`);
    console.log(`- status: ${item.status}`);
    console.log(`- detail: ${item.detail}`);
  }

  const okCount = results.filter((item) => item.ok).length;
  if (okCount === 0) {
    console.error("\n后端不可达: 两个健康检查接口均失败，cloudflared 可能未连通本地 FastAPI");
    process.exitCode = 1;
    return;
  }

  if (okCount < results.length) {
    console.warn("\n后端部分可达: 至少一个健康接口成功，但并非全部成功");
    return;
  }

  console.log("\n后端在线: cloudflared 已可访问本地 FastAPI（两个健康接口均成功）");
}

main().catch((error) => {
  console.error(`后端连接测试失败: ${error?.message || error}`);
  process.exitCode = 1;
});

// 运行示例:
// node .\test_modules\test-backend-connection.js
// node .\test_modules\test-backend-connection.js --base-url "https://xxx.trycloudflare.com"
