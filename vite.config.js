// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  root: "pyPlayUI",           // where index.html lives
  plugins: [react()],
  build: {
    outDir: "../ui",          // put the built files into /ui
    emptyOutDir: true
  },
  server: {
    host: true,
    port: 5173
  }
});
