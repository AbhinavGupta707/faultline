/** What-If console — stress-test the supply graph (UI prompt 6).
 *  A compact scenario form {event_type, location, duration, magnitude} + presets
 *  ("Suez closes 3 weeks", "frost in Minas Gerais") → POST /whatif (+ ws whatif.run).
 *  Results carry the distinct amber SIMULATED frame treatment.
 *  Session C2 owns this folder. */
import { useState } from "react";
import { AccordionPanel } from "../_shared/accordion";
import { runWhatif, useFaultline, type WhatifScenario } from "../_shared/store";
import { humanize, pct } from "../_shared/format";

const EVENT_TYPES = [
  "earthquake", "flood", "storm", "hurricane", "wildfire", "industrial_accident",
  "recall", "strike", "port_disruption", "drought", "frost", "geopolitical", "other",
];

interface Preset {
  key: string;
  label: string;
  scenario: WhatifScenario;
}

const PRESETS: Preset[] = [
  {
    key: "minas-frost",
    label: "Frost in Minas Gerais",
    scenario: { preset: "minas-frost", title: "Frost in Minas Gerais", event_type: "frost", location: { lat: -21.13, lon: -44.25 }, place_name: "Minas Gerais, Brazil", duration_days: 14, magnitude: 0.7 },
  },
  {
    key: "suez-closure-3w",
    label: "Suez closes 3 weeks",
    scenario: { preset: "suez-closure-3w", title: "Suez Canal closure (3 weeks)", event_type: "port_disruption", location: { lat: 30.02, lon: 32.56 }, place_name: "Suez Canal, Egypt", duration_days: 21, magnitude: 0.8 },
  },
  {
    key: "gulf-hurricane",
    label: "Gulf Coast hurricane",
    scenario: { preset: "gulf-hurricane", title: "Hurricane hits US Gulf Coast petrochem", event_type: "hurricane", location: { lat: 29.3, lon: -94.8 }, place_name: "US Gulf Coast", duration_days: 7, magnitude: 0.75 },
  },
  {
    key: "busan-port-strike",
    label: "Port of Busan strike",
    scenario: { preset: "busan-port-strike", title: "Port of Busan strike (10 days)", event_type: "strike", location: { lat: 35.1, lon: 129.04 }, place_name: "Port of Busan, South Korea", duration_days: 10, magnitude: 0.6 },
  },
];

const DEFAULT: WhatifScenario = {
  event_type: "flood",
  location: { lat: 22.31, lon: 73.18 },
  place_name: "",
  duration_days: 14,
  magnitude: 0.6,
};

