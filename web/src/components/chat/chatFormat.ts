// Sizes the way the rest of the app words them: whole KB above 1 KB.
export const sizeText = (chars: number | null | undefined): string => {
  const n = chars ?? 0;
  if (n < 1024) {
    return `${n} B`;
  }
  return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
};

// A tool result's error code when it answered with one.
export const resultError = (result: unknown): string | null => {
  if (result && typeof result === 'object' && 'error' in result) {
    const code = (result as { error?: unknown }).error;
    return code == null ? null : String(code);
  }
  return null;
};
