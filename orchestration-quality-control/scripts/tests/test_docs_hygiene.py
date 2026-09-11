import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = REPO_ROOT / "docs"

REQUIRED_FIELDS = {
    "title",
    "id",
    "description",
    "doc_type",
    "status",
    "audience",
    "version",
    "created",
    "last_updated",
}

VALID_DOC_TYPES = {"guide", "concept", "reference", "index", "tutorial"}
VALID_STATUSES = {"active", "draft", "deprecated", "superseded"}
VALID_AUDIENCES = {"user", "integrator", "contributor"}


def _parse_frontmatter(text: str) -> dict:
    if not (text.startswith("---\n") or text.startswith("---\r\n")):
        raise ValueError("Document does not start with frontmatter ---")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("Frontmatter is not closed with ---")
    raw_yaml = text[4:end]
    fields = {}
    current_key = None
    for line in raw_yaml.splitlines():
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue
        if ":" in line_str and not line.startswith(" ") and not line.startswith("\t"):
            key, val = line_str.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            fields[key] = val
            current_key = key
        elif current_key and (line_str.startswith("- ") or line_str.startswith("* ")):
            if not isinstance(fields[current_key], list):
                fields[current_key] = []
            fields[current_key].append(line_str[2:].strip().strip('"').strip("'"))
    return fields


class DocsHygieneTest(unittest.TestCase):
    def test_docs_directory_exists(self):
        self.assertTrue(DOCS_DIR.is_dir(), f"Expected docs directory at {DOCS_DIR}")

    def test_no_obsolete_stubs_in_docs_root(self):
        forbidden = ["specs.md", "specs_2.md", "architecture.md"]
        for name in forbidden:
            path = DOCS_DIR / name
            self.assertFalse(path.exists(), f"Found obsolete file in docs/: {name}")

    def test_no_loose_binaries_in_docs_root(self):
        loose_pdfs = list(DOCS_DIR.glob("*.pdf"))
        self.assertEqual(loose_pdfs, [], f"PDFs must be in docs/references/: {loose_pdfs}")

    def test_every_markdown_file_conforms_to_schema(self):
        md_files = sorted(path for path in DOCS_DIR.glob("*.md") if path.is_file())
        self.assertTrue(len(md_files) > 0, "No markdown files found in docs/")

        for path in md_files:
            rel = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")

            with self.subTest(file=rel):
                frontmatter = _parse_frontmatter(text)

                missing = REQUIRED_FIELDS - set(frontmatter.keys())
                self.assertFalse(missing, f"{rel} missing required frontmatter fields: {missing}")

                self.assertIn(frontmatter["doc_type"], VALID_DOC_TYPES, f"{rel}: invalid doc_type")
                self.assertIn(frontmatter["status"], VALID_STATUSES, f"{rel}: invalid status")
                self.assertIn(frontmatter["audience"], VALID_AUDIENCES, f"{rel}: invalid audience")

                date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(date_pattern.match(str(frontmatter["created"])), f"{rel}: created must be YYYY-MM-DD")
                self.assertTrue(date_pattern.match(str(frontmatter["last_updated"])), f"{rel}: last_updated must be YYYY-MM-DD")

                if frontmatter["doc_type"] in {"guide", "concept"}:
                    self.assertIn("```mermaid", text, f"{rel}: user guides must include at least one Mermaid diagram")


if __name__ == "__main__":
    unittest.main()
