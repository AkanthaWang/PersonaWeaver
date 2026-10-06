import OSS from "ali-oss";

export function getOssConfigFromEnv(env = import.meta.env || {}) {
  const endpoint = readEnvValue(env, ["VITE_OSS_ENDPOINT"]);
  const bucketHost = readEnvValue(env, ["VITE_OSS_BUCKET_HOST", "VITE_OSS_RUCKET"]);
  const bucketNameFromEnv = readEnvValue(env, ["VITE_OSS_BUCKET"]);
  const accessKeyId = readEnvValue(env, ["VITE_OSS_ACCESS_KEY_ID"]);
  const accessKeySecret = readEnvValue(env, ["VITE_OSS_ACCESS_KEY_SECRET"]);

  const bucketName = bucketNameFromEnv || deriveBucketName(bucketHost);
  if (!endpoint || !bucketName || !accessKeyId || !accessKeySecret) {
    throw new Error("OSS 配置不完整，请在 .env.local 中设置 VITE_OSS_ENDPOINT、VITE_OSS_BUCKET、VITE_OSS_ACCESS_KEY_ID、VITE_OSS_ACCESS_KEY_SECRET");
  }

  return {
    endpoint,
    bucketName,
    bucketHost: bucketHost || `${bucketName}.${endpoint}`,
    accessKeyId,
    accessKeySecret,
  };
}

export function createOssClient(config) {
  return new OSS({
    endpoint: config.endpoint,
    bucket: config.bucketName,
    accessKeyId: config.accessKeyId,
    accessKeySecret: config.accessKeySecret,
    secure: true,
  });
}

export function buildOssPublicUrl(config, objectKey) {
  const normalizedHost = stripTrailingSlash(`https://${config.bucketHost}`);
  const normalizedKey = String(objectKey || "")
    .replace(/^\/+/, "")
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");

  return `${normalizedHost}/${normalizedKey}`;
}

function readEnvValue(env, keys) {
  for (const key of keys) {
    const value = env?.[key];
    if (!value) {
      continue;
    }
    const trimmed = String(value).trim();
    if (trimmed) {
      return trimmed;
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

function stripTrailingSlash(url) {
  return String(url || "").replace(/\/+$/, "");
}
