export function characterAvatarUrl(name) {
  const seed = String(name || "PersonaWeaver").trim() || "PersonaWeaver";
  const base = import.meta.env?.VITE_API_BASE_URL || "/api/v1";
  return `${base}/avatars/dicebear?seed=${encodeURIComponent(seed)}`;
}
