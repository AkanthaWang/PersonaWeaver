import { deleteObject, normalizeExtFromName, putObject } from "./ossCommon";

// 统一书籍原文存储路径：{user_id}/Books/{book_id}/source.ext
export function buildBookSourceObjectKey(userId, bookId, fileName = "source.txt") {
  const ext = normalizeExtFromName(fileName, "txt");
  return `${userId}/Books/${bookId}/source.${ext}`;
}

// 上传书籍源文件，返回 objectKey 和公网 URL。
export async function uploadBookSourceToOss({ userId, bookId, file }) {
  const objectKey = buildBookSourceObjectKey(userId, bookId, file?.name || "source.txt");
  const url = await putObject({
    objectKey,
    file,
    contentType: file?.type || "text/plain",
  });
  return {
    objectKey,
    url,
  };
}

export async function deleteBookSourceFromOssByKey(objectKey) {
  await deleteObject(objectKey);
}
