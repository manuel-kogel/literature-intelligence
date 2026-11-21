# Literature Intelligence – Mobile V0.2

Eine auf Smartphone-Bildschirme angepasste Streamlit-Anwendung zur **Metadatensuche** nach wissenschaftlicher Literatur zu affektiver Polarisierung, Terroranschlägen und politischer Gewalt. Die Bewertung ist regelbasiert (Titel/Abstract), **nicht** KI-generiert und kein Ersatz für wissenschaftliches Screening. Export: CSV, XLSX, RIS (Zotero).

## Auf dem iPhone online nutzen (Streamlit Community Cloud)

1. Kostenloses GitHub-Konto erstellen oder anmelden: https://github.com
2. Unter https://github.com/new ein neues Repository anlegen, z. B. `literature-intelligence` (für die einfachste Cloud-Bereitstellung **Public**). Keine persönlichen Datensätze oder Zugangsdaten hochladen.
3. Die **einzelnen Dateien aus diesem Ordner** auf GitHub hochladen: auf Repository-Seite `Add file` → `Upload files` → `Commit changes`. Wichtig: `app.py` und `requirements.txt` müssen im Repository-Hauptverzeichnis liegen, nicht verschachtelt im ZIP-Ordner. Alternativ GitHub über Desktop/Browser nutzen.
4. https://share.streamlit.io öffnen, mit GitHub anmelden, `Create app` / `Deploy app` auswählen, Repository wählen, Branch `main`, **Main file path** `app.py`.
5. Nach erfolgreicher Bereitstellung die angezeigte `*.streamlit.app`-URL in Safari auf dem iPhone öffnen.
6. Safari → **Teilen** → **Zum Home-Bildschirm** hinzufügen (optional).
7. In der App den OpenAlex-API-Key über `⚙️ Einstellungen & API-Zugang` eintragen. Kostenlosen API-Key über https://openalex.org/settings/api erstellen.

**Optional: Geheimnis statt manueller Eingabe**: In den App-Einstellungen der Streamlit Community Cloud unter **Secrets** eintragen (niemals in GitHub!):

```toml
OPENALEX_API_KEY = "DEIN_ECHTER_KEY"
```

Bei einer öffentlich erreichbaren App kann ein serverseitiger API-Key von Besuchern für Suchanfragen genutzt werden. Für ausschließlich persönliche Nutzung den Key lieber bei jeder Sitzung selbst eingeben, oder den Zugriff beschränken. Geheimnisse nicht in Code, README oder Screenshots veröffentlichen.

## Lokal auf PC/Mac starten

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Wissenschaftliche Grenzen

- Nur OpenAlex-Titel, Abstracts und Metadaten, **keine Volltext-PDF-Scraping-Funktion**.
- Heuristische Trefferbewertung anhand offengelegter Keywords; keine Validierung von Forschungsdesigns, Theoriequalität oder Kausalidentifikation.
- OpenAlex-Kontingente können sich ändern; API-Key und Limits: https://help.openalex.org/api/authentication/
- Kein vollständiges systematisches Review. Suche, Datum, Ausschlüsse und manuelle Codierung gesondert dokumentieren.
- Öffentliche Cloud-Apps sind nicht als sicherer Speicher für vertrauliche Forschungsdaten vorgesehen.

## V0.3: optionales KI-Screening

Nach einer OpenAlex-Recherche kann das Tool ausgewählte Titel und Abstracts über die OpenAI Responses API prüfen. Hierfür ist ein **separater OpenAI-API-Key mit aktiver Abrechnung** nötig (ChatGPT Plus reicht nicht). Der Key wird ausschließlich im passwortgeschützten Eingabefeld der Streamlit-Sitzung verwendet und nicht im Repository abgelegt. Die API verarbeitet die eingesandten Titel und Abstracts; keine Volltexte oder PDFs. Kosten hängen vom gewählten Modell und Tokenverbrauch ab. Zunächst nur 3–5 Artikel prüfen.

Die Auswertung enthält KI-Relevanz, Kategorie, Hypothesenbezug (keine Befundbestätigung), Studiendesign, Begründung, wörtlichen Textbeleg und Unsicherheit. Der Textbeleg wird gegen den übergebenen Text validiert. Keine KI-Auswertung ersetzt die Lektüre des Originals.

**Update des bestehenden GitHub-Repositories:** `app.py`, `ai_review.py`, `test_ai_review.py` und `README.md` im Repository-Hauptverzeichnis hochladen bzw. ersetzen. `requirements.txt` bleibt unverändert. Streamlit stellt nach dem Commit automatisch neu bereit.
