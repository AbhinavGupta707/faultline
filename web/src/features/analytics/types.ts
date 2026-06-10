/** $defs/analytics_summary (contracts/schemas/faultline.schema.json). Extra fields are
 *  allowed and ignored — forward-compatible per the project-wide contract rule. */
export interface RiskPoint {
  date: string;
  product_id: string;
  product_name?: string;
  severity_avg: number;
  dollars_at_risk_usd: number;
}

export interface Chokepoint {
  supplier_id: string;
  name: string;
  country: string;
  tier?: number;
  incident_count: number;
  products_affected: string[];
}

export interface AnalyticsSummary {
  generated_at: string;
  window_days: number;
  runs_count: number;
  dollars_at_risk_avoided_usd: number;
  includes_backfill?: boolean;
  risk_over_time: RiskPoint[];
  top_chokepoints: Chokepoint[];
}
