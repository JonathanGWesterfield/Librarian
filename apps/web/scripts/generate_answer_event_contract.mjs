import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compileFromFile } from "json-schema-to-typescript";

const arguments_ = process.argv.slice(2);
if (arguments_.length > 1 || (arguments_.length === 1 && arguments_[0] !== "--check")) {
  console.error("Usage: node scripts/generate_answer_event_contract.mjs [--check]");
  process.exit(2);
}

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const repositoryRoot = resolve(webRoot, "../..");
const schemaPath = resolve(
  repositoryRoot,
  "schemas/librarian/answer/v1/answer_event.schema.json",
);
const outputPath = resolve(webRoot, "src/generated/answer_event.ts");
const generated = await compileFromFile(schemaPath, {
  bannerComment: "/* This file is generated from schemas/librarian/answer/v1/answer_event.schema.json. Do not edit it directly. */",
  unreachableDefinitions: true,
});

if (arguments_[0] === "--check") {
  let existing = "";
  try {
    existing = await readFile(outputPath, "utf8");
  } catch {
    console.error("Generated answer-event types are missing. Run npm run generate:answer-event-contract.");
    process.exit(1);
  }
  if (existing !== generated) {
    console.error("Generated answer-event types are stale. Run npm run generate:answer-event-contract.");
    process.exit(1);
  }
  console.log("Generated answer-event types are current.");
} else {
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, generated, "utf8");
  console.log("Generated answer-event types.");
}
