export const rnd  = () => Math.random().toString(36).slice(2);
export const now  = () => Date.now();
export const safe = (fn, fallback = null) => { try { return fn(); } catch (_) { return fallback; } };
