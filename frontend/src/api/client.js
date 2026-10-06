import { createAuthApi } from "./modules/authApi";
import { createBookApi } from "./modules/bookApi";
import { createTaskApi } from "./modules/taskApi";
import { createSummaryApi } from "./modules/summaryApi";
import { createCardApi } from "./modules/cardApi";
import { createChatApi } from "./modules/chatApi";

// 统一对外导出 api 对象，保持现有页面调用方式不变。
export const api = {
  ...createAuthApi(),
  ...createBookApi(),
  ...createTaskApi(),
  ...createSummaryApi(),
  ...createCardApi(),
  ...createChatApi(),
};
