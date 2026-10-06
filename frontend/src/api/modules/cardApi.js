import { getSupabaseClient } from "../../lib/supabase";
import {
  isMissingRelationError,
  pickFirst,
} from "../core";

export function createCardApi() {
  return {
    async getCardList(bookId, settings) {
      const supabase = getSupabaseClient();

      if (!bookId) {
        return { cards: [] };
      }

      const query = supabase
        .from("card")
        .select("card_id, book_id, type, name, intro, prompt_id, content_local_url, content_oss_url, created_at, updated_at")
        .eq("book_id", bookId)
        .order("updated_at", { ascending: false })
        .order("created_at", { ascending: false });

      const { data, error } = await query;
      if (error) {
        if (isMissingRelationError(error, "card")) {
          return { cards: [] };
        }
        throw error;
      }

      return {
        cards: (data || []).map((item) => ({
          id: pickFirst(item, ["card_id"]),
          card_id: pickFirst(item, ["card_id"]),
          book_id: item.book_id,
          type: item.type || "character",
          name: item.name || "未命名卡片",
          intro: item.intro || "",
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
