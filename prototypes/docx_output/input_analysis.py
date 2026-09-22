"""Read-only PDF evidence: inspector owns text; PDFium owns geometry and rendering."""

from __future__ import annotations

import ctypes
import itertools
import math
import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

import pdf_inspector
import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import DemoError, Json, box_valid, digest, validate_input
from .native_glyphs import bind_runs, read_glyphs

PDFIUM_LOCK = threading.RLock()


@dataclass(frozen=True)
class PageGeometry:
    """Continuous PDF canvas to visible, rotated, top-left point coordinates."""

    visible_box: tuple[float, float, float, float]
    rotation: int
    media_box: tuple[float, ...] | None = None
    crop_box: tuple[float, ...] | None = None

    @property
    def width(self) -> float:
        """Visible rotated width in points."""
        left, b, r, t = self.visible_box
        return t - b if self.rotation in (90, 270) else r - left

    @property
    def height(self) -> float:
        """Visible rotated height in points."""
        left, b, r, t = self.visible_box
        return r - left if self.rotation in (90, 270) else t - b

    def to_point(self, x: float, y: float) -> tuple[float, float]:
        """Map an unrotated PDF point without pixel rounding."""
        left, b, r, t = self.visible_box
        return {
            0: (x - left, t - y),
            90: (y - b, x - left),
            180: (r - x, y - b),
            270: (t - y, r - x),
        }[self.rotation]

    def to_pdf(self, x: float, y: float) -> tuple[float, float]:
        """Invert the continuous visible-page transform."""
        left, b, r, t = self.visible_box
        return {
            0: (left + x, t - y),
            90: (left + y, b + x),
            180: (r - x, b + y),
            270: (r - y, t - x),
        }[self.rotation]

    def quad(self, raw: list[float]) -> list[list[float]]:
        """Transform all four corners of a PDF-space rectangle."""
        left, b, r, t = raw
        return [list(self.to_point(x, y)) for x, y in ((left, b), (r, b), (r, t), (left, t))]

    def record(self) -> Json:
        """Serialize geometry, keeping absent raw boxes distinct from effective boxes."""
        return {
            **asdict(self),
            "width_pt": self.width,
            "height_pt": self.height,
            "box_basis": "PDFium_effective_intersection",
            "raw_box_inheritance": "unknown_when_absent",
            "pdf_to_point_basis": [self.to_point(0, 0), self.to_point(1, 0), self.to_point(0, 1)],
        }


def envelope(points: list[list[float]]) -> list[float]:
    """Enclose transformed corners without pretending this measures ink coverage."""
    return [
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    ]


def open_pdf(source: Path) -> Any:
    """Open a PDF with distinct safe password/format diagnostics; caller owns lock."""
    try:
        doc = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as exc:
        codes = {
            2: "PDF_FILE_ERROR",
            3: "PDF_FORMAT_ERROR",
            4: "PDF_PASSWORD_REQUIRED",
            5: "PDF_SECURITY_UNSUPPORTED",
            6: "PDF_PAGE_ERROR",
        }
        raise DemoError(codes.get(exc.err_code, "PDF_OPEN_FAILED")) from exc
    if pdfium.raw.FPDF_GetSecurityHandlerRevision(doc) >= 0:
        doc.close()
        raise DemoError("PDF_SECURITY_UNSUPPORTED")
    return doc


def geometry_of(native: Any) -> PageGeometry:
    """Read effective geometry without modifying boxes or rotation."""
    visible = tuple(float(v) for v in native.get_bbox())
    if len(visible) != 4 or not box_valid(visible):
        raise DemoError("INVALID_PAGE_SIZE")
    g = PageGeometry(
        visible, native.get_rotation(), native.get_mediabox(False), native.get_cropbox(False)
    )
    if not math.isfinite(g.width + g.height) or min(g.width, g.height) <= 0:
        raise DemoError("INVALID_PAGE_SIZE")
    return g


@dataclass(frozen=True)
class DocumentInspection:
    """Immutable preflight facts, without a conversion job or model calls."""

    sha256: str
    page_count: int
    pages: tuple[PageGeometry, ...]
    status: str = "OK"


def inspect_document(source: Path) -> DocumentInspection:
    """Inspect an input read-only and release all PDFium resources even on failure."""
    validate_input(source)
    with PDFIUM_LOCK, ExitStack() as stack:
        doc = open_pdf(source)
        stack.callback(doc.close)
        if not len(doc):
            raise DemoError("PDF_EMPTY_DOCUMENT")
        pages = []
        for index in range(len(doc)):
            with ExitStack() as page_stack:
                native = doc[index]
                page_stack.callback(native.close)
                pages.append(geometry_of(native))
        return DocumentInspection(digest(source), len(doc), tuple(pages))


