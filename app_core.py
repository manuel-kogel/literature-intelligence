"""Literature Intelligence: a transparent OpenAlex discovery assistant."""
import io
import os
import re
import time
import unicodedata
from datetime import date
from collections import Counter

import pandas as pd
import requests

BASE = "https://api.openalex.org/works"
DEFAULT_QUERIES = [
    '"affective polarization" terrorist attack',
    '"affective polarization" political violence',
    'terrorist attack political attitudes polarization',
    'terrorism partisan attitudes blame attribution',
    'intergroup threat common ingroup identity polarization',
    'rally round the flag terrorist attacks political trust',
]
DIMENSIONS = {
    "Affektive Polarisierung": ["affective polari", "affective partisan", "partisan animosity", "out-party", "outgroup hostility", "out-group hostility", "partisan dislike"],
    "Terror/Politische Gewalt": ["terror", "political violen", "attack", "extremis", "mass shooting", "assassination", "violent incident"],
    "Schuldzuschreibung": ["blame", "attribut", "responsib", "scapegoat", "culpab"],
    "Bedrohung": ["threat", "fear", "anxiety", "insecurity", "perceived danger"],
    "Gemeinsame Identität": ["common ingroup", "superordinate ident", "collective ident", "national unity", "social ident", "solidarity"],
    "Panel/Experiment": ["panel", "longitudinal", "difference-in-differences", "difference in differences", "experiment", "event study", "pre-post", "natural experiment"],
    "Vertikale Polarisierung": ["vertical polari", "political elite", "politician", "party leader", "elite affect"],
    "Horizontale Polarisierung": ["horizontal polari", "voter", "ordinary partisan", "supporters", "citizens", "social distance"],
}
WEIGHTS = {"Affektive Polarisierung": 26, "Terror/Politische Gewalt": 20, "Schuldzuschreibung": 12,
           "Bedrohung": 11, "Gemeinsame Identität": 10, "Panel/Experiment": 9,
           "Vertikale Polarisierung": 6, "Horizontale Polarisierung": 6}
FIELDS = ["Relevanz (heuristisch)", "Priorität", "Titel", "Autor:innen", "Jahr", "Journal/Quelle",
          "DOI", "OpenAlex", "Open-Access-Link", "Zitationen", "Abstract", "Erkannte Dimensionen", "Suchanfragen"]


def abstract_from_index(index):
    if not isinstance(index, dict) or not index:
        return ""
    words = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(words))


def clean_doi(value):
    if not value:
        return ""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value).strip(), flags=re.I).lower()


def norm(value):
    text = unicodedata.normalize("NFKD", value or "")
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def key_for(work):
    doi = clean_doi(work.get("doi"))
    return "doi:" + doi if doi else "title:" + norm(work.get("title") or work.get("display_name") or "")


def score_work(work):
    title = (work.get("title") or work.get("display_name") or "").lower()
    abstract = (work.get("abstract") or "").lower()
    matches = []
    score = 0
    for dimension, phrases in DIMENSIONS.items():
        in_title = any(p in title for p in phrases)
        in_abstract = any(p in abstract for p in phrases)
        if in_title or in_abstract:
            matches.append(dimension)
            score += WEIGHTS[dimension] * (1.0 if in_title else 0.72)
    return min(100, round(score)), ", ".join(matches)


def fetch_works(query, start_year, max_results, api_key, email=""):
    """Page results; retry temporary failures; never silently truncate on errors."""
    found = []
    page = 1
    while len(found) < max_results:
        params = {
            "search": query,
            "filter": f"from_publication_date:{start_year}-01-01,to_publication_date:{date.today().isoformat()}",
            "per_page": min(100, max_results - len(found)),
            "page": page,
        }
        if api_key:
            params["api_key"] = api_key
        if email:
            params["mailto"] = email
        for attempt in range(3):
            try:
                response = requests.get(BASE, params=params, timeout=30, headers={"User-Agent": "LiteratureIntelligence/0.1 (academic research)"})
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            except (requests.RequestException, ValueError) as error:
                if attempt == 2:
                    raise RuntimeError(f"OpenAlex-Anfrage fehlgeschlagen ({query!r}, Seite {page}): {error}") from error
                time.sleep(2 ** attempt)
        batch = payload.get("results") or []
        if not batch:
            break
        found.extend(batch)
        if len(batch) < params["per_page"]:
            break
        page += 1
        time.sleep(0.15)
    return found


def normalize_work(work, query):
    venue = (work.get("primary_location") or {}).get("source") or {}
    authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
    best_oa = work.get("best_oa_location") or {}
    oa = work.get("open_access") or {}
    return {
        "title": work.get("display_name") or work.get("title") or "",
        "authors": ", ".join(a for a in authors if a),
        "year": work.get("publication_year"),
        "venue": venue.get("display_name") or "",
        "doi": clean_doi(work.get("doi")),
        "openalex": work.get("id") or "",
        "oa_url": best_oa.get("pdf_url") or best_oa.get("landing_page_url") or oa.get("oa_url") or "",
        "citations": work.get("cited_by_count", 0),
        "abstract": abstract_from_index(work.get("abstract_inverted_index")),
        "queries": [query],
    }


def merge_results(raw_by_query):
    merged = {}
    for query, works in raw_by_query.items():
        for work in works:
            k = key_for(work)
            if not k or k == "title:":
                continue
            item = normalize_work(work, query)
            if k not in merged:
                merged[k] = item
            else:
                prior = merged[k]
                prior["queries"] = list(dict.fromkeys(prior["queries"] + [query]))
                for field in ("abstract", "oa_url", "doi", "venue"):
                    if not prior[field] and item[field]:
                        prior[field] = item[field]
    return list(merged.values())


def dataframe_for(works):
    rows = []
    for work in works:
        s, matched = score_work(work)
        priority = "Hoch" if s >= 45 else "Mittel" if s >= 20 else "Niedrig"
        rows.append({
            "Relevanz (heuristisch)": s, "Priorität": priority,
            "Titel": work["title"], "Autor:innen": work["authors"], "Jahr": work["year"],
            "Journal/Quelle": work["venue"], "DOI": work["doi"], "OpenAlex": work["openalex"],
            "Open-Access-Link": work["oa_url"], "Zitationen": work["citations"],
            "Abstract": work["abstract"], "Erkannte Dimensionen": matched,
            "Suchanfragen": " | ".join(work["queries"]),
        })
    if not rows:
        return pd.DataFrame(columns=FIELDS)
    return pd.DataFrame(rows, columns=FIELDS).sort_values(
        ["Relevanz (heuristisch)", "Zitationen"], ascending=[False, False]).reset_index(drop=True)


def export_ris(df):
    """RIS for Zotero; provide only information available from OpenAlex."""
    lines = []
    for _, row in df.iterrows():
        lines.extend(["TY  - JOUR", f"TI  - {row['Titel']}"])
        for author in str(row["Autor:innen"]).split(", "):
            if author:
                lines.append(f"AU  - {author}")
        if pd.notna(row["Jahr"]):
            lines.append(f"PY  - {int(row['Jahr'])}")
        if row["Journal/Quelle"]:
            lines.append(f"JO  - {row['Journal/Quelle']}")
        if row["DOI"]:
            lines.append(f"DO  - {row['DOI']}")
        if row["Abstract"]:
            lines.append("AB  - " + str(row["Abstract"]).replace("\n", " "))
        lines.append("UR  - " + (f"https://doi.org/{row['DOI']}" if row["DOI"] else row["OpenAlex"]))
        lines.extend(["ER  -", ""])
    return "\n".join(lines).encode("utf-8")


