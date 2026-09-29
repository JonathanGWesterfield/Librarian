import Ajv2020 from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";

import type { AnswerEvent } from "./generated/answer_event";
import schema from "../../../schemas/librarian/answer/v1/answer_event.schema.json";
import invalidEvents from "../../../tests/fixtures/answer_delivery/v1/invalid_events.json";
import successfulLifecycle from "../../../tests/fixtures/answer_delivery/v1/success_lifecycle.json";
import terminalEvents from "../../../tests/fixtures/answer_delivery/v1/terminal_events.json";

const typedStartedEvent: AnswerEvent = {
  schema_version: "v1",
  request_id: "0d4f7c96-49f6-4ea0-8804-3b4fd3d55692",
  sequence: 1,
  event: "started",
};
void typedStartedEvent;

const invalidTypedEvent: AnswerEvent = {
  schema_version: "v1",
  request_id: "0d4f7c96-49f6-4ea0-8804-3b4fd3d55692",
  sequence: 1,
  event: "started",
  // @ts-expect-error Generated event types reject fields that the schema forbids.
  answer: "Raw answer prose is not a progress payload.",
};
void invalidTypedEvent;

const validate = new Ajv2020({ allErrors: true }).compile(schema);

describe("answer event contract", () => {
  it("accepts the complete successful lifecycle and each terminal event", () => {
    const lifecycle = successfulLifecycle as unknown as AnswerEvent[];
    const terminals = terminalEvents as unknown as AnswerEvent[];

    for (const event of [...lifecycle, ...terminals]) {
      expect(validate(event), JSON.stringify(validate.errors)).toBe(true);
    }

    expect(lifecycle.map((event) => event.sequence)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(lifecycle.map((event) => event.event)).toEqual([
      "started",
      "evidence_candidates",
      "generation_started",
      "validation_started",
      "answer_validated",
      "completed",
    ]);
    const validated = lifecycle.find(
      (event): event is Extract<AnswerEvent, { event: "answer_validated" }> =>
        event.event === "answer_validated",
    );
    const completed = lifecycle.find(
      (event): event is Extract<AnswerEvent, { event: "completed" }> => event.event === "completed",
    );
    expect(validated?.result).toEqual(completed?.result);
    expect(lifecycle.filter((event) => event.event === "completed")).toHaveLength(1);
  });

  it("rejects malformed sequence numbers and unsafe candidate or answer data", () => {
    for (const event of invalidEvents) {
      expect(validate(event)).toBe(false);
    }
  });

  it("keeps candidate progress to count, identity, and title metadata", () => {
    const lifecycle = successfulLifecycle as unknown as AnswerEvent[];
    const candidates = lifecycle.find(
      (event): event is Extract<AnswerEvent, { event: "evidence_candidates" }> =>
        event.event === "evidence_candidates",
    );

    expect(candidates).toBeDefined();
    expect(candidates?.candidate_count).toBe(2);
    expect(candidates?.candidates).toEqual([
      { candidate_id: "candidate-1", book_id: "book-1", book_title: "The Brass Orchard" },
      { candidate_id: "candidate-2", book_id: "book-2", book_title: null },
    ]);
  });
});
