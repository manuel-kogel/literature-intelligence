"""Optional, evidence-constrained abstract screening via OpenAI Responses API."""
import json
import requests

ENDPOINT = 'https://api.openai.com/v1/responses'
SYSTEM = '''You are screening academic papers for a political psychology master's thesis about changes in affective polarization following terrorist attacks and political violence. Only use the provided title and abstract. Never infer results, study design, or mechanisms not explicitly stated. Distinguish empirical evidence from theoretical relevance. Reply ONLY with valid JSON containing: relevance (integer 0-100), category (one of 'Direkt empirisch', 'Theoretisch', 'Methodisch', 'Randständig', 'Nicht relevant'), hypotheses (array of any of 'H1 Schuldzuschreibung/Polarisierung', 'H2 gemeinsame Bedrohung/Depolarisierung', 'Vertikal/horizontal', 'Keine Zuordnung'), design (short string or 'Nicht erkennbar'), rationale (German, max 45 words), evidence (verbatim short excerpt from the supplied title or abstract, or empty string), uncertainty (German, max 25 words). A hypothesis tag means thematic relevance, NOT that the hypothesis was supported. If abstract is missing, say so and avoid strong judgments.'''

def parse_review(text, source_text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('Antwort ist kein JSON-Objekt')
    score = data.get('relevance')
    if type(score) is not int or not 0 <= score <= 100:
        raise ValueError('Ungültiger Relevanzwert')
    allowed = {'Direkt empirisch', 'Theoretisch', 'Methodisch', 'Randständig', 'Nicht relevant'}
    if data.get('category') not in allowed:
        raise ValueError('Ungültige Kategorie')
    evidence = str(data.get('evidence') or '')
    if evidence and evidence.casefold() not in source_text.casefold():
        raise ValueError('Belegstelle ist nicht im Titel/Abstract enthalten')
    hypotheses = data.get('hypotheses', [])
    valid_h = {'H1 Schuldzuschreibung/Polarisierung', 'H2 gemeinsame Bedrohung/Depolarisierung', 'Vertikal/horizontal', 'Keine Zuordnung'}
    if not isinstance(hypotheses, list) or any(x not in valid_h for x in hypotheses):
        raise ValueError('Ungültige Hypothesenlabels')
    return {
        'KI-Relevanz': score, 'KI-Kategorie': data['category'],
        'Hypothesenbezug (nicht Befund)': ', '.join(hypotheses),
        'Studiendesign (KI)': str(data.get('design') or 'Nicht erkennbar')[:180],
        'KI-Begründung': str(data.get('rationale') or '')[:600],
        'Textbeleg': evidence[:400], 'KI-Unsicherheit': str(data.get('uncertainty') or '')[:400],
    }

def review_paper(title, abstract, api_key, model='gpt-4.1-mini'):
    if not api_key.strip():
        raise ValueError('OpenAI API-Key fehlt')
    source = f'Title: {title}\nAbstract: {abstract or "[not available]"}'
    payload = {'model': model, 'instructions': SYSTEM, 'input': source,
               'max_output_tokens': 500, 'text': {'format': {'type': 'json_object'}}}
    response = requests.post(ENDPOINT, json=payload,
                             headers={'Authorization': f'Bearer {api_key.strip()}', 'Content-Type': 'application/json'},
                             timeout=50)
    response.raise_for_status()
    result = response.json()
    chunks = [part.get('text', '') for item in result.get('output', [])
              for part in item.get('content', []) if part.get('type') == 'output_text']
    if not chunks:
        raise ValueError('Keine auswertbare Modellantwort')
    return parse_review(''.join(chunks), source)
