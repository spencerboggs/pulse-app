// Settings persists checkbox preferences to localStorage and syncs them to Supabase when the session is signed in.
// Checkbox ids map directly to keys inside the preferences object stored in user_settings.

(() => {
  const STORAGE_KEY = 'pulse_settings_v1';
  const DEFAULTS = {
    preferences: {},
    meta: {
      lastLoadedAt: null,
      lastSavedAt: null,
      lastSyncAt: null,
      lastSyncError: null
    }
  };

  // Parses JSON safely so corrupt localStorage does not throw during first paint.
  function safeJsonParse(s) {
    try {
      return JSON.parse(s);
    } catch {
      return null;
    }
  }

  // Timestamps for status copy and debugging sync order.
  function nowIso() {
    return new Date().toISOString();
  }

  // Deep merges plain objects so server loaded preferences overlay local without dropping sibling keys.
  function mergeDeep(base, patch) {
    if (patch == null || typeof patch !== 'object') return base;
    const out = Array.isArray(base) ? [...base] : { ...base };
    Object.keys(patch).forEach((k) => {
      const pv = patch[k];
      const bv = base?.[k];
      if (pv && typeof pv === 'object' && !Array.isArray(pv)) {
        out[k] = mergeDeep(bv && typeof bv === 'object' ? bv : {}, pv);
      } else {
        out[k] = pv;
      }
    });
    return out;
  }

  // Hydrates state from browser storage then merges defaults for any missing meta or preference keys.
  function loadState() {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? safeJsonParse(raw) : null;
    return mergeDeep(DEFAULTS, parsed || {});
  }

  // Persists the full state blob including meta after each local or remote change.
  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  // Template sets data logged in when Flask session contains user_id.
  function isLoggedIn() {
    return document.body?.dataset?.loggedIn === '1';
  }

  // Every settings toggle is a checkbox with an id that becomes a preference key.
  function getCheckboxes() {
    return Array.from(document.querySelectorAll('input[type="checkbox"][id]'));
  }

  // Writes booleans onto controls and composes the human readable status line under the heading.
  function applyStateToUI(state) {
    getCheckboxes().forEach((cb) => {
      if (!cb.id) return;
      if (typeof state.preferences[cb.id] === 'boolean') cb.checked = state.preferences[cb.id];
    });

    const status = document.getElementById('settings-status');
    if (status) {
      const parts = [];
      if (state.meta.lastSavedAt) parts.push(`Saved locally: ${new Date(state.meta.lastSavedAt).toLocaleString()}`);
      if (isLoggedIn() && state.meta.lastSyncAt) {
        parts.push(`Synced to account: ${new Date(state.meta.lastSyncAt).toLocaleString()}`);
      }
      if (state.meta.lastSyncError) parts.push(`Sync: ${state.meta.lastSyncError}`);
      status.textContent = parts.length ? parts.join(' • ') : 'Preferences saved on this device.';
    }
  }

  // Snapshots all checkbox values into preferences and records lastSavedAt for the status strip.
  function readUIIntoState(prevState) {
    const state = mergeDeep(prevState, {});
    const prefs = { ...state.preferences };
    getCheckboxes().forEach((cb) => {
      if (!cb.id) return;
      prefs[cb.id] = !!cb.checked;
    });
    state.preferences = prefs;
    state.meta.lastSavedAt = nowIso();
    state.meta.lastSyncError = null;
    return state;
  }

  // Coalesces rapid toggles so one debounced pass writes storage and hits the network once.
  function debounce(fn, ms) {
    let t = null;
    return (...args) => {
      if (t) window.clearTimeout(t);
      t = window.setTimeout(() => fn(...args), ms);
    };
  }

  // AbortController avoids indefinite pending when Supabase or the network stalls.
  async function fetchWithTimeout(url, options, timeoutMs = 8000) {
    const controller = new AbortController();
    const id = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal, credentials: 'same-origin' });
    } finally {
      window.clearTimeout(id);
    }
  }

  // POSTs the current preferences map to user_settings when a session exists.
  async function syncToServer(state) {
    if (!isLoggedIn()) return state;
    try {
      const res = await fetchWithTimeout('/api/settings/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferences: state.preferences })
      });
      if (res.status === 401) return state;
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}${text ? `: ${text}` : ''}`);
      }
      state.meta.lastSyncAt = nowIso();
      state.meta.lastSyncError = null;
    } catch (e) {
      state.meta.lastSyncError = e?.message ? String(e.message) : 'Sync failed';
    }
    return state;
  }

  // GET merges remote preferences into local state on first load for signed in visitors.
  async function loadFromServer(state) {
    if (!isLoggedIn()) return state;
    try {
      const res = await fetchWithTimeout('/api/settings/load', { method: 'GET' });
      if (res.status === 401) return state;
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}${text ? `: ${text}` : ''}`);
      }
      const data = await res.json();
      if (data && typeof data === 'object' && data.preferences && typeof data.preferences === 'object') {
        state.preferences = mergeDeep(state.preferences, data.preferences);
        state.meta.lastLoadedAt = nowIso();
        state.meta.lastSyncError = null;
      }
    } catch (e) {
      state.meta.lastSyncError = e?.message ? String(e.message) : 'Load failed';
    }
    return state;
  }

  // Binds change handlers, runs initial server pull, and hooks account action buttons.
  function wireEvents() {
    let state = loadState();
    applyStateToUI(state);

    // Each toggle change saves locally then attempts server upsert before refreshing status text.
    const persist = debounce(async () => {
      state = readUIIntoState(state);
      saveState(state);
      state = await syncToServer(state);
      saveState(state);
      applyStateToUI(state);
    }, 250);

    getCheckboxes().forEach((cb) => {
      cb.addEventListener('change', () => persist());
    });

    (async () => {
      state = await loadFromServer(state);
      saveState(state);
      applyStateToUI(state);
    })();

    document.getElementById('btn-logout')?.addEventListener('click', () => {
      window.location.href = '/logout';
    });

    document.getElementById('btn-delete-account')?.addEventListener('click', () => {
      if (confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
        alert('Account deletion will be implemented with backend connection');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', wireEvents);
})();
