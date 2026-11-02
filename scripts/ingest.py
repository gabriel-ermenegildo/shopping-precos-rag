#!/usr/bin/env python
"""Ingestão da documentação: crawl + ETL + indexação.

Uso:
    python scripts/ingest.py            # incremental (usa manifest)
    python scripts/ingest.py --full     # reindexa tudo do zero
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings           # noqa: E402
from app.container import get_pipeline, refresh_after_ingest  # noqa: E402
from app.observability.logging import setup_logging    # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestão da documentação do Shopping de Preços")
    parser.add_argument("--full", action="store_true", help="reindexa tudo (ignora manifest)")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    stats = get_pipeline().run(full=args.full)
    refresh_after_ingest()
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
