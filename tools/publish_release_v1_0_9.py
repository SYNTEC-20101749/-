from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAG = "v1.0.9"
RELEASE_FILES = [
    ".vscode/tasks.json",
    "build_release_v1_0_8.ps1",
    "build_release_v1_0_9.ps1",
    "desktop_app.py",
    "docs/发票管理系统操作说明书-v1.0.9.docx",
    "docs/发票管理系统操作教学视频-v1.0.7.mp4",
    "invoice_desktop/main.py",
    "invoice_desktop/main.spec",
    "main.spec",
    "publish_v1_0_9.ps1",
    "python_recognizer/heuristics.py",
    "python_recognizer/pairing.py",
    "python_recognizer/workflow.py",
    "tools/generate_tutorial_video.py",
    "tools/generate_user_manual.py",
    "tools/publish_release_v1_0_9.py",
    "ui_config.txt",
    "version_info.txt",
]


def run_git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main() -> None:
    run_git("add", "--", *RELEASE_FILES)

    staged_files = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    staged_files = [path for path in staged_files if path]
    unexpected_files = sorted(set(staged_files) - set(RELEASE_FILES))
    if unexpected_files:
        raise RuntimeError(f"Unexpected staged files: {unexpected_files}")

    run_git("commit", "-m", "Release v1.0.9: configurable reimbursement reminder blinking")
    run_git("push", "origin", "HEAD")
    subprocess.run(["git", "tag", "-d", TAG], cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", f":refs/tags/{TAG}"], cwd=ROOT, check=False)
    run_git("tag", "-a", TAG, "-m", "Release v1.0.9")
    run_git("push", "origin", TAG)


if __name__ == "__main__":
    main()
