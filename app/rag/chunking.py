"""Chunking semântico (RF03).

Princípios:
  * Blocos de código (```...```) são ATÔMICOS — nunca divididos. É neles que
    moram payloads, exemplos cURL e respostas JSON; cortar no meio destrói o RAG.
  * Headings definem seções; cada chunk recebe um "breadcrumb" do caminho de
    títulos ("Contexto: Doc > Seção"), o que melhora muito o recall.
  * chunk_size e chunk_overlap são configuráveis (presets: 300/500/800/1000 e
    50/100/150 tokens).

Contagem de tokens: tiktoken (cl100k_base) se disponível; senão heurística
~4 chars/token — suficiente para empacotamento.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

try:  # opcional
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:  # pragma: no cover - fallback sem tiktoken

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)


_FENCE_RE = re.compile(r"^```")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


@dataclass
class _Block:
    kind: str  # "heading" | "code" | "text"
    text: str
    level: int = 0  # só para headings


def split_blocks(markdown: str) -> list[_Block]:
    """Markdown -> blocos (heading | código cercado | parágrafo)."""
    blocks: list[_Block] = []
    code_lines: list[str] = []
    para_lines: list[str] = []
    in_code = False

    def flush_para():
        text = "\n".join(para_lines).strip()
        if text:
            blocks.append(_Block("text", text))
        para_lines.clear()

    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            if in_code:
                code_lines.append(line)
                blocks.append(_Block("code", "\n".join(code_lines)))
                code_lines.clear()
                in_code = False
            else:
                flush_para()
                in_code = True
                code_lines.append(line)
            continue
        if in_code:
            code_lines.append(line)
            continue
        m = _HEADING_RE.match(line)
        if m:
            flush_para()
            blocks.append(_Block("heading", m.group(2).strip(), level=len(m.group(1))))
            continue
        if not line.strip():
            flush_para()
        else:
            para_lines.append(line)

    if in_code and code_lines:  # cerca não fechada — preserva mesmo assim
        blocks.append(_Block("code", "\n".join(code_lines) + "\n```"))
    flush_para()
    return blocks


class SemanticChunker:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap deve ser menor que chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------ api
    def chunk(self, markdown: str, base_metadata: dict) -> list[Chunk]:
        blocks = split_blocks(markdown)
        title = base_metadata.get("title", "")

        chunks: list[Chunk] = []
        current: list[_Block] = []
        current_tokens = 0
        breadcrumb: dict[int, str] = {}

        def crumb() -> str:
            path = [title] + [breadcrumb[k] for k in sorted(breadcrumb)]
            return " > ".join(p for p in path if p)

        def emit():
            nonlocal current, current_tokens
            body = "\n\n".join(b.text if b.kind != "heading"
                               else "#" * max(1, b.level) + " " + b.text
                               for b in current).strip()
            if not body:
                current, current_tokens = [], 0
                return
            prefix = f"[Contexto: {crumb()}]\n\n" if crumb() else ""
            text = prefix + body
            meta = dict(base_metadata)
            meta["section_path"] = crumb()
            meta["chunk_index"] = len(chunks)
            cid = hashlib.sha1(
                f"{meta.get('url','')}::{len(chunks)}::{meta.get('content_hash','')[:12]}".encode()
            ).hexdigest()
            chunks.append(Chunk(id=cid, text=text, metadata=meta))
            # overlap: carrega blocos finais (nunca código maior que o overlap)
            tail: list[_Block] = []
            tokens = 0
            for b in reversed(current):
                bt = count_tokens(b.text)
                if b.kind == "code" or tokens + bt > self.chunk_overlap:
                    break
                tail.insert(0, b)
                tokens += bt
            current, current_tokens = tail, tokens

        for block in blocks:
            if block.kind == "heading":
                breadcrumb[block.level] = block.text
                for deeper in [k for k in breadcrumb if k > block.level]:
                    del breadcrumb[deeper]

            btokens = count_tokens(block.text)

            # Código gigante: fecha o chunk atual e emite o bloco sozinho, inteiro.
            if block.kind == "code" and btokens > self.chunk_size:
                if current:
                    emit()
                    current, current_tokens = [], 0  # sem overlap antes de código
                current = [block]
                current_tokens = btokens
                emit()
                current, current_tokens = [], 0
                continue

            if current and current_tokens + btokens > self.chunk_size:
                emit()
            current.append(block)
            current_tokens += btokens

        if current:
            emit()
        return chunks
