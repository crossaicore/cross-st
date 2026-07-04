import unittest
from cross_st._ask_match import find_matches

_FAQ = [
    {"id": "install", "question": "How do I install cross-st?", "answer": "Run: pipx install cross-st"},
    {"id": "upgrade", "question": "How do I upgrade cross-st?", "answer": "Run: st-admin --upgrade"},
    {"id": "api_key", "question": "How do I add an API key?", "answer": "Run: st-admin --setup and follow the prompts."},
    {"id": "help", "question": "Where can I get help?", "answer": "See https://github.com/crossaicore/cross-st/discussions or https://crossai.dev/community"},
    {"id": "uninstall", "question": "How do I uninstall cross-st?", "answer": "Run: pipx uninstall cross-st"},
]

class TestAskMatch(unittest.TestCase):
    def test_exact(self):
        q = "How do I install cross-st?"
        m = find_matches(q, _FAQ, top_k=1)
        self.assertEqual(m[0]["id"], "install")
    def test_fuzzy(self):
        q = "installing cross-st"
        m = find_matches(q, _FAQ, top_k=1)
        self.assertEqual(m[0]["id"], "install")
    def test_no_match(self):
        q = "How do I bake a cake?"
        m = find_matches(q, _FAQ, top_k=1)
        self.assertTrue(bool(m[0]["_score"] < 0.3))
    def test_top_k(self):
        q = "update cross-st"
        m = find_matches(q, _FAQ, top_k=2)
        self.assertIn(m[0]["id"], ["upgrade", "install"])

if __name__ == "__main__":
    unittest.main()
