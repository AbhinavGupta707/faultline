/** Formatting helpers shared by the C2 panels. Pure, dependency-free.
 *  Folder note: panels/_shared/ is C2-owned panel-support code (sole writer C2),
 *  added because the four panels derive one normalized view-model from the same
 *  event stream. Logged in STATUS.md for Session F's visibility. */

/** $460,000 — whole-dollar, grouped, no cents. The board is mono and dense. */
export function usd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return "$" + Math.round(n).toLocaleString("en-US");
}

/** Compact money for big headline metrics: $460k, $1.2M. */
export function usdCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1_000_000) return "$" + (n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1) + "M";
  if (a >= 1_000) return "$" + Math.round(n / 1_000) + "k";
  return "$" + Math.round(n);
}

/** "9d" days-of-cover style. */
export function days(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return (Number.isInteger(n) ? n : n.toFixed(1)) + "d";
}

/** HH:MM in UTC — feeds are timestamped UTC; the evidence chips read "GDACS · 08:42". */
export function hhmm(iso: string | null | undefined): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  return d.getUTCHours().toString().padStart(2, "0") + ":" + d.getUTCMinutes().toString().padStart(2, "0");
}

/** HH:MM:SS for the decision-log timeline gutter. */
export function clock(iso: string | null | undefined): string {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  const p = (x: number) => x.toString().padStart(2, "0");
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

/** A human label for a feed source code. */
export function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    gdacs: "GDACS",
    usgs: "USGS",
    noaa: "NOAA",
    openfda: "FDA recall",
    gdelt: "GDELT",
    whatif: "What-If",
    seed: "Seed",
  };
  return map[source] ?? source.toUpperCase();
}

/** Title-case an agent / kind code: "faultline_agent" → "Faultline agent". */
export function humanize(s: string): string {
  if (!s) return "";
  const t = s.replace(/[_-]+/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Clamp a 0..1 score to a percent string. */
export function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Math.round(Math.max(0, Math.min(1, n)) * 100) + "%";
}
