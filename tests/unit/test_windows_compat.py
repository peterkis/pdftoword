"""Windows 11 native compatibility guards (T0001 implementation prompt).

The project develops and ships on Windows 11 without WSL, so code must
use ``pathlib``/``tempfile`` instead of POSIX-only assumptions, and must
support Chinese file names and paths containing spaces.
"""

from __future__ import annotations

import pathlib
import tempfile

import pdf2word_core_domain

# POSIX-only locations that must never be hardcoded; temporary directories
# must come from tempfile instead.
FORBIDDEN_PATH_LITERALS = ("/tmp", "/opt", "/home")


def test_windows_paths_are_not_parsed_as_posix() -> None:
    raw = r"C:\Jobs\作业 001\input file.pdf"
    windows = pathlib.PureWindowsPath(raw)
    assert windows.drive == "C:"
    assert windows.suffix == ".pdf"
    assert windows.parts == ("C:\\", "Jobs", "作业 001", "input file.pdf")

    posix = pathlib.PurePosixPath(raw)
    # A POSIX parser understands neither drive letters nor backslashes.
    assert posix.drive == ""
    assert posix.parts == (raw,)


def test_temp_directories_come_from_tempfile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp)
        assert path.is_dir()
        assert path.exists()
    assert not path.exists()


def test_real_file_roundtrip_with_chinese_names_and_spaces() -> None:
    """Exercise the real filesystem (not just path parsing) inside a
    tempfile-managed directory: create a directory and a file whose names
    contain Chinese characters and spaces, write UTF-8 content, read it
    back and assert equality. TemporaryDirectory cleans up on exit.
    """
    content = "第 1 题：计算 12 × 34 = ?\n答案：408\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        target_dir = root / "中文 测试目录"
        target_dir.mkdir()
        assert target_dir.is_dir()
        assert target_dir.exists()

        target_file = target_dir / "数学 试卷样本.txt"
        target_file.write_text(content, encoding="utf-8")
        assert target_file.is_file()
        assert target_file.exists()

        assert target_file.read_text(encoding="utf-8") == content
    assert not root.exists()


def test_package_sources_avoid_posix_only_paths() -> None:
    package_root = pathlib.Path(pdf2word_core_domain.__file__).resolve().parent
    python_sources = sorted(package_root.rglob("*.py"))
    assert python_sources, "sanity check: package sources must exist"
    for source in python_sources:
        text = source.read_text(encoding="utf-8")
        for literal in FORBIDDEN_PATH_LITERALS:
            assert literal not in text, (
                f"{source.name} hardcodes POSIX-only path {literal!r}; "
                "use pathlib and tempfile instead"
            )
