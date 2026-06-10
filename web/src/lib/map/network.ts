/** Static supply-network geography for the living map (Session C1 owns).
 *
 *  Source of truth = contracts/fixtures/{suppliers,products,supplier_graph}.json (FROZEN).
 *  Supplier coordinates are copied verbatim from suppliers.json. Products are abstract in
 *  the fixtures (no lat/lon), so finished-product nodes are placed as a cluster around
 *  Northwind's Portland, OR HQ (company_profile.json) — purely a visual convenience; ids
 *  are canonical. If the fixtures ever change, F amends the contract and we re-sync here. */

export interface NetNode {
  id: string;
  name: string;
  short: string; // tiny mono label
  kind: "supplier" | "product";
  tier?: number;
  lat: number;
  lon: number;
  country?: string;
}

export interface NetEdge {
  id: string;
  src: string;
  dst: string;
  dstType: "supplier" | "product";
  component: string;
}

export const SUPPLIERS: NetNode[] = [
  { id: "sup-vadodara-chem", name: "Vadodara Specialty Chemicals", short: "Tier-3 · Emulsifier", kind: "supplier", tier: 3, lat: 22.3072, lon: 73.1812, country: "IN" },
  { id: "sup-mumbai-blend", name: "Asha Food Ingredients", short: "Tier-1 · Blender", kind: "supplier", tier: 1, lat: 19.033, lon: 73.0297, country: "IN" },
  { id: "sup-rotterdam-blend", name: "Van Doorn Ingredient Works", short: "Tier-1 · Compounder", kind: "supplier", tier: 1, lat: 51.9056, lon: 4.4653, country: "NL" },
  { id: "sup-jurong-chem", name: "Jurong Fine Ingredients", short: "Alt · Emulsifier", kind: "supplier", tier: 3, lat: 1.3161, lon: 103.6957, country: "SG" },
  { id: "sup-lyon-emuls", name: "Provence Lipides", short: "Alt · Emulsifier", kind: "supplier", tier: 3, lat: 45.764, lon: 4.8357, country: "FR" },
  { id: "sup-guadalajara-ing", name: "Ingredientes Occidente", short: "Alt · Emulsifier", kind: "supplier", tier: 3, lat: 20.6597, lon: -103.3496, country: "MX" },
  { id: "sup-minas-coop", name: "Café Sul de Minas", short: "Tier-2 · Arabica", kind: "supplier", tier: 2, lat: -21.5556, lon: -45.4364, country: "BR" },
  { id: "sup-portland-roast", name: "Cascade Roasting Co.", short: "Tier-1 · Roaster", kind: "supplier", tier: 1, lat: 45.5152, lon: -122.6784, country: "US" },
  { id: "sup-huila-coop", name: "Cafetera del Huila", short: "Alt · Arabica", kind: "supplier", tier: 2, lat: 1.8536, lon: -76.0507, country: "CO" },
  { id: "sup-bahrain-smelt", name: "Gulf Aluminium Smelting", short: "Tier-3 · Smelter", kind: "supplier", tier: 3, lat: 26.1736, lon: 50.5478, country: "BH" },
  { id: "sup-ulsan-mill", name: "Ulsan Rolling Mill", short: "Tier-2 · Rolling mill", kind: "supplier", tier: 2, lat: 35.5384, lon: 129.3114, country: "KR" },
  { id: "sup-stockton-cans", name: "PacWest Can Manufacturing", short: "Tier-1 · Cans", kind: "supplier", tier: 1, lat: 37.9577, lon: -121.2908, country: "US" },
  { id: "sup-gulf-petchem", name: "Pelican Polymer Films", short: "Tier-2 · PET film", kind: "supplier", tier: 2, lat: 30.2266, lon: -93.2174, country: "US" },
  { id: "sup-saskatoon-oats", name: "Prairie Gold Oats", short: "Tier-1 · Oats", kind: "supplier", tier: 1, lat: 52.1332, lon: -106.67, country: "CA" },
  { id: "sup-grasse-botanicals", name: "Grasse Botanique", short: "Tier-2 · Botanicals", kind: "supplier", tier: 2, lat: 43.6589, lon: 6.926, country: "FR" },
];

