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
import streamlit as st
from ai_review import review_paper

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


st.set_page_config(page_title="Literature Intelligence", page_icon="📚", layout="centered")
st.markdown("""<style>
.block-container {max-width: 940px; padding-top: 1.1rem; padding-bottom: 3rem;}
.stButton button[kind=primary] {width: 100%; min-height: 3rem;}
@media (max-width: 640px) {
 .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: 0.6rem;}
 h1 {font-size: 1.7rem !important;}
 [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
 [data-testid="column"] {min-width: 100% !important;}
 .stDownloadButton button {width: 100%; min-height: 2.8rem;}
}
</style>""", unsafe_allow_html=True)
st.title("Literature Intelligence")
st.caption("Literaturrecherche für die Masterarbeit · Mobile V0.3 · Metadatensuche, kein PDF-Scraping")
st.info("Die Standardbewertung ist heuristisch. Optional kannst du eine **KI-Analyse von Titeln und Abstracts** durchführen. KI-Aussagen sind keine verifizierten Studienbefunde; überprüfe die Originaltexte.")
with st.expander("⚙️ Einstellungen & API-Zugang", expanded=False):
    st.caption("Diese Einstellungen sind auch auf dem iPhone direkt erreichbar.")
    default_key = os.getenv("OPENALEX_API_KEY", "")
    try:
        default_key = st.secrets.get("OPENALEX_API_KEY", default_key)
    except (FileNotFoundError, KeyError):
        pass
    api_key = st.text_input("OpenAlex-API-Key", value=default_key, type="password", help="Kostenlos unter openalex.org/settings/api anlegen. Niemals in GitHub-Dateien eintragen.")
    email = st.text_input("Kontakt-E-Mail (optional)", value="", help="Wird als mailto-Parameter an OpenAlex übertragen.")
    start_year = st.number_input("Publikationsjahr ab", min_value=1900, max_value=date.today().year, value=2010)
    max_per_query = st.slider("Treffer je Suchanfrage", min_value=10, max_value=100, value=40, step=10)
    st.caption("Bis zu 100 Treffer je Suchanfrage; API-Limits können begrenzen. Ein kostenloser API-Key wird empfohlen.")

query_text = st.text_area("Suchanfragen (eine pro Zeile)", value="\n".join(DEFAULT_QUERIES), height=185)
queries = list(dict.fromkeys(x.strip() for x in query_text.splitlines() if x.strip()))
if st.button("🔎 Literatur recherchieren", type="primary", disabled=not queries):
    results = {}
    errors = []
    progress = st.progress(0)
    for n, query in enumerate(queries):
        try:
            results[query] = fetch_works(query, int(start_year), max_per_query, api_key, email)
        except RuntimeError as e:
            errors.append(str(e))
        progress.progress((n + 1) / len(queries))
    st.session_state["results"] = dataframe_for(merge_results(results))
    st.session_state["counts"] = {q: len(w) for q, w in results.items()}
    st.session_state["errors"] = errors

if "results" in st.session_state:
    df = st.session_state["results"]
    for err in st.session_state["errors"]:
        st.error(err)
    st.write(f"**{len(df)} eindeutige Publikationen** aus {sum(st.session_state['counts'].values())} Treffern (vor Dublettenbereinigung)")
    if st.session_state["counts"]:
        st.caption("Treffer pro Suchanfrage: " + " · ".join(f"{q}: {n}" for q, n in st.session_state["counts"].items()))
    priorities = st.multiselect("Priorität anzeigen", ["Hoch", "Mittel", "Niedrig"], default=["Hoch", "Mittel", "Niedrig"])
    filtered = df[df["Priorität"].isin(priorities)].copy()
    st.dataframe(filtered, use_container_width=True, hide_index=True, column_config={
        "OpenAlex": st.column_config.LinkColumn("OpenAlex"),
        "Open-Access-Link": st.column_config.LinkColumn("Open-Access-Link")})
    st.subheader("Ergebnisse exportieren")
    left, middle, right = st.columns(3)
    with left:
        st.download_button("CSV für Excel", use_container_width=True, data=filtered.to_csv(index=False).encode("utf-8-sig"), file_name="literature_results.csv", mime="text/csv")
    with middle:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            filtered.to_excel(writer, index=False, sheet_name="Literatur")
        st.download_button("Excel (.xlsx)", use_container_width=True, data=buffer.getvalue(), file_name="literature_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with right:
        st.download_button("RIS für Zotero", use_container_width=True, data=export_ris(filtered), file_name="literature_results.ris", mime="application/x-research-info-systems")
    st.caption("Die Suchabdeckung ist nicht systematisch vollständig. Relevanzscores beruhen auf Titel/Abstract, nicht auf der Prüfung eines Volltextes.")
    st.divider()
    st.subheader("KI-Abstract-Screening (optional)")
    st.caption("OpenAI-API ist ein separater, potenziell kostenpflichtiger Dienst. Dein ChatGPT-Abo beinhaltet keine API-Nutzung. Es werden Titel und Abstracts an OpenAI übermittelt, keine PDFs. Der Schlüssel wird nicht in GitHub gespeichert.")
    ai_key = st.text_input("OpenAI API-Key", type="password", key="ai_key", help="Nur hier eingeben, niemals in GitHub eintragen oder weitergeben.")
    model = st.selectbox("KI-Modell", ["gpt-4.1-mini", "gpt-4.1-nano"], index=0)
    limit = st.slider("Maximal zu analysierende Artikel", 1, 30, 5, 1)
    only_abstracts = st.checkbox("Nur Artikel mit Abstract", value=True)
    st.caption("Es werden die höchstplatzierten Artikel der aktuellen Filterung analysiert. Starte zunächst mit 3–5 Artikeln, um die Kosten zu begrenzen. Die API berechnet nach Tokenverbrauch, nicht nach der Anzahl angezeigter Artikel.")
    candidates = filtered[filtered["Abstract"].fillna("").str.strip().ne("")] if only_abstracts else filtered
    if st.button("KI-Analyse starten", disabled=not bool(ai_key.strip()) or candidates.empty):
        selected = candidates.head(limit)
        reviewed = []
        failures = []
        bar = st.progress(0)
        for index, (_, paper) in enumerate(selected.iterrows()):
            try:
                review = review_paper(str(paper["Titel"]), str(paper["Abstract"] or ""), ai_key, model)
                reviewed.append({"Titel": paper["Titel"], "DOI": paper["DOI"], **review})
            except (requests.RequestException, ValueError, KeyError) as error:
                failures.append(f"{paper['Titel']}: {str(error)[:180]}")
            bar.progress((index + 1) / len(selected))
        st.session_state['ai_reviews'] = pd.DataFrame(reviewed)
        st.session_state['ai_failures'] = failures
    if 'ai_reviews' in st.session_state:
        for error in st.session_state.get('ai_failures', []):
            st.warning(error)
        ai_df = st.session_state['ai_reviews']
        if not ai_df.empty:
            st.dataframe(ai_df, use_container_width=True, hide_index=True)
            st.download_button("KI-Screening als CSV", data=ai_df.to_csv(index=False).encode('utf-8-sig'), file_name='abstract_screening.csv', mime='text/csv')
            st.caption("Hypothesenlabels zeigen nur thematische Anschlussfähigkeit, keine empirische Bestätigung. Zitate werden gegen den gelieferten Text geprüft; die Interpretation bleibt prüfpflichtig.")

else:
    st.caption("Suchanfragen bearbeiten und auf „Literatur recherchieren“ klicken. Die Anwendung kontaktiert dann OpenAlex.")
