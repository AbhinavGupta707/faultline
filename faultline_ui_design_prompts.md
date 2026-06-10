# Faultline — UI Design Direction & Image-Generation Prompts

Reference mockups to feed an image generator (Midjourney / Nano Banana / Imagen / etc.), then hand the results to your coding agents as visual targets. All prompts share **one cohesive design system** so the generated screens look like one product, not a patchwork.

---

## The design system (use this in every prompt)

**Concept — a cartographic control tower / operations instrument.** Think a darkened maritime radar room crossed with a Bloomberg terminal and Linear-grade polish. It should read as a *precision instrument*, not a generic SaaS dashboard. **Spend all the boldness on one signature: the living world map where disruptions ripple through a glowing supplier graph.** Everything else stays quiet, monochrome, and data-dense.

**Palette (named hex):**
- `base #0A1422` (midnight nautical) · `panel #060D17` (deeper) · `landmass #1B2A3D` (muted slate)
- `graph-edge #2DD4BF` (teal — supplier-graph arcs) · `signal #F5B544` (amber gold — the agent's focus/actions)
- status: `risk #FF5C5C` (coral) · `watch #F5B544` (amber) · `secured #4ADE80` (mint)
- text: `ink #E6EDF6` · `ink-dim #8A9BB3`

**Typography:** a precise technical grotesque for labels/headings (e.g., Geist or Space Grotesk), a humanist mono for data/IDs/metrics (e.g., JetBrains Mono / Geist Mono). Avoid Inter-everywhere. Small, confident, generous letter-spacing on eyebrows; large numerals for metrics.

**Rules to put in every prompt:** dark mode; subtle glow/bloom only around live data; hairline 1px dividers; no drop-shadow-heavy cards; restrained; high information density with calm spacing; motion implied (ripples, pulses). Avoid: cream backgrounds, single acid-green accents, generic card grids, stock 3D blobs.

**Suffix to append to every prompt:** `— high-fidelity UI design mockup, dribbble/Figma quality, dark mode, crisp vector UI, 16:9, no lorem ipsus gibberish, realistic data labels, designed by a senior product designer.`

---

## Prompt 1 — The full control tower (hero / overview)

> A dark "supply-chain control tower" web app, full dashboard view. Left two-thirds: a dramatic dark world map (basemap `#0A1422`, landmasses `#1B2A3D`) covered in a glowing supplier network — small node dots connected by thin luminous teal (`#2DD4BF`) arcs sweeping between continents. Two disruption points emit concentric coral (`#FF5C5C`) ripple rings; one product cluster glows coral, another glows mint (`#4ADE80`) as "secured". A soft amber (`#F5B544`) scan-pulse marks where the agent is currently looking. Right third: a vertical "mission control" rail with a live agent plan (numbered steps), streaming tool-call chips, and a small ranked exposure list with mono metrics ($ at risk, days of cover). Technical grotesque headings, humanist-mono data. Hairline dividers, deep `#060D17` panels, restrained glow. Top bar reads "Faultline · Supply Chain Control Tower". — high-fidelity UI design mockup, dribbble/Figma quality, dark mode, crisp vector UI, 16:9, realistic data labels, designed by a senior product designer.

## Prompt 2 — The living map, full-bleed (the signature)

> Full-bleed dark cartographic visualization for a supply-chain risk app. A near-black ocean (`#0A1422`) and muted slate landmasses (`#1B2A3D`). A web of luminous teal (`#2DD4BF`) arcs connects supplier nodes across the globe (deck.gl arc style, soft bloom). One epicenter near western India emits expanding coral (`#FF5C5C`) concentric rings; the arcs leading from it pulse coral toward a highlighted finished-product node. Elsewhere a node transitions to mint (`#4ADE80`). A faint amber (`#F5B544`) radial sweep indicates the agent's active scan. Tiny mono labels float on key nodes ("Tier-3 · Emulsifier", "9 days cover"). Cinematic, instrument-like, premium. — high-fidelity UI mockup, dark mode, crisp vector UI, 16:9, designed by a senior product designer.

## Prompt 3 — Mission Control panel (the agent's reasoning)

> A vertical "mission control" panel from a dark agentic app. Top: current goal in a technical-grotesque heading. Below: a numbered live plan (Sense → Trace → Assess → Re-source → Verify) with the active step highlighted in amber (`#F5B544`). A stream of tool-call chips, each showing a tool name in mono and a status dot — several explicitly labelled "Elastic · match_event_to_suppliers", "Elastic · traverse_supply_graph". A confidence meter. A prominent "Approval required" gate card with Approve / Edit buttons in muted styling. Deep `#060D17` background, `#E6EDF6` text, hairline dividers, coral/amber/mint status dots. Calm, dense, precise. — high-fidelity UI mockup, dark mode, 16:9, designed by a senior product designer.

## Prompt 4 — Action Board with contingent PO + live call

> A dark "action board" panel for a supply-chain agent. A ranked list of at-risk products, each row: product name (grotesque), then mono metrics — days of cover, $ at risk — and a small status pill (coral "at risk" / amber "watch" / mint "secured"). One row is expanded to show a recommended alternate supplier and a drafted "Contingent Purchase Order" card (qty, lead time, locked price) with an Approve action. Beside it, a "Live call" mini-panel shows an in-progress voice negotiation: a waveform, a streaming transcript with speaker labels, and an amber "AI agent speaking" indicator. Deep panels, teal/amber accents, mono data. — high-fidelity UI mockup, dark mode, 16:9, designed by a senior product designer.

## Prompt 5 — Decision Log / Situation Report

> A dark, document-like "decision log" view for a supply-chain control tower. A timestamped vertical timeline of the agent's reasoning steps; each entry has a short grotesque title and mono body, and small inline "evidence" chips that cite source events (e.g., "GDELT · 11:42", "FDA recall · 09:15"), rendered as subtle teal links. A header summarizes a generated "Situation Report" with one big mono metric ($ at risk avoided) and a Download button. Hairline rules, deep `#060D17`, restrained, editorial but technical. — high-fidelity UI mockup, dark mode, 16:9, designed by a senior product designer.

## Prompt 6 — What-If stress-test console

> A dark "what-if" simulation console for a supply-chain app. A compact form to define a hypothetical disruption (event type dropdown, location, duration, magnitude slider) on the left, in muted controls. On the right, a results preview: a small dark map with a simulated coral epicenter (clearly marked "SIMULATED" in amber) rippling through teal supplier arcs, and a ranked list of projected exposures. A distinct "simulation mode" treatment — a thin amber border frame around the whole panel. Precise, instrument-like. — high-fidelity UI mockup, dark mode, 16:9, designed by a senior product designer.

## Prompt 7 — Voice interaction (talk to the tower)

> A dark voice-interaction overlay for a supply-chain control tower app. A central glowing amber (`#F5B544`) waveform/orb reacting to speech, over the dimmed control-tower background. A live transcript line: user asks "what's my biggest risk right now?" and the agent's response streams below in `#E6EDF6`. A subtle push-to-talk control and a small hint chip "Say 'approve the cold-brew re-source'". Minimal, cinematic, premium. — high-fidelity UI mockup, dark mode, 16:9, designed by a senior product designer.

---

## How to use these

1. Generate 2–3 variations per prompt; pick the most cohesive set (consistent palette + type).
2. Hand the chosen frames to your coding agent as the **visual target**, alongside the token list above (so it derives exact colors/type, not approximations).
3. Keep the **map as the one hero**; if a generated screen over-decorates the side panels, regenerate with "quieter, more restrained side panels" appended.
