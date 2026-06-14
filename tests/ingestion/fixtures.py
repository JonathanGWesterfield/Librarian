from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SAMPLE_EPUB = FIXTURES_DIR / "epubs" / "sample.epub"
SAMPLE_EPUB_SHA256 = "48e35723c92413bd4ae704ca4e460f64894dae7ca9f754f55d70ef6f4e976a37"
SAMPLE_TITLE = "The Clockwork Garden"
SAMPLE_AUTHORS = ["Test Author"]
SAMPLE_PUBLISHER = "Fixture Press"
SAMPLE_TEXT_FRAGMENTS = [
    "Chapter One",
    "The clockwork garden woke at dawn.",
    "A brass robin counted three silver seeds.",
    "Chapter Two",
    "Mara opened the gate with a borrowed key.",
    "The garden answered in careful ticking.",
]
