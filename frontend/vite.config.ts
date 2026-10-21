import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser only ever calls relative /api URLs; Vite proxies them to the
// backend inside the sandbox (never expose localhost to browser code).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: { environment: "node" },
});