class NativeTextBackend(Protocol):
    """Replaceable native-only backend; no OCR or network interface is exposed."""

    def extract(self, source: Path) -> Json:
        """Return plain observations and backend classification evidence."""
        ...


class PdfInspectorBackend:
    """Adapter for pinned pdf-inspector 1.20.0, never its optional OCR path."""

    def extract(self, source: Path) -> Json:
        """Keep run precision, indexing and synthetic rotation frames explicit."""
        try:
            result = pdf_inspector.detect_pdf(str(source))
            positioned = pdf_inspector.extract_text_with_positions_and_rotations(str(source))
            frames = {r.page - 1: r.rotation for r in positioned.page_rotations}
            items = []
            for index, item in enumerate(positioned.items):
                if item.item_type != "text":
                    continue
                items.append(
                    {
                        "id": f"inspector-{index}",
                        "page_index": item.page - 1,
                        "text": item.text,
                        "x": item.x,
                        "y": item.y,
                        "width": item.width,
                        "height": item.height,
                        "font_size": item.font_size,
                        "font": item.font,
                        "bold": item.is_bold,
                        "italic": item.is_italic,
                        "underline": item.is_underline,
                        "baseline_shift": item.baseline_shift,
                        "rotation": item.rotation,
                        "advance_known": item.advance_known,
                        "frame_rotation": frames.get(item.page - 1),
                        "geometry_precision": "run_estimate",
                        "visibility": "unknown",
                    }
                )
            return {
                "backend": "pdf-inspector",
                "version": version("pdf-inspector"),
                "status": "OK",
                "items": items,
                "classification": {
                    "pdf_type": result.pdf_type,
                    "backend_score": result.confidence,
                    "has_encoding_issues": result.has_encoding_issues,
                    "pages_needing_ocr": result.pages_needing_ocr,
                },
            }
        except (ValueError, RuntimeError, OSError) as exc:
            return {
                "backend": "pdf-inspector",
                "version": version("pdf-inspector"),
                "status": "NATIVE_EXTRACTION_FAILED",
                "items": [],
                "classification": {},
                "error_type": type(exc).__name__,
            }


@dataclass(frozen=True)
class NativeObservation:
    """Detached page observations, safe after every native handle has closed."""

    geometry: PageGeometry
    text_runs: tuple[Json, ...]
    objects: tuple[Json, ...]
    backend: Json
    glyph_evidence: Json | None = None

    def record(self) -> Json:
        """Return a versioned private observation sidecar."""
        return {
            "schema_version": "native-observation/1",
            "geometry": self.geometry.record(),
            "text_runs": list(self.text_runs),
            "objects": list(self.objects),
            "backend": self.backend,
            **({"glyph_evidence": self.glyph_evidence} if self.glyph_evidence is not None else {}),
        }


def object_evidence(native: Any) -> Iterator[tuple[Any, tuple[float, ...], int]]:
    """Walk form ancestry, carrying each parent's affine matrix to page space."""
    identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def walk(
        form: Any, parent: tuple[float, ...], depth: int
    ) -> Iterator[tuple[Any, tuple[float, ...], int]]:
        for obj in native.get_objects(max_depth=1, form=form):
            yield obj, parent, depth
            if obj.type == pdfium.raw.FPDF_PAGEOBJ_FORM:
                if depth >= 14:
                    raise DemoError("PDF_OBJECT_DEPTH_LIMIT")
                a, b, c, d, e, f = parent
                aa, bb, cc, dd, ee, ff = obj.get_matrix().get()
                combined = (
                    a * aa + c * bb,
                    b * aa + d * bb,
                    a * cc + c * dd,
                    b * cc + d * dd,
                    a * ee + c * ff + e,
                    b * ee + d * ff + f,
                )
                yield from walk(obj, combined, depth + 1)

    yield from walk(None, identity, 0)


def _stroke_width_pt(
    obj: Any, to_page: Callable[[float, float], tuple[float, float]]
) -> float | None:
    """Expose stroke radius only for similarity transforms, never guess anisotropic ink."""
    width = ctypes.c_float()
    if not pdfium.raw.FPDFPageObj_GetStrokeWidth(obj, width):
        return None
    a, b, c, d, e, f = obj.get_matrix().get()
    origin = to_page(e, f)
    px, py = to_page(a + e, b + f), to_page(c + e, d + f)
    vx = (px[0] - origin[0], px[1] - origin[1])
    vy = (py[0] - origin[0], py[1] - origin[1])
    sx, sy = math.hypot(*vx), math.hypot(*vy)
    if min(sx, sy) <= 0 or abs(sx - sy) > 1e-5 or abs(vx[0] * vy[0] + vx[1] * vy[1]) > 1e-5:
        return None
    return float(width.value * sx)


