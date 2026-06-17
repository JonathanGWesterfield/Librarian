import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_EPUB_SHA256

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_config.config import resolve_books_dir
from librarian_ingestion.scan import EpubSourceError, hash_file, scan_epub_files


class ScanEpubFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_finds_epubs_recursively_and_sorts_them(self) -> None:
        """Verify scanner discovery behavior, not EPUB parsing.
        This protects recursive lookup, case-insensitive `.epub` handling,
        deterministic ordering, file sizes, and content hashes.
        """
        nested = self.root / "nested"
        nested.mkdir()
        second = self.root / "b.epub"
        first = nested / "a.EPUB"
        ignored = self.root / "notes.txt"
        second.write_bytes(b"second")
        first.write_bytes(b"first")
        ignored.write_text("not an epub")

        discovered = scan_epub_files(self.root)

        self.assertEqual(
            [epub.relative_path for epub in discovered],
            ["b.epub", "nested/a.EPUB"],
        )
        self.assertEqual(discovered[0].size_bytes, len(b"second"))
        self.assertEqual(
            discovered[0].sha256,
            hashlib.sha256(b"second").hexdigest(),
        )

    def test_scan_rejects_missing_directory(self) -> None:
        """Verify bad source configuration fails loudly.
        The ingestor should not silently continue when the configured books
        directory is missing, because that would hide setup mistakes.
        """
        with self.assertRaises(EpubSourceError):
            scan_epub_files("/definitely/not/a/librarian/books/dir")

    def test_hash_file_reads_file_content(self) -> None:
        """Verify hashing is based on file bytes.
        The file hash is our change-detection key, so this test protects the
        idempotency layer from using names, timestamps, or partial content.
        """
        path = self.root / "book.epub"
        path.write_bytes(b"book bytes")

        self.assertEqual(hash_file(path), hashlib.sha256(b"book bytes").hexdigest())

    def test_sample_epub_has_expected_hash(self) -> None:
        """Verify the deterministic fixture has not changed unexpectedly.
        If this hash changes, parser/storage expectations may also need to be
        reviewed because the source-of-truth EPUB is different.
        """
        self.assertEqual(hash_file(SAMPLE_EPUB), SAMPLE_EPUB_SHA256)

    def test_scan_finds_sample_epub_fixture(self) -> None:
        """Verify the scanner can discover our real test EPUB fixture.
        This connects the scan layer to the fixture used by parser and storage
        tests, giving us one stable book through the ingestion pipeline.
        """
        discovered = scan_epub_files(SAMPLE_EPUB.parent)

        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].relative_path, "sample.epub")
        self.assertEqual(discovered[0].sha256, SAMPLE_EPUB_SHA256)
        self.assertGreater(discovered[0].size_bytes, 0)


class ResolveBooksDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_env_value_wins(self) -> None:
        """Verify explicit configuration takes precedence.
        This lets local runs, Docker, and future automation point ingestion at
        different source folders without changing code.
        """
        self.assertEqual(
            resolve_books_dir(env={"LIBRARIAN_BOOKS_DIR": "/tmp/books"}),
            Path("/tmp/books"),
        )

    def test_local_default_wins_when_present(self) -> None:
        """Verify the local `Epub-Books` convention works without env setup.
        This keeps development ergonomic on this machine while still allowing
        environment-based configuration for other contexts.
        """
        (self.root / "Epub-Books").mkdir()

        self.assertEqual(
            resolve_books_dir(env={}, cwd=self.root),
            self.root / "Epub-Books",
        )

    def test_container_default_is_last_resort(self) -> None:
        """Verify the Docker default is used only as a fallback.
        If no env var or local folder is present, containerized ingestion should
        look at `/books`, which matches the Compose volume mount.
        """
        self.assertEqual(
            resolve_books_dir(env={}, cwd=self.root),
            Path("/books"),
        )


if __name__ == "__main__":
    unittest.main()
