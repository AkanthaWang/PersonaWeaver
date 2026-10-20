export function characterAvatarUrl(name) {
  const seed = String(name || "PersonaWeaver").trim() || "PersonaWeaver";
  return `/api/v1/avatars/dicebear?seed=${encodeURIComponent(seed)}`;
}
