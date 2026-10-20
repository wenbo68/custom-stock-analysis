// Values the browser remembers for this user (localStorage): the
// interface language and the run form's last inputs. Values this tab
// remembers (sessionStorage): the chat box's unsent draft. The 2026-09-24
// vocabulary rename renamed their keys too, which would have dropped
// every saved value (owner audit 2026-09-25) — so a read falls back to
// the key an earlier build used and moves the value to the new key.

export function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** This tab's own storage: kept across page switches and a refresh, gone with the tab. */
export function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Stores `value` under `key`, or drops the key when the value is empty.
 *  Quietly does nothing when storage is unusable (private mode, full). */
export function writeStoredValue(storage: Storage | null | undefined, key: string, value: string | null): void {
  if (!storage) {
    return;
  }
  try {
    if (value) {
      storage.setItem(key, value);
    } else {
      storage.removeItem(key);
    }
  } catch {
    // storage unavailable — the page works without it
  }
}

/** The value under `key`; failing that, the one under `legacyKey`, moved
 *  to `key` on the way. Null when neither exists or storage is unusable. */
export function readStoredValue(storage: Storage | null | undefined, key: string, legacyKey?: string): string | null {
  if (!storage) {
    return null;
  }
  try {
    const current = storage.getItem(key);
    if (current) {
      return current;
    }
    if (!legacyKey) {
      return null;
    }
    const legacy = storage.getItem(legacyKey);
    if (!legacy) {
      return null;
    }
    storage.setItem(key, legacy);
    storage.removeItem(legacyKey);
    return legacy;
  } catch {
    return null;
  }
}
