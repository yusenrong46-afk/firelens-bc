const STORAGE_KEY = "firelens.saved_scopes.v1";
const MAX_SCOPES = 3;

export type SavedScope = {
  id: string;
  label: string;
};

export function readSavedScopes(): SavedScope[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is SavedScope => (
        typeof item === "object"
        && item !== null
        && typeof (item as SavedScope).id === "string"
        && typeof (item as SavedScope).label === "string"
        && (item as SavedScope).label.trim().length > 0
      ))
      .slice(0, MAX_SCOPES);
  } catch {
    return [];
  }
}

export function addSavedScope(label: string): SavedScope[] {
  const trimmed = label.trim();
  if (!trimmed) return readSavedScopes();
  const current = readSavedScopes().filter((item) => item.label.toLocaleLowerCase() !== trimmed.toLocaleLowerCase());
  const next = [{ id: crypto.randomUUID(), label: trimmed }, ...current].slice(0, MAX_SCOPES);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function removeSavedScope(id: string): SavedScope[] {
  const next = readSavedScopes().filter((item) => item.id !== id);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function clearSavedScopes(): SavedScope[] {
  window.localStorage.removeItem(STORAGE_KEY);
  return [];
}
