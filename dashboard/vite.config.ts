import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// Same origin in dev and in production: FastAPI serves dist/ at /dashboard/,
// and in dev Vite (:5173) proxies the API paths to FastAPI (:8000).
const API = "http://localhost:8000";
const API_PATHS = [
  "/predict", "/villages", "/alerts", "/events", "/replay", "/scoreboard", "/health", "/reset",
  "/detections", "/history", "/risk",
];

export default defineConfig({
  base: "/dashboard/",
  plugins: [react(), tailwindcss()],
  worker: { format: "es" }, // MapLibre starts its worker as a module worker
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    proxy: Object.fromEntries(API_PATHS.map((p) => [p, { target: API, changeOrigin: true }])),
  },
});
