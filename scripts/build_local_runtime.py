"""Build an offline relocatable macOS runtime from already installed, pinned dependencies."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
CORE = [
    "pypdfium2",
    "pdf-inspector",
    "python-docx",
    "lxml",
    "pillow",
    "jsonschema",
    "httpx",
    "fastapi",
    "uvicorn",
    "python-multipart",
]


def core_names() -> list[str]:
    """Resolve only installed required dependencies; extras and development tools are excluded."""
    seen: set[str] = set()

    def visit(name: str) -> None:
        d = metadata.distribution(name)
        name = d.metadata["Name"]
        if name in seen:
            return
        seen.add(name)
        for raw in d.requires or []:
            dep = Requirement(raw)
            if dep.marker is None or dep.marker.evaluate({"extra": ""}):
                visit(dep.name)

    for name in CORE:
        visit(name)
    return sorted(seen)


def distributions(python: Path, names: list[str]) -> list[dict[str, Any]]:
    """Read RECORD-listed files and license metadata from the selected interpreter."""
    program = """import importlib.metadata as m,json,sys
result=[]
for name in json.loads(sys.argv[1]):
 d=m.distribution(name)
 result.append({'name':d.metadata['Name'],'version':d.version,
 'license':d.metadata.get('License-Expression') or d.metadata.get('License'),
 'root':str(d.locate_file('')),'files':[str(p) for p in d.files or []]})
print(json.dumps(result))"""
    result: list[dict[str, Any]] = json.loads(
        subprocess.check_output([str(python), "-I", "-c", program, json.dumps(names)], text=True)
    )
    return result


def copy_distributions(target: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy dependency payloads and notices, never external bin scripts or editable .pth files."""
    target.mkdir()
    result = []
    for d in records:
        hashes = {}
        for name in d["files"]:
            rel = Path(name)
            if (
                rel.is_absolute()
                or ".." in rel.parts
                or "__pycache__" in rel.parts
                or rel.suffix == ".pyc"
            ):
                continue
            if rel.suffix == ".pth":
                raise ValueError("DEPENDENCY_PTH_REQUIRES_REVIEW")
            source = Path(d["root"]) / rel
            if not source.is_file():
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
        if not hashes:
            raise ValueError("DEPENDENCY_FILES_MISSING")
        result.append(
            {"name": d["name"], "version": d["version"], "license": d["license"], "files": hashes}
        )
    return result


def build(destination: Path) -> Path:
    """Produce a new self-contained directory and archive, refusing to overwrite any release."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("MACOS_ARM64_BUILD_ONLY")
    destination = destination.absolute()
    if destination.exists() or any(p.is_symlink() for p in [destination, *destination.parents]):
        raise ValueError("NEW_REAL_DIRECTORY_REQUIRED")
    destination.mkdir(parents=True, mode=0o700)
    shutil.copytree(
        Path(sys.base_prefix),
        destination / "python",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    app = destination / "app"
    app.mkdir()
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, text=True
    ).split("\0")
    for name in names:
        if not name:
            continue
        rel = Path(name)
        if not (
            rel.parts[0] in {"prototypes", "scripts", "specs", "config", "packages"}
            or name == "uv.lock"
        ):
            continue
        if rel.suffix not in {".py", ".json", ".yaml", ".txt", ".html", ".css", ".js", ".lock"}:
            continue
        source = ROOT / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError("SOURCE_FILE_UNSAFE")
        dest = app / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    core = copy_distributions(
        destination / "core", distributions(Path(sys.executable), core_names())
    )
    worker_python = ROOT / "tmp/docx-demo/docvortex-runtime/.venv/bin/python"
    worker_names = [
        line.split("==")[0]
        for line in (ROOT / "requirements/docvortex-poc.in").read_text().splitlines()
        if "==" in line
    ]
    worker = copy_distributions(destination / "worker", distributions(worker_python, worker_names))
    (destination / "bootstrap.py").write_text("""import os,sys,site
from pathlib import Path
base=Path(__file__).resolve().parent
site.addsitedir(str(base/'core'))
sys.path[:0]=[str(base/'app'),str(base/'app/scripts'),str(base/'app/packages/core-domain/src')]
os.environ['P2W_RUNTIME_SITE']=str(base/'core')
os.environ['P2W_DOCVORTEX_PYTHON']=str(base/'worker-python')
default_data=Path.home()/'Library/Application Support/PDF2Word/runtime'
os.environ.setdefault('P2W_PRIVATE_ROOT',str(default_data))
from prototypes.docx_output.runtime_cli import main
raise SystemExit(main())
""")
    (destination / "worker-bootstrap.py").write_text("""import sys,site,runpy
from pathlib import Path
base=Path(__file__).resolve().parent
site.addsitedir(str(base/'worker'))
args=sys.argv[1:]
if args and args[0]=='-I':args=args[1:]
sys.argv=args
runpy.run_path(args[0],run_name='__main__')
""")
    for name, script in [("pdf2word", "bootstrap.py"), ("worker-python", "worker-bootstrap.py")]:
        path = destination / name
        path.write_text(
            '#!/bin/sh\nbase=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$base/python/bin/python3" -I "$base/'  # noqa: E501
            + script
            + '" "$@"\n'
        )
        path.chmod(0o755)
    launch = destination / "Start.command"
    launch.write_text(
        '#!/bin/sh\nbase=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n"$base/pdf2word" serve --port 8765\n'  # noqa: E501
    )
    launch.chmod(0o755)
    (destination / "THIRD_PARTY_NOTICES.md").write_text(
        "# Internal runtime dependency notices\n\nPython license files are retained in python/. Package LICENSE/NOTICE/METADATA files are retained under core/ and worker/. No system fonts or Office XSLT are distributed. This is an unsigned macOS arm64 internal candidate, not a public distribution approval.\n"  # noqa: E501
    )
    (destination / "README.txt").write_text(
        "PDF2Word 本地运行候选\n将整个目录复制到本机任意可读目录；不要仅复制启动脚本。\n运行 ./pdf2word serve，在浏览器打开 http://127.0.0.1:8765 。关闭终端前按 Ctrl-C。\n数据默认保存在 ~/Library/Application Support/PDF2Word/runtime；可用 P2W_PRIVATE_ROOT 指定新的绝对路径。\nCLI: ./pdf2word convert --input FILE.pdf --pages 1\n离线导出: ./pdf2word reexport --source-job SAVED_JOB --revision auto\n只支持 native 和保存结果离线导出；每次最多3页，输入25MiB。表格保图、布局受限。没有新扫描识别能力。\n队列重启保留；已运行但无完成收据的任务不自动重发，必须显式重试。取消保留文件。\n无需uv、pip、源码checkout、模型权重或开发工具。未公证、未测试Windows。请不要删除数据目录中的自动结果和人工稿。\n"  # noqa: E501
    )
    manifest = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "core": core,
        "worker": worker,
        "default_profile": "fidelity-v3.1",
        "live_models": False,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    archive = destination.with_suffix(".tar.gz")
    if archive.exists():
        raise ValueError("ARCHIVE_ALREADY_EXISTS")
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(destination, arcname=destination.name)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
