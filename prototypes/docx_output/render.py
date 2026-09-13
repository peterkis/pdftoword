"""Optional real LibreOffice rendering, followed by serialized PDFium page images."""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import DemoError, Json, private_dir, read, save, secure_tree
from .native_pdf import PDFIUM_LOCK


def render(job: Path, revision: str = "auto") -> Json:
    """Run an actual local renderer with an isolated profile and bounded timeout."""
    if revision not in {"auto", "reviewed"}:
        raise DemoError("INVALID_REVISION")
    source = job / f"{revision}.docx"
    if not source.is_file():
        raise DemoError("DOCX_NOT_FOUND")
    qa_path = job / ("qa.json" if revision == "auto" else "qa.reviewed.json")
    qa = read(qa_path)
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        installed = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        executable = str(installed) if installed.is_file() else None
    if not executable:
        qa.update(
            render_status="DOCX_VISUAL_REVIEW_PENDING",
            renderer=None,
            renderer_reason="No local LibreOffice/soffice found",
        )
        save(qa_path, qa)
        return qa
    out = job / "rendered" / revision
    private_dir(out)
    attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=out))
    try:
        # The bundled headless build uses fontconfig. Point it at existing macOS
        # font directories; no font bytes are copied, downloaded or distributed.
        env = dict(os.environ)
        if Path("/System/Library/Fonts").is_dir():
            config = job / "fontconfig.xml"
            directories = [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library/Fonts",
            ]
            config.write_text(
                '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                + "<fontconfig>"
                + "".join(
                    "<dir>" + html.escape(str(d)) + "</dir>" for d in directories if d.is_dir()
                )
                + "<cachedir>"
                + html.escape(str(job / "font-cache"))
                + "</cachedir></fontconfig>",
                encoding="utf-8",
            )
            config.chmod(0o600)
            env["FONTCONFIG_FILE"] = str(config)
        version = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=30, check=True
        ).stdout.strip()
        with tempfile.TemporaryDirectory(prefix="lo-profile-", dir=job) as profile:
            result = subprocess.run(
                [
                    executable,
                    "-env:UserInstallation=" + Path(profile).as_uri(),
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(attempt),
                    str(source),
                ],
                capture_output=True,
                env=env,
                text=True,
                timeout=90,
                check=False,
            )
        pdf = attempt / f"{revision}.pdf"
        if result.returncode or not pdf.is_file() or not pdf.stat().st_size:
            raise DemoError("RENDERER_FAILED")
        with PDFIUM_LOCK:
            document = pdfium.PdfDocument(pdf)
            try:
                page_count = len(document)
                for index in range(page_count):
                    p = document[index]
                    bitmap = None
                    try:
                        bitmap = p.render(scale=min(2, 4000 / max(p.get_size())))
                        im = bitmap.to_pil()
                        im.save(attempt / f"page-{index + 1}.png")
                        im.close()
                    finally:
                        if bitmap is not None:
                            bitmap.close()
                        p.close()
            finally:
                document.close()
        for asset in attempt.iterdir():
            shutil.copyfile(asset, out / asset.name)
        current_pages = {f"page-{n}.png" for n in range(1, page_count + 1)}
        for previous_page in out.glob("page-*.png"):
            if previous_page.name not in current_pages:
                previous_page.unlink()
        shutil.rmtree(attempt)
        qa.update(
            render_status="RENDERED",
            renderer="LibreOffice",
            renderer_version=version,
            rendered_page_count=page_count,
            visual_review_status="PENDING",
        )
    except (subprocess.SubprocessError, OSError, DemoError) as exc:
        qa.update(
            render_status="DOCX_VISUAL_REVIEW_PENDING",
            renderer="LibreOffice",
            renderer_reason=type(exc).__name__,
        )
    save(qa_path, qa)
    secure_tree(job)
    return qa
