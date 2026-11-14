"""Tests for simple_pdf.py: the hand-made Markdown to PDF writer."""

import re
import unittest

import simple_pdf


def pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


class MarkdownToPdfTest(unittest.TestCase):
    def test_is_a_complete_pdf(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("# Título\n\nTexto.")
        self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        offset = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
        self.assertTrue(pdf[offset:].startswith(b"xref"))

    def test_xref_offsets_point_at_the_objects(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("# A\n\n" + "linha\n" * 200)
        xref = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
        offsets = re.findall(rb"(\d{10}) 00000 n", pdf[xref:])
        for number, offset in enumerate(offsets, 1):
            start = int(offset)
            self.assertTrue(pdf[start:].startswith(f"{number} 0 obj".encode()))

    def test_portuguese_letters_use_windows_1252(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("Relatório de avaliação")
        self.assertIn("Relatório de avaliação".encode("cp1252"), pdf)

    def test_parentheses_are_escaped(self) -> None:
        self.assertIn(rb"media\([]\)", simple_pdf.markdown_to_pdf("media([])"))

    def test_long_text_gets_more_pages(self) -> None:
        self.assertEqual(pages(simple_pdf.markdown_to_pdf("curto")), 1)
        long_text = "\n".join(f"- linha {number}" for number in range(200))
        self.assertGreater(pages(simple_pdf.markdown_to_pdf(long_text)), 1)

    def test_long_paragraph_is_wrapped(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("palavra " * 100)
        self.assertGreater(pdf.count(b") Tj"), 3)

    def test_table_rows_without_the_separator(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("| A | B |\n|---|---|\n| media | 4 |")
        self.assertIn(b"media", pdf)
        self.assertNotIn(b"---", pdf)

    def test_code_block_uses_courier(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("```\nprint(1)\n```")
        self.assertIn(b"/F3 9 Tf", pdf)
        self.assertIn(b"/BaseFont /Courier", pdf)

    def test_nested_lines_are_indented(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("- teste\n  - falha\n    Esperado:")
        margin = simple_pdf.MARGIN
        self.assertIn(f"{margin + 8:.1f} ".encode(), pdf)
        self.assertIn(f"{margin + 20:.1f} ".encode(), pdf)
        self.assertIn(f"{margin + 32:.1f} ".encode(), pdf)

    def test_bold_marks_and_long_dashes_are_cleaned(self) -> None:
        pdf = simple_pdf.markdown_to_pdf("**Nota:** 20 \u2014 fim")
        self.assertIn(b"Nota: 20 - fim", pdf)


if __name__ == "__main__":
    unittest.main()
