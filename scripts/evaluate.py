#!/usr/bin/env python
"""Avaliação RAGAS / smoke test do golden dataset.

Uso:
    python scripts/evaluate.py              # tenta RAGAS; cai para smoke test
    python scripts/evaluate.py --no-ragas   # apenas smoke test (sem deps pesadas)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings        # noqa: E402
from app.container import refresh_after_ingest       # noqa: E402
from app.evaluation.ragas_eval import run_evaluation  # noqa: E402
from app.observability.logging import setup_logging   # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ragas", action="store_true")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    refresh_after_ingest()
    report = run_evaluation(use_ragas=not args.no_ragas)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
