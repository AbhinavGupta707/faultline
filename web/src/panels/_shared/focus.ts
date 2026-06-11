/** Click-to-fly: panels ask C1's living map to fly to a location by dispatching a
 *  window CustomEvent. The map (C1) listens for "faultline:focus"; if nothing is
 *  listening (e.g. pure replay screenshots) it's a harmless no-op. Coordinates come
 *  from the run's event/exposure payloads already in the store. */

export interface FocusDetail {
  lat: number;
  lon: number;
  label: string;
  url?: string;
}

export const FOCUS_EVENT = "faultline:focus";

export function focusOnMap(detail: FocusDetail): void {
  try {
    window.dispatchEvent(new CustomEvent(FOCUS_EVENT, { detail }));
  } catch {
    /* no-op when CustomEvent/window unavailable */
  }
}

/** True when a left-click should open the source link instead of flying the map
 *  (modified / middle click on an evidence chip). */
export function isModifiedClick(e: { metaKey?: boolean; ctrlKey?: boolean; button?: number }): boolean {
  return Boolean(e.metaKey || e.ctrlKey || e.button === 1);
}
