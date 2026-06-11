/** Live intelligence feed (Session C1 owns).
 *  Source of the ambient "recent events" field + the intel ticker. In replay/demo mode
 *  this is driven deterministically from contracts/fixtures/world_events.json so the
 *  recording stays pixel-stable; in live mode it polls GET /events/recent (Session B is
 *  adding it) and falls back to the same fixture until the endpoint exists. */
import worldEventsRaw from "../../../contracts/fixtures/world_events.json?raw";

export interface IntelEvent {
  id: string;
  source: string;
  title: string;
  eventType: string;
  lon: number;
  lat: number;
  place: string;
  severity: number;
  publishedAt: string;
  url: string;
  simulated: boolean;
}

interface RawEvent {
  id: string;
  source: string;
  title: string;
  event_type: string;
  location: { lat: number; lon: number };
  place_name: string;
  severity_raw: number;
  published_at: string;
  url: string;
  simulated?: boolean;
}

function normalize(e: RawEvent): IntelEvent {
  return {
    id: e.id,
    source: e.source,
    title: e.title,
    eventType: e.event_type,
    lon: e.location.lon,
    lat: e.location.lat,
    place: e.place_name,
    severity: e.severity_raw ?? 0.4,
    publishedAt: e.published_at,
    url: e.url ?? "",
    simulated: e.simulated ?? false,
  };
}

let fixtureCache: IntelEvent[] | null = null;
export function fixtureEvents(): IntelEvent[] {
  if (!fixtureCache) fixtureCache = (JSON.parse(worldEventsRaw) as RawEvent[]).map(normalize);
  return fixtureCache;
}

/** Ambient "monitored signal" dots — deterministic global hazard hotspots that give the
 *  firehose visual density (matches the "14 events scanned" narrative). These carry NO
 *  headlines — they are anonymous background noise, never claimed as specific reports. */
export const AMBIENT_NOISE: Array<{ id: string; lon: number; lat: number; severity: number }> = [
  { id: "amb-jp", lon: 139.69, lat: 35.69, severity: 0.3 },
  { id: "amb-id", lon: 106.85, lat: -6.21, severity: 0.35 },
  { id: "amb-cl", lon: -70.65, lat: -33.46, severity: 0.28 },
  { id: "amb-is", lon: -21.94, lat: 64.15, severity: 0.22 },
  { id: "amb-ca", lon: -119.42, lat: 36.78, severity: 0.32 },
  { id: "amb-tr", lon: 35.24, lat: 38.96, severity: 0.4 },
  { id: "amb-nz", lon: 174.78, lat: -41.29, severity: 0.25 },
  { id: "amb-ak", lon: -149.49, lat: 61.37, severity: 0.27 },
  { id: "amb-it", lon: 14.43, lat: 40.82, severity: 0.3 },
  { id: "amb-pr", lon: -66.59, lat: 18.22, severity: 0.26 },
];

export interface AmbientBlip {
  id: string;
  lon: number;
  lat: number;
  severity: number;
  simulated: boolean;
  hasHeadline: boolean;
}

/** the blip field = real recent events (headlined, clickable) + anonymous noise dots */
export function ambientField(events: IntelEvent[]): AmbientBlip[] {
  const real = events.map((e) => ({ id: e.id, lon: e.lon, lat: e.lat, severity: e.severity, simulated: e.simulated, hasHeadline: true }));
  const noise = AMBIENT_NOISE.map((n) => ({ ...n, simulated: false, hasHeadline: false }));
  return [...real, ...noise];
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
function utcHM(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}Z`;
}

export interface TickerItem {
  id: string;
  text: string;
  lon: number;
  lat: number;
  label: string;
  url: string;
  simulated: boolean;
}

export function tickerItems(events: IntelEvent[]): TickerItem[] {
  return events.map((e) => ({
    id: e.id,
    text: `${e.source.toUpperCase()} · ${cap(e.eventType)} · ${e.place.split(",")[0]} · ${utcHM(e.publishedAt)}`,
    lon: e.lon,
    lat: e.lat,
    label: e.title,
    url: e.url,
    simulated: e.simulated,
  }));
}

/** The live endpoint (agents /events/recent) returns FLAT lat/lon + `severity` and no
 *  event_type — a different shape from the world_event fixture. Normalize both; never
 *  let one malformed record throw the whole batch back to fixtures. */
function normalizeLive(e: Record<string, unknown>): IntelEvent | null {
  const loc = (e.location ?? {}) as { lat?: number; lon?: number };
  const lat = typeof e.lat === "number" ? e.lat : loc.lat;
  const lon = typeof e.lon === "number" ? e.lon : loc.lon;
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  const title = String(e.title ?? "");
  // derive a short type when the feed doesn't provide one (NOAA: "Flood Warning issued …")
  const derived = title.split(/ issued | for | at /i)[0].slice(0, 30) || "event";
  return {
    id: String(e.id ?? `${lat},${lon},${e.published_at}`),
    source: String(e.source ?? "feed"),
    title,
    eventType: String(e.event_type ?? derived),
    lon,
    lat,
    place: String(e.place_name ?? ""),
    severity: typeof e.severity_raw === "number" ? e.severity_raw : typeof e.severity === "number" ? e.severity : 0.4,
    publishedAt: String(e.published_at ?? ""),
    url: String(e.url ?? ""),
    simulated: Boolean(e.simulated ?? false),
  };
}

/** Live mode: poll the endpoint; the fixture is only a fallback when the endpoint is
 *  unreachable or empty — live data must never be silently replaced by canned data. */
export async function fetchRecentEvents(apiBase: string): Promise<IntelEvent[]> {
  try {
    const res = await fetch(`${apiBase}/events/recent?limit=25`, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as { events?: unknown[] } | unknown[];
    const arr = Array.isArray(data) ? data : data.events ?? [];
    const live = arr.map((e) => normalizeLive(e as Record<string, unknown>)).filter((x): x is IntelEvent => x !== null);
    if (!live.length) return fixtureEvents();
    return live;
  } catch {
    return fixtureEvents();
  }
}
