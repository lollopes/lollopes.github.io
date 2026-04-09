#!/usr/bin/env python3

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scholarly import ProxyGenerator, scholarly


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "data" / "scholar.json"
DEFAULT_NAME = os.getenv("SCHOLAR_AUTHOR_NAME", "Lorenzo Pes")
DEFAULT_AFFILIATION_HINT = os.getenv("SCHOLAR_AFFILIATION_HINT", "Eindhoven University of Technology")
DEFAULT_ORCID_URL = "https://orcid.org/0000-0002-8151-9327"
DEFAULT_TUE_URL = "https://research.tue.nl/en/persons/lorenzo-pes"


def configure_proxy() -> None:
    if os.getenv("SCHOLAR_USE_FREE_PROXIES", "1") != "1":
        return

    try:
        proxy = ProxyGenerator()
        if proxy.FreeProxies():
            scholarly.use_proxy(proxy)
    except Exception:
        return


def build_scholar_url(user_id: str | None) -> str:
    if user_id:
        return f"https://scholar.google.com/citations?user={user_id}&hl=en"
    return f"https://scholar.google.com/scholar?q={quote(f'\"{DEFAULT_NAME}\"')}"


def score_author(candidate: dict[str, Any]) -> tuple[int, int, int]:
    name = (candidate.get("name") or "").casefold()
    affiliation = (candidate.get("affiliation") or "").casefold()
    email_domain = (candidate.get("email_domain") or "").casefold()

    return (
        int(DEFAULT_NAME.casefold() == name),
        int(DEFAULT_AFFILIATION_HINT.casefold() in affiliation),
        int("tue" in email_domain or "eindhoven" in affiliation),
    )


def find_author() -> dict[str, Any]:
    user_id = os.getenv("SCHOLAR_USER_ID")
    if user_id:
        return scholarly.search_author_id(user_id)

    best_match = None
    best_score = (-1, -1, -1)

    for candidate in scholarly.search_author(DEFAULT_NAME):
        candidate_score = score_author(candidate)
        if candidate_score > best_score:
            best_match = candidate
            best_score = candidate_score
        if candidate_score[0] and candidate_score[1]:
            break

    if not best_match:
        raise RuntimeError(f'No Google Scholar profile found for "{DEFAULT_NAME}"')

    return best_match


def extract_publications(filled_author: dict[str, Any]) -> list[dict[str, Any]]:
    publications = []

    for publication in filled_author.get("publications", []):
        try:
            filled_publication = scholarly.fill(publication)
        except Exception:
            continue

        bibliographic = filled_publication.get("bib", {})
        publications.append(
            {
                "title": bibliographic.get("title") or "Untitled",
                "year": bibliographic.get("pub_year"),
                "venue": bibliographic.get("citation") or bibliographic.get("journal") or bibliographic.get("venue"),
                "citations": filled_publication.get("num_citations", 0),
                "url": filled_publication.get("pub_url") or filled_publication.get("eprint_url"),
            }
        )

    publications.sort(
        key=lambda publication: (
            int(publication.get("year") or 0),
            int(publication.get("citations") or 0),
        ),
        reverse=True,
    )

    return publications[:12]


def build_payload(filled_author: dict[str, Any]) -> dict[str, Any]:
    scholar_id = filled_author.get("scholar_id")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "name": filled_author.get("name") or DEFAULT_NAME,
            "scholar_url": build_scholar_url(scholar_id),
            "tue_url": DEFAULT_TUE_URL,
            "orcid": DEFAULT_ORCID_URL,
            "affiliation": filled_author.get("affiliation") or DEFAULT_AFFILIATION_HINT,
            "citedby": filled_author.get("citedby", 0),
            "hindex": filled_author.get("hindex", 0),
            "i10index": filled_author.get("i10index", 0),
        },
        "publications": extract_publications(filled_author),
    }


def main() -> None:
    configure_proxy()
    author = find_author()
    filled_author = scholarly.fill(author, sections=["basics", "indices", "counts", "publications"])
    payload = build_payload(filled_author)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
