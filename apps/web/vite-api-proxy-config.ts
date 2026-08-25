import { readFileSync } from "node:fs";

const librarianConfigPath = new URL("../../config/librarian.json", import.meta.url);

type ConfigDocument = {
  services?: { api_port?: unknown };
};

/** Read the local API port from the same JSON file used by Docker Compose. */
export function readConfiguredApiPort(configPath: URL = librarianConfigPath): number {
  let document: ConfigDocument;
  try {
    document = JSON.parse(readFileSync(configPath, "utf8")) as ConfigDocument;
  } catch (error) {
    const detail = error instanceof Error ? ` ${error.message}` : "";
    throw new Error(
      "Unable to read config/librarian.json. Run scripts/start_local.sh first, "
      + "or copy config/librarian.example.json to config/librarian.json." + detail,
    );
  }
  const apiPort = document.services?.api_port;
  if (
    typeof apiPort !== "number"
    || !Number.isInteger(apiPort)
    || apiPort < 1
    || apiPort > 65_535
  ) {
    throw new Error("config/librarian.json must set services.api_port to an integer from 1 through 65535.");
  }
  return apiPort;
}

/** Build Vite's same-origin `/api` development proxy from Librarian JSON. */
export function createApiProxy(configPath: URL = librarianConfigPath) {
  const apiPort = readConfiguredApiPort(configPath);
  return {
    "/api": {
      target: `http://localhost:${apiPort}`,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
    },
  };
}
