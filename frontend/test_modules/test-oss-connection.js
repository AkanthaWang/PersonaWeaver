import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import OSS from "ali-oss";

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

function getValue(env, keys) {
  for (const key of keys) {
    const value = env[key];
    if (value && String(value).trim()) {
      return String(value).trim();
    }
  }
  return "";
}

function deriveBucketName(bucketHost) {
  const normalized = String(bucketHost || "").trim();
  if (!normalized) {
    return "";
  }
  return normalized.replace(/^https?:\/\//i, "").split(".")[0];
}

async function main() {
  const cwd = process.cwd();
  const envPath = resolve(cwd, ".env.local");
  if (!existsSync(envPath)) {
    throw new Error("未找到 .env.local，请先在 frontend_vue 根目录创建该文件");
  }

  const env = readEnvFile(envPath);
  const endpoint = getValue(env, ["VITE_OSS_ENDPOINT", "OSS_ENDPOINT"]);
  const bucketHost = getValue(env, ["VITE_OSS_BUCKET_HOST", "VITE_OSS_RUCKET", "OSS_BUCKET"]);
  const bucketName = getValue(env, ["VITE_OSS_BUCKET"]) || deriveBucketName(bucketHost);
  const accessKeyId = getValue(env, ["VITE_OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_ID"]);
  const accessKeySecret = getValue(env, ["VITE_OSS_ACCESS_KEY_SECRET", "OSS_ACCESS_KEY_SECRET"]);

  if (!endpoint || !bucketName || !accessKeyId || !accessKeySecret) {
    throw new Error("OSS 配置不完整，需要 endpoint、bucket、access key id、access key secret");
  }

  const client = new OSS({
    endpoint,
    bucket: bucketName,
    accessKeyId,
    accessKeySecret,
    secure: true,
  });

  const objectKey = `connectivity-test/${Date.now()}_oss-check.txt`;
  const payload = `oss connectivity check at ${new Date().toISOString()}`;

  console.log("OSS 连接参数:");
  console.log(`- endpoint: ${endpoint}`);
  console.log(`- bucket: ${bucketName}`);

  await client.put(objectKey, Buffer.from(payload, "utf8"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });

  const { content } = await client.get(objectKey);
  const text = Buffer.isBuffer(content) ? content.toString("utf8") : String(content);

  if (text !== payload) {
    throw new Error("OSS 回读内容不一致，连接或权限可能异常");
  }

  await client.delete(objectKey);

  console.log("OSS 连接测试成功: 上传、下载、删除均通过");
}

main().catch((error) => {
  console.error(`OSS 连接测试失败: ${error?.message || error}`);
  process.exitCode = 1;
});

// 测试代码: node .\test_modules\test-oss-connection.js