#!/usr/bin/env python
"""Pergunta rápida pela linha de comando (sem subir a API).

Uso:
    python scripts/ask.py "Como autenticar na API?"
    python scripts/ask.py --mode agent "Como enviar um produto e atualizar o estoque?"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings        # noqa: E402
from app.container import get_chain, refresh_after_ingest  # noqa: E402
from app.observability.logging import setup_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", help="pergunta em linguagem natural")
    parser.add_argument("--mode", choices=["chat", "agent"], default="chat")
    parser.add_argument("--session", default="cli")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    refresh_after_ingest()  # garante BM25 carregado do banco persistente
    res = get_chain().answer(args.question, session_id=args.session, mode=args.mode)
    print(res.answer)
    print(f"\n[confiança: {res.confidence} | latência: {res.latency_ms} ms]")


if __name__ == "__main__":
    main()
