// Values the browser remembers for this user (localStorage): the
// interface language and the run form's last inputs. The 2026-09-24
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
