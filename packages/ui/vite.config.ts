import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Só para os testes: a biblioteca não é compilada sozinha; cada interface a inclui na própria compilação.
export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", include: ["tests/**/*.test.tsx", "tests/**/*.test.ts"] },
});
