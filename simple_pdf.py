"""
Minimal text-only PDF writer with no dependencies.
Turns a report in Markdown into an A4 PDF (Helvetica, Courier for code).
Supports headings (#, ##, ###), **bold labels**, bullets, tables,
code blocks (```) and horizontal rules (---).
"""

import re

WIDTH, HEIGHT = 595, 842
MARGIN = 56
EM_DASH, EN_DASH, ELLIPSIS = "\u2014", "\u2013", "\u2026"

_NARROW = set("iljtfI.,;:!'|()[] ")
_WIDE = set("mwMW@%")


def _text_width(text: str, size: float) -> float:
    """Rough Helvetica width, good enough for line wrapping."""
    total = 0
    for char in text:
        if char in _NARROW:
            total += 300
        elif char in _WIDE:
            total += 850
        elif char.isupper() or char.isdigit():
            total += 640
        else:
            total += 540
    return total * size / 1000


def _wrap(text: str, size: float, width: float,
          mono: bool = False) -> list[str]:
    if mono:
        per_line = max(10, int(width / (size * 0.6)))
        return [text[i:i + per_line]
                for i in range(0, max(len(text), 1), per_line)]
    lines = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and _text_width(candidate, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(
        b")", b"\\)")


def _clean(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return (text.replace(EM_DASH, "-").replace(EN_DASH, "-")
            .replace(ELLIPSIS, "..."))


def _font(name: str) -> bytes:
    return (f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} "
            "/Encoding /WinAnsiEncoding >>").encode()


class _Document:
    def __init__(self) -> None:
        self.pages: list[list[bytes]] = []
        self.new_page()

    def new_page(self) -> None:
        self._ops: list[bytes] = []
        self.pages.append(self._ops)
        self._y = HEIGHT - MARGIN

    def line(self, text: str, size: float = 10, font: str = "F1",
             indent: float = 0, spacing: float = 1.35,
             mono: bool = False) -> None:
        width = WIDTH - 2 * MARGIN - indent
        for part in _wrap(text, size, width, mono):
            if self._y - size * spacing < MARGIN:
                self.new_page()
            self._y -= size * spacing
            position = f"{MARGIN + indent:.1f} {self._y:.1f}"
            self._ops.append(f"BT /{font} {size} Tf {position} Td (".encode()
                             + _escape(part) + b") Tj ET")

    def rule(self) -> None:
        if self._y - 12 < MARGIN:
            self.new_page()
        self._y -= 8
        self._ops.append(f"0.6 w {MARGIN} {self._y:.1f} m "
                         f"{WIDTH - MARGIN} {self._y:.1f} l S".encode())
        self._y -= 4

    def space(self, amount: float) -> None:
        self._y -= amount

    def to_bytes(self) -> bytes:
        page_count = len(self.pages)
        # Objects: 1 catalog, 2 pages, 3-4 fonts, then page + content pairs,
        # and the monospace font last
        mono_font = 5 + 2 * page_count
        kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(page_count))
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
            _font("Helvetica"),
            _font("Helvetica-Bold"),
        ]
        for i, ops in enumerate(self.pages):
            content = b"\n".join(ops)
            fonts = f"/F1 3 0 R /F2 4 0 R /F3 {mono_font} 0 R"
            objects.append(
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {WIDTH} {HEIGHT}] "
                f"/Resources << /Font << {fonts} >> >> "
                f"/Contents {6 + 2 * i} 0 R >>".encode())
            objects.append(f"<< /Length {len(content)} >>\nstream\n".encode()
                           + content + b"\nendstream")
        objects.append(_font("Courier"))

        out = b"%PDF-1.4\n"
        offsets = []
        for number, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{offset:010d} 00000 n \n".encode()
                        for offset in offsets)
        out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return out


def _write_table(doc: _Document, rows: list[str]) -> None:
    cells = [[_clean(cell.strip())
              for cell in row.strip().strip("|").split("|")]
             for row in rows]
    widths = [max(len(row[i]) for row in cells if i < len(row))
              for i in range(len(cells[0]))]
    for index, row in enumerate(cells):
        text = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        doc.line(text, size=9.5, font="F3", mono=True, spacing=1.45)
        if index == 0:
            doc.space(2)
    doc.space(6)


def markdown_to_pdf(md: str) -> bytes:
    doc = _Document()
    table: list[str] = []
    in_code = False
    for raw in md.splitlines():
        if raw.strip() == "```":
            in_code = not in_code
            continue
        if in_code:
            doc.line(raw.rstrip(), size=9, font="F3", indent=20, mono=True,
                     spacing=1.3)
            continue
        if raw.startswith("|"):
            if not re.match(r"^\|[-| ]+\|$", raw):
                table.append(raw)
            continue
        if table:
            _write_table(doc, table)
            table = []

        text = _clean(raw.rstrip())
        if text.startswith("# "):
            doc.line(text[2:], size=16, font="F2", spacing=1.4)
            doc.space(6)
        elif text.startswith("## "):
            doc.space(8)
            doc.line(text[3:], size=13, font="F2")
            doc.space(2)
        elif text.startswith("### "):
            doc.space(4)
            doc.line(text[4:], size=11, font="F2")
            doc.space(2)
        elif text == "---":
            doc.rule()
        elif text.startswith("- "):
            doc.line("-  " + text[2:], indent=8)
        elif raw.startswith("  ") and text.strip():
            # Nested lines: two spaces of Markdown indent per level
            depth = (len(raw) - len(raw.lstrip(" "))) // 2
            content = text.strip()
            if content.startswith("- "):
                content = "-  " + content[2:]
            doc.line(content, indent=8 + 12 * depth, size=9.5)
        elif not text.strip():
            doc.space(5)
        else:
            doc.line(text)
    if table:
        _write_table(doc, table)
    return doc.to_bytes()
