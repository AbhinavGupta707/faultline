import { useEffect, useRef } from "react";

/** Live waveform from a Player's AnalyserNode. Amber while audio is flowing, dim otherwise. */
export default function Waveform({
  getAnalyser,
  active,
}: {
  getAnalyser: () => AnalyserNode | null;
  active: boolean;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let raf = 0;
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const tick = () => {
      raf = requestAnimationFrame(tick);
      const a = getAnalyser();
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      if (!a) {
        ctx.strokeStyle = "var(--hairline)";
        ctx.beginPath();
        ctx.moveTo(0, h / 2);
        ctx.lineTo(w, h / 2);
        ctx.stroke();
        return;
      }
      const buf = new Uint8Array(a.fftSize);
      a.getByteTimeDomainData(buf);
      let speaking = false;
      for (let i = 0; i < buf.length; i++) {
        if (Math.abs(buf[i] - 128) > 4) {
          speaking = true;
          break;
        }
      }
      ctx.lineWidth = 2;
      ctx.strokeStyle = speaking ? "#f5a623" : "#2a4258";
      ctx.beginPath();
      for (let i = 0; i < buf.length; i++) {
        const x = (i / buf.length) * w;
        const y = (buf[i] / 255) * h;
        if (i) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      }
      ctx.stroke();
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [getAnalyser]);

  return (
    <canvas
      ref={ref}
      width={460}
      height={56}
      style={{
        width: "100%",
        height: 56,
        display: "block",
        background: "#08131e",
        border: "1px solid var(--hairline, #1d3b54)",
        borderRadius: 8,
        opacity: active ? 1 : 0.5,
      }}
    />
  );
}
