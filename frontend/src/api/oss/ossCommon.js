import { buildOssPublicUrl, createOssClient, getOssConfigFromEnv } from "../../lib/oss";

export function getOssRuntime() {
  const config = getOssConfigFromEnv();
  const client = createOssClient(config);
  return { config, client };
}

export function normalizeExtFromName(fileName, fallbackExt = "txt") {
  const raw = String(fileName || "").trim();
  const matched = raw.match(/\.([a-zA-Z0-9]+)$/);
  if (!matched?.[1]) {
    return String(fallbackExt || "txt").replace(/^\./, "").toLowerCase();
  }
  return String(matched[1]).replace(/^\./, "").toLowerCase();
}

export function buildPublicUrl(config, objectKey) {
  return buildOssPublicUrl(config, objectKey);
}

export async function putObject({ objectKey, file, contentType }) {
  const { client, config } = getOssRuntime();
  await client.put(objectKey, file, {
    headers: contentType ? { "Content-Type": contentType } : undefined,
  });
  return buildPublicUrl(config, objectKey);
}

export async function deleteObject(objectKey) {
  const { client } = getOssRuntime();
  await client.delete(objectKey);
}
