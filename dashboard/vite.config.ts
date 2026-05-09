import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Forced port 3000 so the dashboard's dev server URL matches:
//   - the backend's CORS allow-list (http://localhost:3000)
//   - the docker-compose `dashboard` service port mapping
//   - the eventual production deploy target
//
// `strictPort: true` makes the dev server fail loudly if 3000 is
// occupied, instead of silently jumping to 3001 and tripping CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    host: "127.0.0.1",
  },
});
