import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Config volontairement minimale : le build sort dans dist/, que
// app/main.py sert tel quel en statique une fois qu'il existe.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // En dev, on garde le frontend et l'API sur deux ports séparés ;
    // ce proxy évite d'avoir à changer API_BASE dans src/App.jsx.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
