import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.retrieval import _rerank_chunks


class TestRetrievalRanking(unittest.TestCase):
    def test_prefers_newer_effective_date_when_semantic_close(self):
        chunks = [
            {
                "content": "Old admissions deadline is Nov 1.",
                "score": 0.72,
                "metadata": {"effective_at": "2022-01-01", "source_trust": 0.8},
            },
            {
                "content": "Updated admissions deadline is Dec 1.",
                "score": 0.70,
                "metadata": {"effective_at": "2030-01-01", "source_trust": 0.8},
            },
        ]

        ranked = _rerank_chunks(chunks)
        self.assertIn("Updated admissions deadline", ranked[0]["content"])

    def test_prefers_higher_trust_when_semantic_equal(self):
        chunks = [
            {
                "content": "Generic blog source.",
                "score": 0.7,
                "metadata": {"effective_at": "2030-01-01", "source_trust": 0.6},
            },
            {
                "content": "Official policy source.",
                "score": 0.7,
                "metadata": {"effective_at": "2030-01-01", "source_trust": 0.95},
            },
        ]

        ranked = _rerank_chunks(chunks)
        self.assertIn("Official policy source", ranked[0]["content"])


if __name__ == "__main__":
    unittest.main()
