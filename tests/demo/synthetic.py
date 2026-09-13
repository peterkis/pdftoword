"""Self-owned native PDF fixture: bilingual text and a single vector composite."""

from pathlib import Path


def make_pdf(path: Path, *, rotation: int = 0, pages: int = 1, decoration: bytes = b"") -> str:
    """Write a tiny standards-based PDF without importing a second PDF engine."""
    lines = [
        "原生 PDF 测试 Native PDF",
        "1. 比较 3 < 5，保留符号。",
        "A. 中文 English  B. 2026 年",
        "2. 观察图形并记录结果。",
    ]
    stream = b""
    for i, text in enumerate(lines):
        size = 18 if i == 0 else 12
        encoded = text.encode("utf-16-be").hex()
        stream += f"BT /F1 {size} Tf 60 {740 - i * 38} Td <{encoded}> Tj ET\n".encode()
    stream += b"0.2 0.5 0.6 RG 2 w 70 470 140 70 re S 70 470 m 210 540 l S\n"
    stream += decoration
    cmap = (
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def "
        b"/CMapName /Adobe-Identity-UCS def /CMapType 2 def "
        b"1 begincodespacerange <0000> <FFFF> endcodespacerange "
        b"1 beginbfrange <0000> <FFFF> <0000> endbfrange endcmap "
        b"CMapName currentdict /CMap defineresource pop end end"
    )
    kids = " ".join(f"{8 + i} 0 R" for i in range(pages))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H "
        b"/DescendantFonts [4 0 R] /ToUnicode 7 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> "
        b"/FontDescriptor 5 0 R /DW 1000 >>",
        b"<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 "
        b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 "
        b"/CapHeight 700 /StemV 80 >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Length " + str(len(cmap)).encode() + b" >>\nstream\n" + cmap + b"\nendstream",
    ]
    for _ in range(pages):
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Rotate {rotation} "
            "/Resources << /Font << /F1 3 0 R >> >> /Contents 6 0 R >>".encode()
        )
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objs, 1):
        offsets.append(len(data))
        data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    path.write_bytes(data)
    path.chmod(0o600)
    return "\n".join(lines)
