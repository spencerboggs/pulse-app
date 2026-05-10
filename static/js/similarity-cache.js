/**
 * Client-side cache for the top 10 similar users (matchmaking reads this first).
 */
(function () {
  const CACHE_KEY = 'pulse_similarity_top10_v1';
  const MAX_AGE_MS = 60 * 60 * 1000; // 1 hour

  function read(userId) {
    if (userId == null || userId === '') return null;
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (String(data.forUserId) !== String(userId)) return null;
      const ts = data.computedAt || 0;
      if (Date.now() - ts > MAX_AGE_MS) return null;
      return Array.isArray(data.matches) ? data.matches : null;
    } catch {
      return null;
    }
  }

  function write(userId, matches) {
    if (userId == null || userId === '') return;
    try {
      localStorage.setItem(
        CACHE_KEY,
        JSON.stringify({
          forUserId: String(userId),
          computedAt: Date.now(),
          matches: matches || []
        })
      );
    } catch {
      /* ignore quota */
    }
  }

  function clear() {
    try {
      localStorage.removeItem(CACHE_KEY);
    } catch {
      /* ignore */
    }
  }

  window.PulseSimilarityCache = { read, write, clear };
})();
