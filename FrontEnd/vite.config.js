import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Version affichée dans l'app (voir components/Nav.jsx) — package.json
// reste l'unique source de vérité, à incrémenter à chaque publication
// (voir CHANGELOG.md) plutôt que dupliquer le numéro ailleurs.
const { version } = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf-8")
);

// Config volontairement minimale : le build sort dans dist/, que
// app/main.py sert tel quel en statique une fois qu'il existe.
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
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
