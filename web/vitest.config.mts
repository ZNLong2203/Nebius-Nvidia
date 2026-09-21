import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Pure functions only: layout, tokenising, clamping. Components are exercised
// by the static build and by using the page; what lives in lib/ is logic whose
// mistakes are silent -- a node drawn in the wrong row, a docstring coloured as
// code -- and that is what these tests pin down.
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: { include: ["lib/**/*.test.ts"], environment: "node" },
});
