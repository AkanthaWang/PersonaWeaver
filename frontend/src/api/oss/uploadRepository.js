export async function insertUploadBookAndSource(supabase, payload) {
  const { bookRow } = payload;

  const { error: insertBookError } = await insertBookWithStatusFallback(supabase, bookRow);
  if (insertBookError) {
    throw insertBookError;
  }
}

async function rollbackInsertedBook(supabase, bookRow) {
  const bookId = bookRow?.book_id;
  if (!bookId) {
    return;
  }

  const query = supabase.from("books").delete().eq("book_id", bookId);
  const userId = bookRow?.user_id;
  const { error } = userId ? await query.eq("user_id", userId) : await query;
  if (error) {
    throw new Error(`books 表删除失败: ${error.message || "未知错误"}`);
  }
}

async function insertBookWithStatusFallback(supabase, baseRow) {
  return insertWithStatusFallback(supabase, {
    table: "books",
    statusField: "status",
    statusCandidates: ["ready", "待解析", "pending"],
    baseRow,
  });
}

async function insertSourceFileWithStatusFallback(supabase, baseRow) {
  // Deprecated: source_files table no longer used, storing directly in books table via book_file_url
  return { error: null };
}

// 针对不同库表状态字段命名不一致的情况，统一回退插入策略。
async function insertWithStatusFallback(supabase, options) {
  const { table, statusField, statusCandidates, baseRow } = options;
  let lastError = null;
  let safeRow = { ...baseRow };

  for (const statusValue of statusCandidates) {
    while (true) {
      const { error } = await supabase.from(table).insert({ ...safeRow, [statusField]: statusValue });
      if (!error) {
        return { error: null, [statusField]: statusValue };
      }

      const missingColumn = extractMissingColumnName(error);
      if (missingColumn && Object.prototype.hasOwnProperty.call(safeRow, missingColumn)) {
        delete safeRow[missingColumn];
        continue;
      }

      lastError = error;
      break;
    }
  }

  return { error: lastError };
}

function extractMissingColumnName(error) {
  const message = String(error?.message || "");
  const normalized = message.toLowerCase();
  if (!normalized.includes("could not find the") || !normalized.includes("column")) {
    return "";
  }

  const match = message.match(/'([^']+)'\s+column/i);
  if (match?.[1]) {
    return String(match[1]).trim();
  }

  return "";
}
