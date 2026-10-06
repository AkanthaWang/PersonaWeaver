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

function toChatCompletionsUrl(inputBaseUrl) {
  const normalized = stripTrailingSlash(inputBaseUrl);
  if (/\/chat\/completions$/i.test(normalized)) {
    return normalized;
  }
  return `${normalized}/chat/completions`;
}

function toModelsUrl(inputBaseUrl) {
  const normalized = stripTrailingSlash(inputBaseUrl);
  if (/\/chat\/completions$/i.test(normalized)) {
    return normalized.replace(/\/chat\/completions$/i, "/models");
  }
  return `${normalized}/models`;
}

function maskKey(key) {
  const raw = String(key || "");
  if (raw.length <= 8) {
    return "*".repeat(raw.length || 1);
  }
  return `${raw.slice(0, 4)}...${raw.slice(-4)}`;
}

async function main() {
  const cwd = process.cwd();
  const envPath = resolve(cwd, ".env.local");
  const env = existsSync(envPath) ? readEnvFile(envPath) : {};

  const baseUrl =
    getArgValue("--base-url") ||
    getValue(env, [
      "MODEL_BASE_URL",
      "OPENAI_BASE_URL",
      "VITE_MODEL_BASE_URL",
      "VITE_OPENAI_BASE_URL",
    ]);

  const apiKey =
    getArgValue("--api-key") ||
    getValue(env, [
      "MODEL_API_KEY",
      "OPENAI_API_KEY",
      "VITE_MODEL_API_KEY",
      "VITE_OPENAI_API_KEY",
    ]);

  const model = getArgValue("--model") || getValue(env, ["MODEL_NAME", "OPENAI_MODEL", "VITE_MODEL_NAME"]) || "ecnu-plus";

  if (!baseUrl || !apiKey) {
    console.error("模型连接测试失败: 缺少 base_url 或 api_key");
    console.error("可用方式:");
    console.error("1) 命令行参数: --base-url <url> --api-key <key> --model <model>");
    console.error("2) .env.local: MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME");
    process.exitCode = 1;
    return;
  }

  const chatUrl = toChatCompletionsUrl(baseUrl);
  const modelsUrl = toModelsUrl(baseUrl);

  console.log("模型连接参数:");
  console.log(`- base_url: ${stripTrailingSlash(baseUrl)}`);
  console.log(`- chat_url: ${chatUrl}`);
  console.log(`- model: ${model}`);
  console.log(`- api_key: ${maskKey(apiKey)}`);

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${apiKey}`,
  };

  try {
    const modelsRes = await axios.get(modelsUrl, {
      headers,
      timeout: 10000,
      validateStatus: () => true,
    });

    if (modelsRes.status < 200 || modelsRes.status >= 300) {
      const detail = typeof modelsRes.data === "string" ? modelsRes.data : JSON.stringify(modelsRes.data);
      throw new Error(`models 接口失败: HTTP ${modelsRes.status} | ${detail}`);
    }

    console.log("models 接口连通成功");
  } catch (error) {
    console.error(`模型连接测试失败(models): ${error?.message || error}`);
    process.exitCode = 1;
    return;
  }

  try {
    const completionRes = await axios.post(
      chatUrl,
      {
        model,
        messages: [
          { role: "system", content: "You are a helpful assistant." },
          { role: "user", content: "你是谁？请用一句话回答。" },
        ],
        temperature: 0.2,
      },
      {
        headers,
        timeout: 20000,
        validateStatus: () => true,
      },
    );

    if (completionRes.status < 200 || completionRes.status >= 300) {
      const detail =
        typeof completionRes.data === "string"
          ? completionRes.data
          : JSON.stringify(completionRes.data);
      throw new Error(`chat.completions 失败: HTTP ${completionRes.status} | ${detail}`);
    }

    const answer = completionRes.data?.choices?.[0]?.message?.content ?? "";
    console.log("chat.completions 调用成功");
    console.log("模型回复:");
    console.log(answer || "(空回复)");
  } catch (error) {
    console.error(`模型连接测试失败(chat): ${error?.message || error}`);
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(`模型连接测试失败: ${error?.message || error}`);
  process.exitCode = 1;
});

// 运行示例:
// node .\test_modules\test-model-connection.js --base-url "https://chat.ecnu.edu.cn/open/api/v1/chat/completions" --api-key "sk-eefe6b0740f841efb5142be31ba15849" --model "ecnu-plus"
