from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = BACKEND_DIR / "venv"
MODEL_DIR = BACKEND_DIR / "database" / "models" / "all-MiniLM-L6-v2"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def run(command: list[str], cwd: Path | None = None) -> None:
    print(f"Running: {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_pip() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def ensure_venv() -> None:
    if VENV_DIR.exists():
        print(f"Virtual environment already exists: {VENV_DIR}")
        return

    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def install_backend_packages() -> None:
    pip_path = venv_pip()
    run([str(pip_path), "install", "--upgrade", "pip"])
    run([str(pip_path), "install", "-r", str(BACKEND_DIR / "requirements.txt")])


def download_model() -> None:
    if MODEL_DIR.exists():
        print(f"Model already exists: {MODEL_DIR}")
        return

    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)

    script = (
        "from sentence_transformers import SentenceTransformer; "
        f'model = SentenceTransformer("{MODEL_NAME}"); '
        f'model.save(r"{MODEL_DIR}")'
    )
    run([str(venv_python()), "-c", script], cwd=ROOT)


def install_frontend_packages() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is not installed or not found in PATH")

    run([npm, "install"], cwd=FRONTEND_DIR)


def main() -> None:
    ensure_venv()
    install_backend_packages()
    download_model()
    install_frontend_packages()
    print("Init complete.")


if __name__ == "__main__":
    main()
