import subprocess

from fastapi import FastAPI
from librarian_logging import configure_logging
from pydantic import BaseModel, Field

configure_logging()

app = FastAPI(title="Librarian Codex Broker", version="0.1.0")


class Passage(BaseModel):
    citation: str
    text: str


class GenerateRequest(BaseModel):
    question: str
    passages: list[Passage] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    answer: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
def generate(request: GenerateRequest) -> GenerateResponse:
    prompt = build_prompt(request)
    completed = subprocess.run(
        ["codex", "exec", "--ephemeral", prompt],
        check=True,
        capture_output=True,
        text=True,
    )
    return GenerateResponse(answer=completed.stdout.strip())


def build_prompt(request: GenerateRequest) -> str:
    passages = "\n\n".join(
        f"[{index}] {passage.citation}\n{passage.text}"
        for index, passage in enumerate(request.passages, start=1)
    )
    return (
        "Answer the user's question using only the provided passages. "
        "Cite passage numbers when making claims. If the passages are "
        "insufficient, say what is missing.\n\n"
        f"Question:\n{request.question}\n\n"
        f"Passages:\n{passages}"
    )
