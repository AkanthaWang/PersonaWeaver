import { getSupabaseClient } from "../../lib/supabase";
import { deleteBookSourceFromOssByKey, uploadBookSourceToOss } from "../oss/ossBook";
import { insertUploadBookAndSource } from "../oss/uploadRepository";
import {
  assertRemoteFileUrl,
  backendApiV1Base,
  buildHeaders,
  detectSourceType,
  formatUnknownError,
  hashFile,
  normalizeNumericProgress,
  normalizeOptionalText,
  normalizeUploadStatus,
  resolveCurrentUserId,
  taskProgressFromStatus,
  taskStageFromStatus,
  taskStepFromStatus,
  createId,
  createShortId,
  axios,
} from "../core";

export function createBookApi() {
  return {
    async uploadFile(file, bookName, settings, options = {}) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);
      const now = new Date().toISOString();
      const bookId = createShortId("book");

      const normalizedTitle = String(bookName || file?.name || "未命名书籍").trim() || "未命名书籍";
      const sourceType = String(options?.source_type || detectSourceType(file)).toLowerCase();
      const author = normalizeOptionalText(options?.author);
      const language = normalizeOptionalText(options?.language);

      const fileHash = await hashFile(file);
      const uploadRes = await uploadBookSourceToOss({ userId, bookId, file });
      const storagePath = uploadRes.objectKey;
      const fileUrl = uploadRes.url;
      assertRemoteFileUrl(fileUrl);

      try {
        await insertUploadBookAndSource(supabase, {
          bookRow: {
            book_id: bookId,
            user_id: userId,
            title: normalizedTitle,
            author,
            source_type: sourceType,
            language,
            book_file_url: fileUrl,
            status: "ready",
            progress: 0,
            err_message: null,
            created_at: now,
            updated_at: now,
          },
        });
      } catch (error) {
        let rollbackErrorMessage = "";
        try {
          await deleteBookSourceFromOssByKey(storagePath);
        } catch (rollbackError) {
          rollbackErrorMessage = formatUnknownError(rollbackError);
        }

        const insertErrorMessage = formatUnknownError(error);
        throw new Error(`上传文件后入库失败，已回滚 OSS 文件。错误: ${insertErrorMessage}`);
      }

      return {
        task_id: bookId,
        book_id: bookId,
        status: "ready",
        created_at: now,
      };
    },

    async getTaskStatus(taskId, settings) {
      const supabase = getSupabaseClient();
      await resolveCurrentUserId(supabase, settings?.auth_token);

      const { data: bookRow, error: bookError } = await supabase
        .from("books")
        .select("book_id, status, progress, updated_at")
        .eq("book_id", taskId)
        .maybeSingle();

      if (bookError) {
        throw bookError;
      }

      if (!bookRow) {
        throw new Error("任务不存在或已删除");
      }

      const status = normalizeUploadStatus(bookRow.status);
      return {
        task_id: bookRow.book_id,
        book_id: bookRow.book_id,
        status,
        progress: normalizeNumericProgress(bookRow.progress, status),
        stage: taskStageFromStatus(status.toLowerCase()),
        current_step: taskStepFromStatus(status.toLowerCase(), "source.txt"),
        error: status === "失败" ? "解析失败" : null,
      };
    },

    async extractRoles(payload, settings) {
      const res = await axios.post(`${backendApiV1Base()}/extract`, payload, {
        headers: buildHeaders(settings),
      });
      return res.data;
    },

    async startExtractTask(payload, settings) {
      const url = `${backendApiV1Base()}/extract`;
      const headers = buildHeaders(settings);
      // 调试日志：在浏览器控制台输出请求信息，便于排查 Network Error（CORS/证书/不可达）
      try {
        // eslint-disable-next-line no-console
        console.info("startExtractTask ->", { url, payload, headers });
        const res = await axios.post(url, payload, { headers });
        return res.data;
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("startExtractTask error ->", err);
        // 将 axios/网络错误格式化并抛出，便于前端显示更明确的提示
        const message = formatUnknownError(err) || "Network Error";
        const error = new Error(message);
        error.original = err;
        throw error;
      }
    },

    async getBooks(settings) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const { data: booksData, error: booksError } = await supabase
        .from("books")
        .select("book_id, title, status, progress, book_file_url, err_message, created_at, updated_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false });

      if (booksError) {
        throw booksError;
      }

      return {
        books: (booksData || []).map((item) => {
          const normalizedStatus = normalizeUploadStatus(item.status);

          return {
            book_id: item.book_id,
            book_name: item.title,
            status: normalizedStatus,
            file_name: "source.txt",
            file_url: item.book_file_url || null,
            source_file_id: null,
            progress: normalizeNumericProgress(item.progress, normalizedStatus),
            stage: taskStageFromStatus(normalizedStatus),
            err_message: item.err_message || null,
            created_at: item.created_at,
            updated_at: item.updated_at || null,
          };
        }),
      };
    },

    async getBookRoles(bookId, settings) {
      const supabase = getSupabaseClient();
      await resolveCurrentUserId(supabase, settings?.auth_token);

      const { data, error } = await supabase
        .from("characters")
        .select("id, name, appearance_count, status")
        .eq("book_id", bookId)
        .order("appearance_count", { ascending: false });

      if (error) {
        const message = String(error?.message || "").toLowerCase();
        if (message.includes("relation") && message.includes("characters")) {
          return { book_id: bookId, roles: [] };
        }
        throw error;
      }

      return {
        book_id: bookId,
        roles: (data || []).map((item) => ({
          role_id: item.id,
          name: item.name,
          occurrence_count: item.appearance_count || 0,
          extraction_status: item.status === "完整动态角色卡" ? 1 : 0,
        })),
      };
    },

    async getCharacters(settings) {
      const res = await axios.get(`${backendApiV1Base()}/characters`, {
        headers: buildHeaders(settings),
      });
      return res.data;
    },

    async getCharacterDetail(charId, settings) {
      const res = await axios.get(`${backendApiV1Base()}/characters/${charId}`, {
        headers: buildHeaders(settings),
      });
      return res.data;
    },
  };
}
