import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_EPUB_SHA256

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.config import resolve_books_dir
from librarian_ingestion.scan import EpubSourceError, hash_file, scan_epub_files


class ScanEpubFilesTests(unittest.TestCase):
    def test_scan_finds_epubs_recursively_and_sorts_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "nested"
            nested.mkdir()
            second = root / "b.epub"
            first = nested / "a.EPUB"
            ignored = root / "notes.txt"
            second.write_bytes(b"second")
            first.write_bytes(b"first")
            ignored.write_text("not an epub")

            discovered = scan_epub_files(root)

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
        with self.assertRaises(EpubSourceError):
            scan_epub_files("/definitely/not/a/librarian/books/dir")

    def test_hash_file_reads_file_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "book.epub"
            path.write_bytes(b"book bytes")

            self.assertEqual(hash_file(path), hashlib.sha256(b"book bytes").hexdigest())

    def test_sample_epub_has_expected_hash(self) -> None:
        self.assertEqual(hash_file(SAMPLE_EPUB), SAMPLE_EPUB_SHA256)

    def test_scan_finds_sample_epub_fixture(self) -> None:
        discovered = scan_epub_files(SAMPLE_EPUB.parent)

        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].relative_path, "sample.epub")
        self.assertEqual(discovered[0].sha256, SAMPLE_EPUB_SHA256)
        self.assertGreater(discovered[0].size_bytes, 0)


class ResolveBooksDirTests(unittest.TestCase):
    def test_env_value_wins(self) -> None:
        self.assertEqual(
            resolve_books_dir(env={"LIBRARIAN_BOOKS_DIR": "/tmp/books"}),
            Path("/tmp/books"),
        )

    def test_local_default_wins_when_present(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Epub-Books").mkdir()

            self.assertEqual(
                resolve_books_dir(env={}, cwd=root),
                root / "Epub-Books",
            )

    def test_container_default_is_last_resort(self) -> None:
        with TemporaryDirectory() as temp_dir:
            self.assertEqual(
                resolve_books_dir(env={}, cwd=Path(temp_dir)),
                Path("/books"),
            )


if __name__ == "__main__":
    unittest.main()
