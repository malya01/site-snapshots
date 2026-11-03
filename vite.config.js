import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + preview images to FastAPI so no CORS/URL config is needed in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
  "/api": "http://127.0.0.1:8000",
  "/previews": "http://127.0.0.1:8000",
},

  },
});
