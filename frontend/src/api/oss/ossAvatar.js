import { normalizeExtFromName, putObject } from "./ossCommon";

export function buildAvatarObjectKey(userId, fileName = "avatar.png") {
  const ext = normalizeExtFromName(fileName, "png");
  return `${userId}/Avatar/avatar.${ext}`;
}

export async function uploadAvatarToOss(userId, file) {
  const objectKey = buildAvatarObjectKey(userId, file?.name || "avatar.png");
  return putObject({
    objectKey,
    file,
    contentType: file?.type || "image/png",
  });
}
