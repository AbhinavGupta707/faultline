"""Live-mode smoke (manual, not collected by pytest): run the golden pipeline
with whatever ELASTIC_MODE/GEMINI_MODE the environment provides and report
contract validity, narration shape, stage outputs and timing.

    GEMINI_MODE=auto NARRATION_DELAY_S=0 python3 -m agents.tests.live_smoke

The narration-shape check collapses the negotiation-call block: the LLM script
legitimately produces 4–6 transcript beats (the frozen contract fixes payload
shapes, not call length); everything around it must still match ws_replay.jsonl.
"""
import asyncio
import time

from agents import config
from agents.llm import Gemini
from agents.tests.test_golden_path import (REPLAY, _run_golden, phase_signature,
                                           validate_ws)


def collapsed_signature(msgs: list[dict]) -> list[tuple]:
    sig, prev = [], None
    for entry in phase_signature(msgs):
        if entry == ("agent.emit", "call_event"):
            if prev != entry:
                sig.append(("agent.emit", "call_event*"))
        else:
            sig.append(entry)
        prev = entry
    return sig


def main() -> None:
    print(f"ELASTIC_MODE={config.elastic_mode()}  GEMINI_MODE={config.gemini_mode()}  "
          f"llm.enabled={Gemini().enabled()}  pro={config.model_pro()}  flash={config.model_flash()}")
    t0 = time.perf_counter()
    msgs, ctx = asyncio.run(_run_golden(approve=True))
    dur = time.perf_counter() - t0

    for m in msgs:
        validate_ws(m)
    print(f"✓ all {len(msgs)} ws messages contract-valid · run {dur:.1f}s")

    mine, ref = collapsed_signature(msgs), collapsed_signature(REPLAY)
    if mine == ref:
        print("✓ narration shape matches ws_replay.jsonl (call block collapsed)")
    else:
        print("✗ narration shape DIFFERS:")
        for i, (a, b) in enumerate(zip(mine + [None] * len(ref), ref + [None] * len(mine))):
            if a != b:
                print(f"   [{i}] mine={a}  replay={b}")
                break

    print("\n— watcher why_relevant:")
    for e in ctx.state["relevant_events"]["events"]:
        print(f"  [{e['event_id']}] {e['why_relevant'][:150]}")
        if e["supplier_hints"]:
            print(f"    hints: {e['supplier_hints']}")

    print("\n— ranked exposures:")
    for e in ctx.state["ranked_exposures"]["exposures"]:
        gap = max(0.0, e["est_disruption_days"] - e["days_of_cover"])
        expected = round(e["monthly_revenue_usd"] / 30 * gap)
        ok = "✓" if e["dollars_at_risk_usd"] == expected else "✗ MATH DRIFT"
        print(f"  #{e['rank']} {e['product_id']}: est {e['est_disruption_days']:.0f}d, "
              f"cover {e['days_of_cover']:.0f}d, ${e['dollars_at_risk_usd']:,.0f}, "
              f"sev {e['severity']}, {e['status']} {ok}")
        print(f"    {e['rationale'][:160]}")

    print("\n— negotiation transcript:")
    for m in msgs:
        if m["type"] == "agent.emit" and m["payload"]["kind"] == "call_event":
            p = m["payload"]["payload"]
            if p["event"] == "transcript":
                print(f"  {p['speaker']}: {p['text'][:140]}")

    print(f"\n— verify: {ctx.state['verify_result']['summary']}")
    decisions = [m["payload"] for m in msgs if m["type"] == "decision.logged"]
    print(f"— {len(decisions)} decisions logged, kinds: {[d['kind'] for d in decisions]}")


if __name__ == "__main__":
    main()
