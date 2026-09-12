from difflib import SequenceMatcher

try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        import spacy.cli
        spacy.cli.download("en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")

    def extract_person_names(text: str) -> list[str]:
        doc = nlp(text)
        names = {ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"}
        return list(names)
except Exception:
    def extract_person_names(text: str) -> list[str]:
        return []

def normalize(name: str) -> str:
    return " ".join(name.lower().split())

def find_matching_entity(db, case_id: int, name: str, similarity_threshold: float = 0.85):
    norm = normalize(name)
    db.execute(
        "SELECT id, normalized_name FROM entities WHERE case_id = %s", (case_id,)
    )
    existing = db.fetchall()
    
    for row in existing:
        try:
            # handle both dict-like and tuple rows
            row_id = row["id"]
            row_norm = row["normalized_name"]
        except (TypeError, IndexError):
            row_id = row[0]
            row_norm = row[1]
            
        ratio = SequenceMatcher(None, norm, row_norm).ratio()
        if ratio >= similarity_threshold:
            return row_id
    return None

def classify_entity_role(text: str, name: str) -> str:
    # A lightweight prompt to determine the role
    # Assuming anthropic client from classify
    from app.services.classify import client
    
    prompt = f"""In the following document text, what role does "{name}" play?
Choose exactly one: witness, accused, victim, officer, unknown.

Text:
{text[:2000]}

Respond with only the role label."""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        label = response.content[0].text.strip().lower()
        return label if label in ("witness", "accused", "victim", "officer") else "unknown"
    except Exception:
        return "unknown"

def process_entities(db, doc_id: int, case_id: int, raw_text: str):
    names = extract_person_names(raw_text)
    for name in names:
        entity_id = find_matching_entity(db, case_id, name)
        if entity_id is None:
            role = classify_entity_role(raw_text, name)
            db.execute(
                """INSERT INTO entities (case_id, name, normalized_name, role, first_seen_document_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (case_id, name, normalize(name), role, doc_id)
            )
            entity_id = db.fetchone()[0]

        db.execute(
            "INSERT INTO document_entities (document_id, entity_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (doc_id, entity_id)
        )
    db.commit()
