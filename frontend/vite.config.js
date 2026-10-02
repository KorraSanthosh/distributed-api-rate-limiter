import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api and /metrics are proxied to the FastAPI gateway (no CORS needed).
const API_TARGET = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": API_TARGET,
      "/metrics": API_TARGET,
    },
  },
});
