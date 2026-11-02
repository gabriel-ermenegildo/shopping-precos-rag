"""Transformação: HTML bruto -> markdown estruturado e limpo.

Calibrado para as duas fontes reais:
  * Help Center (Product Fruits)  -> documentacao.shoppingdeprecos.com.br/pt/article/<slug>
  * API Docs (Apidog, SSR)        -> apidoc.shoppingdeprecos.com.br/<slug>

Decisões importantes:
  * Sidebar do Apidog se repete em TODA página (centenas de links): removida por
    heurística de densidade de links, não por seletor fixo — sobrevive a redesigns.
  * Blocos <pre> viram cercas ```lang ... ``` e são tratados como ATÔMICOS
    (o chunker nunca corta dentro deles).
  * Headings viram '#', preservando a hierarquia semântica usada no chunking.
  * "Última modificação: ..." (Apidog) é capturada como updated_at real do doc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

NOISE_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "button", "form",
    "footer", "nav", "aside", "header", "video", "canvas", "input", "select",
}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "ul", "ol", "table",
              "blockquote", "figure", "details"}
_HEADING_RE = re.compile(r"^h([1-6])$")
_UPDATED_RE = re.compile(
    r"[Úú]ltima\s+modifica[çc][ãa]o\s*:?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[ T0-9:]*)"
)
_WS_RE = re.compile(r"[ \t]+")
_NL3_RE = re.compile(r"\n{3,}")


@dataclass
class ExtractedDoc:
    url: str
    title: str
    markdown: str
    updated_at: str | None = None
    headings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Limpeza de ruído
# --------------------------------------------------------------------------- #
def _link_density(tag: Tag) -> float:
    text = tag.get_text(" ", strip=True)
    if not text:
        return 0.0
    link_text = " ".join(a.get_text(" ", strip=True) for a in tag.find_all("a"))
    return min(1.0, len(link_text) / max(1, len(text)))


def _prune_noise(soup: BeautifulSoup) -> None:
    for t in soup.find_all(NOISE_TAGS):
        t.decompose()
    # Sidebars/menus: containers dominados por links e SEM código dentro.
    for t in soup.find_all(["ul", "ol", "div", "section"]):
        if not isinstance(t, Tag) or t.find("pre") or t.find("table"):
            continue
        n_links = len(t.find_all("a"))
        if n_links >= 5 and _link_density(t) > 0.7:
            t.decompose()


def _pick_root(soup: BeautifulSoup) -> Tag:
    for selector in ("article", "main", "[role=main]"):
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > 80:
            return node
    return soup.body or soup


# --------------------------------------------------------------------------- #
# Render recursivo HTML -> markdown
# --------------------------------------------------------------------------- #
def _code_lang(pre: Tag) -> str:
    code = pre.find("code")
    classes = (code.get("class") if code else None) or pre.get("class") or []
    for c in classes:
        m = re.match(r"(?:language|lang)-([\w+-]+)", c)
        if m:
            return m.group(1)
    return ""


def _render(node) -> str:
    if isinstance(node, NavigableString):
        return _WS_RE.sub(" ", str(node))
    if not isinstance(node, Tag) or node.name in NOISE_TAGS:
        return ""

    name = node.name
    if name == "pre":
        code = node.get_text("\n").strip("\n")
        if not code.strip():
            return ""
        return f"\n\n```{_code_lang(node)}\n{code}\n```\n\n"

    m = _HEADING_RE.match(name)
    if m:
        text = node.get_text(" ", strip=True)
        text = re.sub(r"\s*#\s*$", "", text)  # âncoras '#' do Apidog
        return f"\n\n{'#' * int(m.group(1))} {text}\n\n" if text else ""

    if name == "code":  # inline (fora de <pre>)
        text = node.get_text(" ", strip=True)
        return f"`{text}`" if text else ""

    if name == "li":
        inner = "".join(_render(c) for c in node.children).strip()
        return f"\n- {inner}" if inner else ""

    if name == "table":
        rows = []
        for i, tr in enumerate(node.find_all("tr")):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not any(cells):
                continue
            rows.append("| " + " | ".join(cells) + " |")
            if i == 0:
                rows.append("|" + "---|" * len(cells))
        return "\n\n" + "\n".join(rows) + "\n\n" if rows else ""

    if name == "br":
        return "\n"

    inner = "".join(_render(c) for c in node.children)
    if name in BLOCK_TAGS:
        return f"\n\n{inner.strip()}\n\n" if inner.strip() else ""
    return inner


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def html_to_markdown(html: str, url: str) -> ExtractedDoc:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    title = re.sub(r"\s*-\s*API Shopping de Preços\s*$", "", title)

    _prune_noise(soup)
    root = _pick_root(soup)

    if not title:
        h1 = root.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else url

    md = _render(root)
    md = _NL3_RE.sub("\n\n", md).strip()

    updated = None
    m = _UPDATED_RE.search(md)
    if m:
        updated = m.group(1).strip()

    headings = re.findall(r"^#{1,6} (.+)$", md, flags=re.MULTILINE)
    return ExtractedDoc(url=url, title=title, markdown=md,
                        updated_at=updated, headings=headings)
