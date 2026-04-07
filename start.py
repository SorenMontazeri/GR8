import os
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_PYTHON = os.path.join(ROOT, "backend", "venv", "bin", "python")


def main():
    processes = []

    backend = subprocess.Popen(
        [BACKEND_PYTHON, "database.py"],
        cwd=os.path.join(ROOT, "backend", "database"),
    )
    processes.append(backend)
    print(f"Started backend with pid {backend.pid}")

    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=os.path.join(ROOT, "frontend"),
    )
    processes.append(frontend)
    print(f"Started frontend with pid {frontend.pid}")

    try:
        while True:
            for process in processes:
                if process.poll() is not None:
                    return
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()

        for process in processes:
            if process.poll() is None:
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
