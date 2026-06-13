from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SAMPLE_EPUB = FIXTURES_DIR / "epubs" / "sample.epub"
SAMPLE_EPUB_SHA256 = "18e7f557c359bca4b9fcd3d7c5f086e33bdd13c71b33c431247f772cd52b4b5d"
SAMPLE_TITLE = "The Clockwork Garden"
SAMPLE_AUTHORS = ["Test Author"]
SAMPLE_TEXT_FRAGMENTS = [
    "Chapter One",
    "The clockwork garden woke at dawn.",
    "A brass robin counted three silver seeds.",
    "Chapter Two",
    "Mara opened the gate with a borrowed key.",
    "The garden answered in careful ticking.",
]

