import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // served from the backend at /app on the GB10
  base: "/app/",
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react()],
});
