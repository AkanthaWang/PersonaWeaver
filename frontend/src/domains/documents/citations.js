export function citationParts(content, citation) {
  const chars = Array.from(content || "");
  const { start, end, quote } = citation || {};
  const valid = Number.isInteger(start) && Number.isInteger(end) && start >= 0 &&
    end > start && end <= chars.length && chars.slice(start, end).join("") === quote;
  return valid
    ? [chars.slice(0, start).join(""), chars.slice(start, end).join(""), chars.slice(end).join("")]
    : [content || "", "", ""];
}
