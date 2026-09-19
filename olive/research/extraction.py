"""Deterministic page extraction preserving quoted technical material."""

import hashlib
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from .models import PageObservation
from .urls import normalize_url

MAX_HTML = 2 * 1024 * 1024
MAX_TEXT = 120000


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_page(html, url, content_type="text/html"):
    url = normalize_url(url)
    if len(html.encode("utf-8")) > MAX_HTML:
        raise ValueError("Page exceeds extraction size limit")
    if "html" not in content_type:
        text = html[:MAX_TEXT]
        return PageObservation(
            url, urlsplit(url).hostname, text, content_hash(text), content_type=content_type
        )
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for name in names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return str(tag["content"])[:500]
        return None

    title = meta("og:title") or (
        soup.title.get_text(" ", strip=True) if soup.title else urlsplit(url).hostname
    )
    author = meta("author", "article:author") or ""
    published = meta("article:published_time", "date", "datePublished")
    updated = meta("article:modified_time", "dateModified", "last-modified")
    canonical = ""
    tag = soup.find("link", rel="canonical")
    if tag and tag.get("href"):
        try:
            canonical = normalize_url(tag["href"], url)
        except ValueError:
            canonical = ""
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe"]
    ):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if not tag.attrs:
            continue
        identity = " ".join(tag.get("class", [])) + " " + str(tag.get("id", ""))
        if re.search(
            r"(?:^|[ _-])(?:cookie-banner|cookie-consent|advertisement|sidebar)(?:$|[ _-])", identity, re.I
        ):
            tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    links, seen = [], set()
    for tag in root.find_all("a", href=True):
        try:
            link = normalize_url(tag["href"], url)
        except ValueError:
            continue
        if link not in seen:
            links.append({"url": link, "text": tag.get_text(" ", strip=True)[:300]})
            seen.add(link)
        if len(links) >= 200:
            break
    blocks, headings, sections = [], [], []
    position = 0
    heading = ""
    for tag in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "p", "li", "pre", "table"]):
        if tag.name == "dd" and tag.find(["p", "li", "pre", "table", "dl"]):
            continue  # Structured children are emitted separately with their owner.
        if any(parent.name in {"pre", "table", "li"} for parent in tag.parents if parent is not root):
            continue
        if tag.name == "pre":
            block = "````\n" + tag.get_text().strip() + "\n````"
        elif tag.name == "table":
            rows = [
                " | ".join(cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"]))
                for row in tag.find_all("tr")
            ]
            block = "\n".join(rows)
        else:
            block = tag.get_text(" ", strip=True)
            if tag.name.startswith("h"):
                headings.append(block)
                heading = block
                block = "#" * int(tag.name[1]) + " " + block
            elif tag.name == "li":
                block = "- " + block
        if block and (not blocks or blocks[-1] != block):
            # Definition-list signatures carry API identity; paragraphs alone often
            # describe unnamed arguments or helpers and lose the owning operation.
            owner = tag if tag.name == "dt" else None
            if owner is None:
                description = tag if tag.name == "dd" else tag.find_parent("dd")
                owner = description.find_previous_sibling("dt") if description else None
            scope = owner.get_text(" ", strip=True)[:300] if owner else heading[:300]
            start = position + (2 if blocks else 0)
            end = start + len(block)
            if sections and sections[-1]['scope'] == scope and sections[-1]['kind'] == ('definition' if owner else 'section'):
                sections[-1]['end'] = min(end, MAX_TEXT)
            else:
                sections.append({'start':start,'end':min(end,MAX_TEXT),'scope':scope,
                                 'kind':'definition' if owner else 'section'})
            blocks.append(block)
            position = end
            if position >= MAX_TEXT:
                break
    text = ("\n\n".join(blocks) or root.get_text("\n", strip=True))[:MAX_TEXT]
    return PageObservation(
        url,
        title[:500],
        text,
        content_hash(text),
        canonical_url=canonical,
        author=author,
        publication_date=published,
        updated_date=updated,
        content_type=content_type,
        links=links,
        headings=headings[:100],
        metadata={"truncated": len(text) >= MAX_TEXT, "extraction": "static_structure",
                  "sections": sections},
    )