def observe_page(native: Any, index: int, extracted: Json) -> NativeObservation:
    """Detach object and text evidence; called with the PDFium mutex held."""
    g = geometry_of(native)
    objects = []
    object_refs: dict[int, Json] = {}
    for oi, (obj, ancestor, depth) in enumerate(object_evidence(native)):
        raw = list(obj.get_bounds())

        def to_page(
            x: float, y: float, ancestor: tuple[float, ...] = ancestor
        ) -> tuple[float, float]:
            a, b, c, d, e, f = ancestor
            return g.to_point(a * x + c * y + e, b * x + d * y + f)

        x0, y0, x1, y1 = raw
        points = [list(to_page(x, y)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        certainty = "object_envelope"
        if obj.type in (pdfium.raw.FPDF_PAGEOBJ_IMAGE, pdfium.raw.FPDF_PAGEOBJ_TEXT):
            try:
                points = [list(to_page(x, y)) for x, y in obj.get_quad_points()]
            except pdfium.PdfiumError:
                certainty = "unknown_quad"
        row: Json = {
            "id": f"p{index}-obj{oi}",
            "paint_order": oi,
            "type": obj.type,
            "raw_bbox_pdf": raw,
            "quad_pt": points,
            "bbox": envelope(points),
            "geometry_precision": certainty,
            "level": depth,
            "ancestor_matrix": ancestor,
            "matrix": list(obj.get_matrix().get()),
            "clip": "unknown",
            "visibility": "unknown",
        }
        # Only two-point, solid, stroked paths can witness a ruled-grid edge.
        # Curves, fills and dashed paths remain envelope-only evidence.
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_PATH:
            fill, stroke = ctypes.c_int(), ctypes.c_int()
            red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
            if (
                pdfium.raw.FPDFPath_CountSegments(obj) == 2
                and pdfium.raw.FPDFPath_GetDrawMode(obj, fill, stroke)
                and fill.value == 0
                and stroke.value
                and pdfium.raw.FPDFPageObj_GetDashCount(obj) == 0
                and pdfium.raw.FPDFPageObj_GetStrokeColor(obj, red, green, blue, alpha)
                and alpha.value == 255
                and (
                    min(red.value, green.value, blue.value) < 245
                    or red.value == green.value == blue.value == 255
                )
            ):
                segments = [pdfium.raw.FPDFPath_GetPathSegment(obj, i) for i in range(2)]
                if [pdfium.raw.FPDFPathSegment_GetType(s) for s in segments] == [2, 0]:
                    a, b, c, d, e, f = obj.get_matrix().get()
                    line = []
                    for segment in segments:
                        sx, sy = ctypes.c_float(), ctypes.c_float()
                        if not pdfium.raw.FPDFPathSegment_GetPoint(segment, sx, sy):
                            break
                        line.append(
                            list(
                                to_page(
                                    a * sx.value + c * sy.value + e,
                                    b * sx.value + d * sy.value + f,
                                )
                            )
                        )
                    if len(line) == 2:
                        if (stroke_size := _stroke_width_pt(obj, to_page)) is not None:
                            row["stroke_width_pt"] = stroke_size
                        row["stroke_rgba"] = [red.value, green.value, blue.value, alpha.value]
                        row["line_cap"] = pdfium.raw.FPDFPageObj_GetLineCap(obj)
                        if red.value == green.value == blue.value == 255:
                            row["white_line"] = line
                        else:
                            row["solid_line"] = line
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_PATH:
            fill, stroke = ctypes.c_int(), ctypes.c_int()
            rgba = [ctypes.c_uint() for _ in range(4)]
            if (
                pdfium.raw.FPDFPath_CountSegments(obj) == 5
                and pdfium.raw.FPDFPath_GetDrawMode(obj, fill, stroke)
                and (
                    (
                        fill.value in (1, 2)
                        and not stroke.value
                        and pdfium.raw.FPDFPageObj_GetFillColor(obj, *rgba)
                    )
                    or (
                        fill.value == 0
                        and stroke.value
                        and pdfium.raw.FPDFPageObj_GetDashCount(obj) == 0
                        and pdfium.raw.FPDFPageObj_GetStrokeColor(obj, *rgba)
                        and min(v.value for v in rgba[:3]) < 245
                    )
                )
                and rgba[3].value == 255
            ):
                segments = [pdfium.raw.FPDFPath_GetPathSegment(obj, i) for i in range(5)]
                if [pdfium.raw.FPDFPathSegment_GetType(s) for s in segments] == [
                    2,
                    0,
                    0,
                    0,
                    0,
                ] and pdfium.raw.FPDFPathSegment_GetClose(segments[-1]):
                    a, b, c, d, e, f = obj.get_matrix().get()
                    vertices = []
                    for segment in segments:
                        sx, sy = ctypes.c_float(), ctypes.c_float()
                        if not pdfium.raw.FPDFPathSegment_GetPoint(segment, sx, sy):
                            break
                        vertices.append(
                            list(
                                to_page(
                                    a * sx.value + c * sy.value + e, b * sx.value + d * sy.value + f
                                )
                            )
                        )
                    if len(vertices) == 5 and vertices[0] == vertices[-1]:
                        rect = envelope(vertices)
                        corners = {
                            (rect[0], rect[1]),
                            (rect[2], rect[1]),
                            (rect[2], rect[3]),
                            (rect[0], rect[3]),
                        }
                        if (
                            box_valid(rect)
                            and {tuple(p) for p in vertices[:4]} == corners
                            and all(
                                a[0] == b[0] or a[1] == b[1]
                                for a, b in itertools.pairwise(vertices)
                            )
                        ):
                            if not stroke.value:
                                row.update(fill_rect=rect, fill_rgba=[v.value for v in rgba])
                            else:
                                if (stroke_size := _stroke_width_pt(obj, to_page)) is not None:
                                    row["stroke_width_pt"] = stroke_size
                                row.update(stroke_rect=rect, stroke_rgba=[v.value for v in rgba])
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT:
            mode = pdfium.raw.FPDFTextObj_GetTextRenderMode(obj)
            red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
            ok = pdfium.raw.FPDFPageObj_GetFillColor(obj, red, green, blue, alpha)
            row.update(
                render_mode=mode,
                fill_rgba=[red.value, green.value, blue.value, alpha.value] if ok else None,
            )
            if mode == 3 or (mode in (0, 4) and ok and alpha.value == 0):
                row["visibility"] = "invisible"
            elif (
                mode in (0, 4)
                and ok
                and alpha.value == 255
                and min(red.value, green.value, blue.value) < 245
            ):
                row["visibility"] = "painted"  # Occlusion remains unknown.
            elif mode in (0, 4) and ok and min(red.value, green.value, blue.value) >= 245:
                row["visibility"] = "white_paint"
        object_refs[ctypes.cast(obj.raw, ctypes.c_void_p).value or 0] = row
        objects.append(row)
    runs = []
    left, b, _, _ = g.visible_box
    for item in extracted["items"]:
        if item["page_index"] != index:
            continue
        run = dict(item)
        x, y, width, height = (item[k] for k in ("x", "y", "width", "height"))
        if item["frame_rotation"] == "ccw":
            x, y, width, height = -y - height, x, height, width
        elif item["frame_rotation"] == "cw":
            x, y, width, height = y, -x - width, height, width
        raw = [left + x, b + y, left + x + width, b + y + height]
        run["geometry_verified"] = bool(item["advance_known"])
        run["raw_bbox_pdf"] = raw
        run["quad_pt"] = g.quad(raw)
        run["bbox"] = envelope(run["quad_pt"])
        run["geometry_verified"] &= box_valid(run["bbox"]) and (
            0 <= run["bbox"][0] < run["bbox"][2] <= g.width + 1
            and 0 <= run["bbox"][1] < run["bbox"][3] <= g.height + 1
        )
        runs.append(run)
    glyphs = read_glyphs(native, g, object_refs)
    return NativeObservation(
        g,
        tuple(runs),
        tuple(objects),
        {k: v for k, v in extracted.items() if k != "items"},
        {
            "basis": "pdfium_tight_glyph_exact_nonspace_binding",
            "glyphs": glyphs,
            "runs": bind_runs(runs, glyphs),
        },
    )


def inspect_page(source: Path, page_index: int) -> NativeObservation:
    """Read one page without rendering or persisting sensitive text."""
    validate_input(source)
    extracted = PdfInspectorBackend().extract(source)
    with PDFIUM_LOCK, ExitStack() as stack:
        doc = open_pdf(source)
        stack.callback(doc.close)
        if not 0 <= page_index < len(doc):
            raise DemoError("PAGE_OUT_OF_RANGE")
        native = doc[page_index]
        stack.callback(native.close)
        return observe_page(native, page_index, extracted)
