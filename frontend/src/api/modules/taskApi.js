import { getSupabaseClient } from "../../lib/supabase";
import {
  buildUserScopedQuery,
  isMissingRelationError,
  normalizeTaskProgress,
  normalizeTaskStatus,
  resolveCurrentUserId,
  taskStatusLabel,
  pickFirst,
} from "../core";

export function createTaskApi() {
  return {
    async getExtractionTasks(bookId, settings, options = {}) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const query = buildUserScopedQuery({
        supabase,
        table: "extraction_tasks",
        select: "id, user_id, book_id, task_type, status, progress, error_message, created_at, updated_at",
        userId,
        bookId,
        limit: Number(options?.limit || 0),
        orders: [
          ["updated_at", false],
          ["created_at", false],
        ],
      });

      const { data, error } = await query;

      if (error) {
        if (isMissingRelationError(error, "extraction_tasks")) {
          return { tasks: [] };
        }
        throw error;
      }

      return {
        tasks: (data || []).map((item) => {
          const status = normalizeTaskStatus(item.status);
          return {
            id: pickFirst(item, ["id", "task_id"]),
            user_id: item.user_id,
            book_id: item.book_id,
            task_type: String(item.task_type || "").trim() || "unknown",
            status,
            status_label: taskStatusLabel(status),
            progress: normalizeTaskProgress(item.progress, status),
            error_message: item.error_message || null,
            created_at: item.created_at,
            updated_at: item.updated_at,
          };
        }),
      };
    },

    async getTaskLogs(settings, options = {}) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const query = buildUserScopedQuery({
        supabase,
        table: "task_logs",
        select: "id, task_id, user_id, level, message, detail_json, created_at",
        userId,
        limit: Number(options?.limit || 0),
        orders: [["created_at", false]],
        extraEquals: options?.taskId ? [["task_id", options.taskId]] : [],
      });

      const { data, error } = await query;
      if (error) {
        if (isMissingRelationError(error, "task_logs")) {
          return { logs: [] };
        }
        throw error;
      }

      return {
        logs: (data || []).map((item) => ({
          id: item.id,
          task_id: item.task_id,
          user_id: item.user_id,
          level: String(item.level || "info").toLowerCase(),
          message: item.message || "",
          detail_json: item.detail_json || null,
          created_at: item.created_at,
        })),
      };
    },

    async getChapterExtractions(bookId, settings) {
      const supabase = getSupabaseClient();
      const userId = await resolveCurrentUserId(supabase, settings?.auth_token);

      const query = buildUserScopedQuery({
        supabase,
        table: "chapter_extractions",
        select: "*",
        userId,
        bookId,
        orders: [
          ["updated_at", false],
          ["created_at", false],
        ],
      });

      const { data, error } = await query;
      if (error) {
        if (isMissingRelationError(error, "chapter_extractions")) {
          return { extractions: [] };
        }
        throw error;
      }

      return {
        extractions: (data || []).map((item) => ({
          id: pickFirst(item, ["id", "extraction_id"]),
          user_id: item.user_id,
          book_id: item.book_id,
          extractor_type: String(item.extractor_type || "unknown"),
          book_extraction_json_local_url: item.book_extraction_json_local_url || null,
          book_extraction_json_oss_url: item.book_extraction_json_oss_url || null,
          model_name: item.model_name || null,
          created_at: item.created_at || null,
          updated_at: item.updated_at || null,
        })),
      };
    },
  };
}
