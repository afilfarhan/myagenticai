"""
Run the W&B Weave evaluation suite against the golden set.

Usage (from backend/ with the full requirements installed):
    python ../scripts/run_evals.py

Requires WANDB_API_KEY / weave configuration in backend/config.yaml.
"""
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import os  # noqa: E402

os.chdir(BACKEND_DIR)


def main() -> int:
    try:
        from app.evaluation.runner import run_evaluation_suite
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nInstall backend requirements first.")
        return 1

    summary = asyncio.run(run_evaluation_suite())
    print("Evaluation summary:", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
