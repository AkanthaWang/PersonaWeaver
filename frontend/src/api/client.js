import axios from "axios";

export const TOKEN_KEY = "personaweaver.local.token";
export const api = axios.create({ baseURL: import.meta.env?.VITE_API_BASE_URL || "/api/v1", timeout: 330000 });
api.interceptors.response.use((response) => response.data, (error) => {
  const detail = error.response?.data?.detail;
  const message = typeof detail === "string" ? detail : Array.isArray(detail)
    ? detail.map((item) => `${item.loc?.slice(1).join(".") || ""}: ${item.msg}`).join("; ")
    : error.code === "ECONNABORTED" ? "请求超时" : "无法连接本地服务";
  return Promise.reject(new Error(message));
});
export async function download(path, filename) {
  saveBlob(await api.get(path, { responseType: "blob" }), filename);
}
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function upload(path, file, params = {}) {
  return api.post(path, file, { params: { filename: file.name, ...params }, headers: { "Content-Type": "application/octet-stream" } });
}
export function uploadBatch(files) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file, file.name));
  return api.post("/books/batch", formData);
}
