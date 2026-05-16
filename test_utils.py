import unittest
import os
from utils import compute_hash, extract_frontmatter, clean_markdown

class TestUtils(unittest.TestCase):
    def test_compute_hash(self):
        test_file = "test_hash.txt"
        content = b"Hello World"
        with open(test_file, "wb") as f:
            f.write(content)
        
        try:
            h1 = compute_hash(test_file)
            h2 = compute_hash(test_file)
            self.assertEqual(h1, h2)
            
            with open(test_file, "wb") as f:
                f.write(b"Hello World changed")
            h3 = compute_hash(test_file)
            self.assertNotEqual(h1, h3)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_extract_frontmatter_present(self):
        md = "---\ntitle: Test\ntags: [a, b]\n---\nBody text here"
        fm, body = extract_frontmatter(md)
        self.assertEqual(fm.get("title"), "Test")
        self.assertEqual(fm.get("tags"), ["a", "b"])
        self.assertEqual(body.strip(), "Body text here")

    def test_extract_frontmatter_missing(self):
        md = "Just some text without frontmatter"
        fm, body = extract_frontmatter(md)
        self.assertEqual(fm, {})
        self.assertEqual(body, md)

    def test_clean_markdown(self):
        md = """# Title
```python
print('code')
```
Some `inline code` and <br> tags.

Multiple


newlines."""
        cleaned = clean_markdown(md)
        self.assertIn("# Title", cleaned)
        self.assertNotIn("print('code')", cleaned)
        self.assertNotIn("inline code", cleaned)
        self.assertNotIn("<br>", cleaned)
        self.assertIn("Multiple\n\nnewlines.", cleaned)

if __name__ == "__main__":
    unittest.main()
