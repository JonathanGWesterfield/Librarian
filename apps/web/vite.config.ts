import { defineConfig, type UserConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { createApiProxy } from "./vite-api-proxy-config";

/** Build the development-server proxy from the authoritative JSON configuration. */
export function createViteConfig(): UserConfig {
  return {
    plugins: [react()],
    server: { proxy: createApiProxy() },
    test: { environment: "jsdom" },
  };
}

export default defineConfig(({ command, mode }) => {
  const testConfig: UserConfig = {
    plugins: [react()],
    test: { environment: "jsdom" },
  };
  if (mode === "test" || command === "build") return testConfig;
  return createViteConfig();
});
