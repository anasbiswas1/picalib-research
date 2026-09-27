"""Single commit step for this repo. Run from a notebook's final cell only:

    subprocess.run(["python", "tools/commit_cell.py", "message"])

Restores git identity and credentials from the Drive project folder, strips all notebook outputs,
refuses to stage data or credential files, commits if anything is staged, and always pushes so
that unpushed commits never remain local.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from glob import glob
from pathlib import Path

DRIVE_PROJECT_ROOT = Path("/content/drive/MyDrive/PICALIB_Research")
REPO_ROOT = Path(os.environ.get("PICALIB_REPO_ROOT", str(DRIVE_PROJECT_ROOT / "picalib-research")))
GIT_NAME = "Md Anas Biswas"
GIT_EMAIL = "anasbiswas@gmail.com"
FORBIDDEN_NAMES = {".git-credentials", ".gitconfig", "kaggle.json", ".env"}
FORBIDDEN_PREFIXES = ("data/", "_bipia/", ".secrets/")
MAX_FILE_MB = 50


def run(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"{' '.join(args)}\n{r.stdout}{r.stderr}")
    return r.stdout


def strip_outputs():
    notebooks = sorted(glob(str(REPO_ROOT / "notebooks" / "*.ipynb")))
    for notebook in notebooks:
        r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert",
                            "--ClearOutputPreprocessor.enabled=True", "--inplace", notebook],
                           capture_output=True, text=True)
        if r.returncode != 0:
            import nbformat
            nb = nbformat.read(notebook, as_version=4)
            for cell in nb.cells:
                if cell.cell_type == "code":
                    cell["outputs"] = []; cell["execution_count"] = None
            nbformat.write(nb, notebook)
    import nbformat
    for notebook in notebooks:
        nb = nbformat.read(notebook, as_version=4)
        if "widgets" in nb.metadata:
            del nb.metadata["widgets"]; nbformat.write(nb, notebook)
    print(f"outputs: stripped {len(notebooks)} notebook(s)")


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        raise SystemExit('usage: python tools/commit_cell.py "commit message"')
    message = sys.argv[1].strip()

    for dotfile in (".gitconfig", ".git-credentials"):
        source = DRIVE_PROJECT_ROOT / dotfile
        if source.exists():
            shutil.copy(source, Path.home() / dotfile)
    credentials = Path.home() / ".git-credentials"
    if credentials.exists():
        os.chmod(credentials, 0o600)

    os.chdir(REPO_ROOT)
    run(["git", "config", "user.name", GIT_NAME])
    run(["git", "config", "user.email", GIT_EMAIL])
    run(["git", "config", "credential.helper", "store"])

    strip_outputs()

    run(["git", "add", "-A"])
    staged = [l for l in run(["git", "diff", "--cached", "--name-only"]).splitlines() if l.strip()]
    bad = [p for p in staged if Path(p).name in FORBIDDEN_NAMES or p.startswith(FORBIDDEN_PREFIXES)]
    big = [p for p in staged if Path(p).exists() and Path(p).stat().st_size > MAX_FILE_MB * 1024 * 1024]
    if bad or big:
        run(["git", "reset", "-q"], check=False)
        raise SystemExit(f"refused: forbidden={bad} oversized={big}")

    if staged:
        commit = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        print(commit.stdout or commit.stderr)
    else:
        print("nothing new to commit; pushing any unpushed commits")

    push = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    print(push.stdout or push.stderr)
    print(run(["git", "log", "--oneline", "-1"]).strip())
    print(run(["git", "status", "--short"]).strip() or "working tree clean")


if __name__ == "__main__":
    main()