export default function WhatIf() {
  const s = useFaultline();
  const [form, setForm] = useState<WhatifScenario>(DEFAULT);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<WhatifScenario | null>(null);
  const [pendingNote, setPendingNote] = useState<string | null>(null);

  function applyPreset(p: Preset) {
    setForm({ ...p.scenario });
    setActivePreset(p.key);
  }
  function patch(p: Partial<WhatifScenario>) {
    setForm((f) => ({ ...f, ...p }));
    setActivePreset(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const scenario = { ...form, preset: activePreset ?? form.preset };
    setSubmitted(scenario);
    setPendingNote(null);
    const res = await runWhatif(scenario);
    if (!res.accepted) {
      // replay transport or no backend reachable — the framing still demonstrates the path
      setPendingNote(
        s.replayMode
          ? "Replay mode — in live mode the identical pipeline streams simulated results into the panels above."
          : "Submitted. Awaiting the simulated run…",
      );
    }
  }

  const strip = submitted ? (
    <><b>Simulating</b> · {submitted.title ?? humanize(submitted.event_type)}</>
  ) : (
    <>stress-test a disruption · 4 presets</>
  );

  return (
    <AccordionPanel id="whatif" title="What-If" meta="stress test" strip={strip}>
      <div className="fl-presets">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            className={`fl-preset ${activePreset === p.key ? "fl-preset--active" : ""}`}
            onClick={() => applyPreset(p)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="fl-whatif">
        <form className="fl-form" onSubmit={submit}>
          <div className="fl-field">
            <label htmlFor="wi-type">Event type</label>
            <select
              id="wi-type"
              className="fl-select"
              value={form.event_type}
              onChange={(e) => patch({ event_type: e.target.value })}
            >
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>{humanize(t)}</option>
              ))}
            </select>
          </div>

          <div className="fl-field">
            <label htmlFor="wi-place">Location</label>
            <input
              id="wi-place"
              className="fl-input"
              placeholder="Place name"
              value={form.place_name ?? ""}
              onChange={(e) => patch({ place_name: e.target.value })}
            />
            <div className="fl-row2">
              <input
                className="fl-input"
                type="number"
                step="0.01"
                aria-label="Latitude"
                value={form.location.lat}
                onChange={(e) => patch({ location: { ...form.location, lat: Number(e.target.value) } })}
              />
              <input
                className="fl-input"
                type="number"
                step="0.01"
                aria-label="Longitude"
                value={form.location.lon}
                onChange={(e) => patch({ location: { ...form.location, lon: Number(e.target.value) } })}
              />
            </div>
          </div>

          <div className="fl-row2">
            <div className="fl-field">
              <label htmlFor="wi-dur">Duration (days)</label>
              <input
                id="wi-dur"
                className="fl-input"
                type="number"
                min={1}
                value={form.duration_days}
                onChange={(e) => patch({ duration_days: Number(e.target.value) })}
              />
            </div>
            <div className="fl-field">
              <label htmlFor="wi-mag">Magnitude <span className="fl-range-val">{pct(form.magnitude)}</span></label>
              <input
                id="wi-mag"
                className="fl-range"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={form.magnitude}
                onChange={(e) => patch({ magnitude: Number(e.target.value) })}
              />
            </div>
          </div>

          <button type="submit" className="fl-btn fl-btn--primary" style={{ marginTop: 2 }}>
            Run simulation
          </button>
        </form>

        <div>
          {submitted ? (
            <SimulatedResult scenario={submitted} note={pendingNote} />
          ) : (
            <div className="fl-sim" style={{ borderStyle: "dashed", opacity: 0.7 }}>
              <div className="fl-sim__banner">
                <span className="fl-dot fl-dot--watch" />
                Simulation preview
              </div>
              <div className="fl-empty" style={{ padding: 0 }}>
                Pick a preset or define a disruption, then run it. Results render here with the
                simulated frame and stream into the board above.
              </div>
            </div>
          )}
        </div>
      </div>
    </AccordionPanel>
  );
}

function SimulatedResult({ scenario, note }: { scenario: WhatifScenario; note: string | null }) {
  return (
    <div className="fl-sim">
      <div className="fl-sim__banner">
        <span className="fl-dot fl-dot--watch" />
        Simulated
      </div>
      <div className="fl-sim__placeholder">
        <span className="fl-sim__ripple" />
        <span className="fl-sim__ripple" style={{ animationDelay: "1.2s" }} />
      </div>
      <div style={{ fontSize: 13 }}>{scenario.title ?? humanize(scenario.event_type)}</div>
      <dl className="fl-kv">
        <dt>Event</dt>
        <dd>{humanize(scenario.event_type)}</dd>
        <dt>Location</dt>
        <dd>{scenario.place_name || `${scenario.location.lat.toFixed(2)}, ${scenario.location.lon.toFixed(2)}`}</dd>
        <dt>Duration</dt>
        <dd>{scenario.duration_days}d</dd>
        <dt>Magnitude</dt>
        <dd>{pct(scenario.magnitude)}</dd>
      </dl>
      {note && <div className="fl-entry__summary" style={{ color: "var(--signal)" }}>{note}</div>}
    </div>
  );
}
