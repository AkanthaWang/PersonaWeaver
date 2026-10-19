import { api } from "../../api/client.js";

// 模型服务配置（Provider 与模型 Profile）的统一入口。
export const listModels = () => api.get("/settings/models");
export const createModel = (payload) => api.post("/settings/models", payload);
export const updateModel = (id, payload) => api.put(`/settings/models/${id}`, payload);
export const activateModel = (id) => api.post(`/settings/models/${id}/activate`);
export const deleteModel = (id) => api.delete(`/settings/models/${id}`);
export const testModelProfile = (id) => api.post(`/settings/models/${id}/test`);
export const getModelSelection = () => api.get("/settings/selection");
export const saveModelSelection = (payload) => api.put("/settings/selection", payload);
