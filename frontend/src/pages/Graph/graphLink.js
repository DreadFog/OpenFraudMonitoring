/**
 * Helpers for building and parsing the /graph deep-link.
 *
 * Seeds are carried as URL-encoded JSON in a single `seeds` query param so any
 * mix of session and STIX seeds can be expressed in one flexible route.
 */

export function buildGraphUrl(seeds) {
  const encoded = encodeURIComponent(JSON.stringify(seeds || []));
  return `/graph?seeds=${encoded}`;
}

export function sessionSeed(fsid) {
  return { kind: "session", fsid };
}

export function deviceSeed(id) {
  return { kind: "device", id };
}

export function stixSeed(type, value) {
  return { kind: "stix", type, value };
}

export function parseSeeds(searchParams) {
  const raw = searchParams.get("seeds");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
