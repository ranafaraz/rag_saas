import unittest

from services.llm import _build_context_and_citations


class TestCitationDedup(unittest.TestCase):
    def test_deduplicates_citations_for_same_document(self):
        chunks = [
            {
                "content": "First chunk content.",
                "score": 0.91,
                "metadata": {
                    "doc_id": "doc-1",
                    "title": "LinkedIn Profile.pdf",
                    "source": "http://localhost:8001/files/linkedin.pdf",
                },
            },
            {
                "content": "Second chunk from same document.",
                "score": 0.88,
                "metadata": {
                    "doc_id": "doc-1",
                    "title": "LinkedIn Profile.pdf",
                    "source": "http://localhost:8001/files/linkedin.pdf",
                },
            },
            {
                "content": "Chunk from another document.",
                "score": 0.86,
                "metadata": {
                    "doc_id": "doc-2",
                    "title": "Admissions.pdf",
                    "source": "http://localhost:8001/files/admissions.pdf",
                },
            },
        ]

        context_text, citations = _build_context_and_citations(chunks)

        self.assertEqual(len(citations), 2)
        self.assertIn("[Citation 1]: First chunk content.", context_text)
        self.assertIn("[Citation 1]: Second chunk from same document.", context_text)
        self.assertIn("[Citation 2]: Chunk from another document.", context_text)
        self.assertEqual(citations[0]["title"], "LinkedIn Profile.pdf")
        self.assertEqual(citations[1]["title"], "Admissions.pdf")


if __name__ == "__main__":
    unittest.main()
