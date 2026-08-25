import { writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { createApiProxy, readConfiguredApiPort } from "../vite-api-proxy-config";

describe("Vite JSON API proxy", () => {
  it("uses the API port from Librarian JSON", () => {
    const path = configUrl({ services: { api_port: 8059 } });
    expect(readConfiguredApiPort(path)).toBe(8059);
    expect(createApiProxy(path)["/api"].target).toBe("http://localhost:8059");
  });

  it("rejects an invalid configured port", () => {
    const path = configUrl({ services: { api_port: "8000" } });
    expect(() => readConfiguredApiPort(path)).toThrow("services.api_port");
  });
});

function configUrl(payload: object): URL {
  const directory = mkdtempSync(join(tmpdir(), "librarian-vite-config-"));
  const path = join(directory, "librarian.json");
  writeFileSync(path, JSON.stringify(payload), "utf8");
  return new URL(`file://${path}`);
}
