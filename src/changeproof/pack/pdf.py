"""A plain PDF 1.4 writer for the evidence pack's report.

Courier is one of the standard fonts every PDF reader has, so nothing is embedded, and being
monospaced it wraps exactly by character count. There are no dates or random IDs in the file: the
same blocks give the same bytes, which is what lets a pack be rebuilt and compared offline.
"""

import textwrap

PAGE_WIDTH, PAGE_HEIGHT, MARGIN = 595, 842, 56  # RENAME: A4 IN POINTS AND THE MARGIN ON EVERY SIDE
STYLES = {  # RENAME: BLOCK KIND TO (FONT, SIZE IN POINTS)
    "title": ("F2", 16), "heading": ("F2", 12), "text": ("F1", 10), "code": ("F1", 8),
}
LINE_CHARS = {kind: int((PAGE_WIDTH - 2 * MARGIN) / (size * 0.6)) for kind, (_, size) in STYLES.items()}
FOOTER_SIZE = 8


# PURPOSE: TEXT AS A PDF STRING LITERAL IN WINANSI, WITH ANYTHING OUTSIDE LATIN-1 SHOWN AS ?
def literal(text: str) -> bytes:
    raw = text.encode("latin-1", errors="replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


# PURPOSE: (FONT, SIZE, LINE) FOR EVERY PRINTED LINE, WRAPPED TO THE PAGE WIDTH
def lines_of(blocks: list[tuple[str, str]]) -> list[tuple[str, int, str]]:
    found = []
    for kind, text in blocks:
        font, size = STYLES[kind]
        if kind in ("title", "heading") and found:
            found.append((font, size, ""))
        indent = "    " if kind == "code" else ""
        for paragraph in text.split("\n"):
            wrapped = textwrap.wrap(paragraph, LINE_CHARS[kind], subsequent_indent=indent,
                                    break_on_hyphens=False, drop_whitespace=True) or [""]
            found += [(font, size, line) for line in wrapped]
    return found


# PURPOSE: SPLITS PRINTED LINES INTO PAGES BY THE HEIGHT EACH LINE TAKES
def paginate(lines: list[tuple[str, int, str]]) -> list[list[tuple[str, int, str]]]:
    pages, page, used = [], [], 0.0
    room = PAGE_HEIGHT - 2 * MARGIN
    for line in lines:
        height = line[1] * 1.3
        if page and used + height > room:
            pages.append(page)
            page, used = [], 0.0
        page.append(line)
        used += height
    return pages + [page] if page or not pages else pages


# PURPOSE: THE CONTENT STREAM THAT DRAWS ONE PAGE AND ITS FOOTER
def page_stream(lines: list[tuple[str, int, str]], number: int, total: int) -> bytes:
    out, y = [b"BT"], PAGE_HEIGHT - MARGIN
    for font, size, text in lines:
        y -= size * 1.3
        out.append(b"/%s %d Tf 1 0 0 1 %d %.1f Tm %s Tj" % (font.encode(), size, MARGIN, y, literal(text)))
    out.append(b"/F1 %d Tf 1 0 0 1 %d %d Tm %s Tj" % (FOOTER_SIZE, MARGIN, MARGIN // 2,
                                                     literal(f"page {number} of {total}")))
    out.append(b"ET")
    return b"\n".join(out)


# PURPOSE: A COMPLETE PDF FILE FOR THE BLOCKS, EACH A (KIND, TEXT) PAIR
def render(blocks: list[tuple[str, str]], title: str) -> bytes:
    pages = paginate(lines_of(blocks))
    first_page = 5  # catalog, page tree, two fonts and the info dictionary come first
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count %d /Kids [%s] >>" % (
            len(pages), b" ".join(b"%d 0 R" % (first_page + 2 * i + 1) for i in range(len(pages)))),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Title %s /Producer (changeproof) >>" % literal(title),
    ]
    for n, page in enumerate(pages, 1):
        stream = page_stream(page, n, len(pages))
        content = first_page + 2 * n
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>" % (PAGE_WIDTH, PAGE_HEIGHT, content))
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