// Finished-product cluster around Northwind HQ (Portland, OR ≈ 45.5, -122.7), fanned east.
export const PRODUCTS: NetNode[] = [
  { id: "prd-coldbrew-12oz", name: "Northwind Cold-Brew", short: "Cold-Brew", kind: "product", lat: 43.9, lon: -118.1 },
  { id: "prd-granola-bar", name: "Trailpoint Granola Bar", short: "Granola Bar", kind: "product", lat: 47.0, lon: -117.4 },
  { id: "prd-sparkling-botanical", name: "Vela Sparkling Botanicals", short: "Sparkling", kind: "product", lat: 45.2, lon: -114.8 },
];

export const EDGES: NetEdge[] = [
  { id: "edg-001", src: "sup-vadodara-chem", dst: "sup-mumbai-blend", dstType: "supplier", component: "cmp-emulsifier" },
  { id: "edg-002", src: "sup-vadodara-chem", dst: "sup-rotterdam-blend", dstType: "supplier", component: "cmp-emulsifier" },
  { id: "edg-003", src: "sup-mumbai-blend", dst: "prd-granola-bar", dstType: "product", component: "cmp-emulsifier" },
  { id: "edg-004", src: "sup-rotterdam-blend", dst: "prd-sparkling-botanical", dstType: "product", component: "cmp-emulsifier" },
  { id: "edg-005", src: "sup-minas-coop", dst: "sup-portland-roast", dstType: "supplier", component: "cmp-coffee-arabica" },
  { id: "edg-006", src: "sup-portland-roast", dst: "prd-coldbrew-12oz", dstType: "product", component: "cmp-coffee-arabica" },
  { id: "edg-007", src: "sup-bahrain-smelt", dst: "sup-ulsan-mill", dstType: "supplier", component: "cmp-alu-can" },
  { id: "edg-008", src: "sup-ulsan-mill", dst: "sup-stockton-cans", dstType: "supplier", component: "cmp-alu-can" },
  { id: "edg-009", src: "sup-stockton-cans", dst: "prd-coldbrew-12oz", dstType: "product", component: "cmp-alu-can" },
  { id: "edg-010", src: "sup-stockton-cans", dst: "prd-sparkling-botanical", dstType: "product", component: "cmp-alu-can" },
  { id: "edg-011", src: "sup-gulf-petchem", dst: "prd-granola-bar", dstType: "product", component: "cmp-pet-film" },
  { id: "edg-012", src: "sup-saskatoon-oats", dst: "prd-granola-bar", dstType: "product", component: "cmp-oats" },
  { id: "edg-013", src: "sup-grasse-botanicals", dst: "sup-rotterdam-blend", dstType: "supplier", component: "cmp-botanical-extract" },
  { id: "edg-014", src: "sup-rotterdam-blend", dst: "prd-sparkling-botanical", dstType: "product", component: "cmp-botanical-extract" },
];

export const NODES: NetNode[] = [...SUPPLIERS, ...PRODUCTS];

const NODE_INDEX: Record<string, NetNode> = Object.fromEntries(NODES.map((n) => [n.id, n]));
export const nodeById = (id: string): NetNode | undefined => NODE_INDEX[id];

/** position helper → [lon, lat] (deck.gl coordinate order). */
export const pos = (id: string): [number, number] | null => {
  const n = NODE_INDEX[id];
  return n ? [n.lon, n.lat] : null;
};

/** edge lookup keyed by "src>dst" for marking hot exposure paths. */
export const edgeKey = (src: string, dst: string) => `${src}>${dst}`;
export const EDGE_BY_KEY: Record<string, NetEdge> = Object.fromEntries(
  EDGES.map((e) => [edgeKey(e.src, e.dst), e])
);
