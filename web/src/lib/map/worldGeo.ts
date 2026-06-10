/** World landmass geometry for the deck.gl basemap (Session C1 owns).
 *  We render the world as GeoJSON polygons in pure deck.gl rather than over a tile
 *  basemap — this gives EXACT palette fidelity (ocean #0A1422 / land #1B2A3D) with no
 *  Maps API key and full offline determinism, the right call for the replay-only dev path.
 *  (The @deck.gl/google-maps interleaved path remains a one-component swap if desired.) */
import { feature } from "topojson-client";
import worldTopo from "world-atlas/countries-110m.json";
import type { Feature, FeatureCollection, Geometry } from "geojson";

let cached: FeatureCollection<Geometry> | null = null;

export function getWorldLand(): Feature<Geometry>[] {
  if (!cached) {
    const topo = worldTopo as unknown as {
      objects: { countries: Parameters<typeof feature>[1] };
    };
    cached = feature(topo as never, topo.objects.countries) as FeatureCollection<Geometry>;
  }
  return cached.features;
}
