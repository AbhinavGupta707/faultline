/** The living map — THE hero (Session C1 owns; deck.gl over Google Maps dark vector).
 *  Phase 0 stub: dark placeholder with the panel chrome. */
export default function MapPanel() {
  return (
    <section className="panel" style={{ position: "relative", height: "100%", overflow: "hidden", background: "var(--base)" }}>
      <div style={{ position: "absolute", top: 12, left: 16 }} className="eyebrow">
        Living map · deck.gl pending (C1)
      </div>
      <div
        aria-hidden
        style={{
          position: "absolute", inset: 0,
          background:
            "radial-gradient(ellipse 60% 45% at 38% 42%, rgba(45,212,191,0.07), transparent), radial-gradient(ellipse 30% 25% at 62% 55%, rgba(255,92,92,0.06), transparent)",
        }}
      />
    </section>
  );
}
