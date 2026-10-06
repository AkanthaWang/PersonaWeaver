import { getSupabaseClient } from "../../lib/supabase";
import {
  isMissingRelationError,
  pickFirst,
  summaryNameByType,
} from "../core";

export function createSummaryApi() {
  return {
    async getSummaryList(bookId, settings) {
      const supabase = getSupabaseClient();

      if (!bookId) {
        return { summaries: [] };
      }

      const query = supabase
        .from("summary")
        .select("summary_id, book_id, type, name, prompt_id, content_local_url, content_oss_url, created_at, updated_at")
        .eq("book_id", bookId)
        .order("updated_at", { ascending: false })
        .order("created_at", { ascending: false });

      const { data, error } = await query;
      if (error) {
        if (isMissingRelationError(error, "summary")) {
          return { summaries: [] };
        }
        throw error;
      }

      return {
        summaries: (data || []).map((item) => ({
          id: pickFirst(item, ["summary_id"]),
          summary_id: pickFirst(item, ["summary_id"]),
          book_id: item.book_id,
          type: item.type || "",
          name: item.name || summaryNameByType(item.type),
          prompt_id: item.prompt_id || null,
          content_local_url: item.content_local_url || null,
          content_oss_url: item.content_oss_url || null,
          created_at: item.created_at || null,
          updated_at: item.updated_at || null,
        })),
      };
    },
  };
}
