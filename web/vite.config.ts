import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// fs.allow ".." so lib/replay.ts can ?raw-import contracts/fixtures/ws_replay.jsonl
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, fs: { allow: [".."] } },
  assetsInclude: ["**/*.jsonl"],
});
