// Standalone voice-gateway test bench client. Self-contained — no build step.
// Mic → 16 kHz PCM16 → WS /voice/intent; WS /voice/call → 24 kHz PCM16 playback + transcript.

const $ = (id) => document.getElementById(id);
const wsBase = (location.protocol === "https:" ? "wss://" : "ws://") + location.host;

// ── health ───────────────────────────────────────────────────────────────────
fetch("/health").then((r) => r.json()).then((h) => {
  const pill = $("modePill");
  pill.textContent = h.mode === "live" ? "LIVE · Vertex" : "MOCK · no creds";
  pill.className = "pill " + (h.mode === "live" ? "live" : "mock");
  $("modelPill").textContent = h.live_model || "";
}).catch(() => { $("modePill").textContent = "gateway unreachable"; });

// ── shared 24 kHz playback with waveform analyser ──────────────────────────────
class Player {
  constructor(canvas) {
    this.ctx = null; this.rate = 24000; this.nextTime = 0;
    this.analyser = null; this.canvas = canvas; this.active = 0; this._raf = null;
  }
  ensure(rate) {
    if (!this.ctx || this.ctx.sampleRate !== rate) {
      if (this.ctx) this.ctx.close();
      this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: rate });
      this.rate = rate;
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.ctx.destination);
      this.nextTime = this.ctx.currentTime;
      this._draw();
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  }
  push(pcm16) {                       // ArrayBuffer of little-endian int16
    if (!this.ctx) this.ensure(this.rate);
    const i16 = new Int16Array(pcm16);
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const buf = this.ctx.createBuffer(1, f32.length, this.rate);
    buf.getChannelData(0).set(f32);
    const src = this.ctx.createBufferSource();
    src.buffer = buf; src.connect(this.analyser);
    const t = Math.max(this.ctx.currentTime, this.nextTime);
    src.start(t); this.nextTime = t + buf.duration;
    this.active++;
    src.onended = () => { this.active = Math.max(0, this.active - 1); };
  }
  get speaking() { return this.ctx && this.nextTime > this.ctx.currentTime + 0.02; }
  _draw() {
    if (!this.canvas) return;
    const c = this.canvas.getContext("2d");
    const buf = new Uint8Array(this.analyser.fftSize);
    const tick = () => {
      this._raf = requestAnimationFrame(tick);
      const w = this.canvas.width, h = this.canvas.height;
      c.clearRect(0, 0, w, h);
      this.analyser.getByteTimeDomainData(buf);
      c.lineWidth = 2; c.strokeStyle = this.speaking ? "#f5a623" : "#2a4258";
      c.beginPath();
      for (let i = 0; i < buf.length; i++) {
        const x = (i / buf.length) * w, y = (buf[i] / 255) * h;
        i ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.stroke();
    };
    tick();
  }
}

// ── mic capture worklet (16 kHz PCM16) via Blob URL — no bundler needed ────────
const WORKLET_SRC = `
class PCMRecorder extends AudioWorkletProcessor {
  constructor(opts){ super(); this.target = opts.processorOptions.targetRate; this.pos = 0; }
  process(inputs){
    const ch = inputs[0][0];
    if(!ch) return true;
    const ratio = sampleRate / this.target;
    const out = [];
    for(let i = this.pos; i < ch.length; i += ratio){
      const idx = Math.floor(i), a = ch[idx] || 0, b = (ch[idx+1] !== undefined ? ch[idx+1] : a);
      out.push(a + (b - a) * (i - idx));
    }
    this.pos = (this.pos % ch.length) - ch.length + (Math.ceil((ch.length - this.pos) / ratio) * ratio);
    if(this.pos < 0) this.pos = 0;
    const i16 = new Int16Array(out.length);
    for(let i = 0; i < out.length; i++){ let s = Math.max(-1, Math.min(1, out[i])); i16[i] = s < 0 ? s*32768 : s*32767; }
    if(i16.length) this.port.postMessage(i16.buffer, [i16.buffer]);
    return true;
  }
}
registerProcessor('pcm-recorder', PCMRecorder);
`;
const workletURL = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));

class Recorder {
  constructor() { this.ctx = null; this.stream = null; this.node = null; this.onframe = null; }
  async start(onframe) {
    this.onframe = onframe;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.audioWorklet.addModule(workletURL);
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm-recorder", { processorOptions: { targetRate: 16000 } });
    this.node.port.onmessage = (e) => this.onframe && this.onframe(e.data);
    src.connect(this.node);
  }
  stop() {
    if (this.node) this.node.disconnect();
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx) this.ctx.close();
    this.node = this.stream = this.ctx = null;
  }
}

// ── Voice IN ───────────────────────────────────────────────────────────────────
const ackPlayer = new Player(null);
let intentWS = null, recorder = null, recording = false;

function openIntentWS() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsBase + "/voice/intent");
    ws.binaryType = "arraybuffer";
    ws.onopen = () => resolve(ws);
    ws.onerror = reject;
    ws.onmessage = (e) => {
      if (typeof e.data !== "string") { ackPlayer.push(e.data); setAck(true); return; }
      const m = JSON.parse(e.data);
      if (m.type === "transcript.partial") setIntentLog(`<span class="hint">… ${m.text}</span>`);
      else if (m.type === "transcript.final") setIntentLog(`<b>“${m.text}”</b>`);
      else if (m.type === "audio.start") ackPlayer.ensure(m.sample_rate_hz);
      else if (m.type === "intent") showIntent(m);
      else if (m.type === "error") setIntentLog(`<span class="err">${m.message}</span>`);
    };
  });
}
function setIntentLog(html) { $("intentLog").innerHTML = html; }
function setAck(on) {
  const el = $("ackSpeaking");
  el.classList.toggle("on", on);
  el.lastElementChild.textContent = on ? "AI agent speaking" : "idle";
  if (on) setTimeout(() => { if (!ackPlayer.speaking) setAck(false); }, 400);
}
function showIntent(m) {
  const j = $("intentJson");
  j.style.display = "block";
  j.textContent = JSON.stringify(m.intent, null, 2);
  const a = m.intent.action;
  setIntentLog(`<b>“${m.transcript}”</b> → <span class="ok">${a}</span> (${(m.intent.confidence*100|0)}%)`);
}

async function startTalking() {
  if (recording) return;
  recording = true;
  $("ptt").classList.add("rec");
  intentWS = await openIntentWS();
  intentWS.send(JSON.stringify({
    type: "start", sample_rate_hz: 16000, encoding: "pcm16",
    pending_approval_id: $("approvalId").value || undefined,
    text: $("mockText").value || undefined,           // mock-mode hint (ignored when live)
  }));
  try {
    recorder = new Recorder();
    await recorder.start((buf) => intentWS && intentWS.readyState === 1 && intentWS.send(buf));
  } catch (err) {
    setIntentLog(`<span class="hint">no mic (${err.name}) — using text in mock mode</span>`);
  }
}
function stopTalking() {
  if (!recording) return;
  recording = false;
  $("ptt").classList.remove("rec");
  if (recorder) { recorder.stop(); recorder = null; }
  if (intentWS && intentWS.readyState === 1) intentWS.send(JSON.stringify({ type: "stop" }));
}
const ptt = $("ptt");
ptt.addEventListener("mousedown", startTalking);
ptt.addEventListener("touchstart", (e) => { e.preventDefault(); startTalking(); });
window.addEventListener("mouseup", stopTalking);
window.addEventListener("touchend", stopTalking);

$("sendMock").addEventListener("click", async () => {
  const text = $("presetCmd").value;
  $("mockText").value = text;
  const ws = await openIntentWS();
  ws.send(JSON.stringify({ type: "start", sample_rate_hz: 16000, encoding: "pcm16",
    pending_approval_id: $("approvalId").value || undefined, text }));
  ws.send(JSON.stringify({ type: "stop" }));
});

// ── Voice OUT ───────────────────────────────────────────────────────────────────
const callPlayer = new Player($("wave"));
let callWS = null;

function speak(label, on) {
  const el = $("callSpeaking");
  el.classList.toggle("on", on);
  el.lastElementChild.textContent = on ? `${label} speaking` : "nobody speaking";
}
function addTurn(speaker, text) {
  const div = document.createElement("div");
  const isAgent = speaker === "faultline_agent";
  div.className = "turn " + (isAgent ? "agent" : "supplier");
  div.innerHTML = `<div class="who">${isAgent ? "✦ Faultline AI agent" : "Supplier (role-play)"}</div><div>${text}</div>`;
  $("callTranscript").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
}
let lastSpeaker = "faultline_agent";

$("callStart").addEventListener("click", () => {
  $("callTranscript").innerHTML = "";
  $("callSummary").style.display = "none";
  $("callStart").disabled = true; $("callEnd").disabled = false;
  const callId = "call-" + Date.now();
  callWS = new WebSocket(wsBase + "/voice/call");
  callWS.binaryType = "arraybuffer";
  callWS.onopen = () => callWS.send(JSON.stringify({ type: "call.start", call_id: callId, po_id: "po-2026-0042" }));
  callWS.onmessage = (e) => {
    if (typeof e.data !== "string") { callPlayer.push(e.data); speak(label(lastSpeaker), true);
      setTimeout(() => { if (!callPlayer.speaking) speak("", false); }, 300); return; }
    const m = JSON.parse(e.data);
    if (m.type === "audio.start") { callPlayer.ensure(m.sample_rate_hz); return; }
    if (m.type === "error") { $("callStatus").innerHTML = `<span class="err">${m.message}</span>`; return; }
    if (m.type !== "call.event") return;
    const p = m.payload;
    if (p.event === "status") $("callStatus").textContent = p.status;
    else if (p.event === "transcript") { lastSpeaker = p.speaker; addTurn(p.speaker, p.text); }
    else if (p.event === "summary") {
      const s = $("callSummary"); s.style.display = "block";
      s.textContent = (p.summary.agreed ? "✓ AGREED — " : "✗ no deal — ") + JSON.stringify(p.summary, null, 2);
    }
    if (p.event === "status" && p.status === "ended") endCall(false);
  };
  callWS.onclose = () => endCall(false);
});
function label(s) { return s === "faultline_agent" ? "AI agent" : "Supplier"; }
function endCall(send) {
  if (send && callWS && callWS.readyState === 1)
    callWS.send(JSON.stringify({ type: "call.end", call_id: "call-x" }));
  $("callStart").disabled = false; $("callEnd").disabled = true;
  speak("", false);
}
$("callEnd").addEventListener("click", () => { endCall(true); if (callWS) callWS.close(); });
