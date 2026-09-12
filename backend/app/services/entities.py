import re
from difflib import SequenceMatcher

nlp = None
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        import spacy.cli
        spacy.cli.download("en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")
except Exception:
    pass

BLACKLIST = {
    "action taken", "acts & sections", "bns", "bnss", "fir", "charge sheet",
    "exhibit", "exhibits", "cctv", "complaint", "district", "police station",
    "colony", "market", "chowk", "nagar", "court", "fsl case", "ward",
    "sample state", "gandhi colony", "shivaji chowk", "kachi basti", "state",
    "address house", "station diary", "entry no", "reference no", "first information",
    "forensic examination", "regional forensic", "trace evidence", "signature of",
    "police", "sub-inspector", "inspector", "court filing", "judicial magistrate"
}

PREFIX_CLEAN = [
    r"^(?:complainant(?:\s+name)?|witness(?:\s+name)?|accused(?:\s*\d+[\.\)]?)?)\s*[:\s-]*",
    r"^(?:investigating\s+officer|investigation\s+officer|duty\s+officer|examining\s+officer|reporting\s+officer|recorded\s+by)\s*[:\s-]*",
    r"^(?:si|inspector|sub-inspector|dr\.|mr\.|ms\.|mrs\.|late)\s+",
]

def clean_name(s: str) -> str:
    s = s.strip()
    for pat in PREFIX_CLEAN:
        s = re.sub(pat, "", s, flags=re.IGNORECASE).strip()
    return s

def extract_person_names(text: str) -> list[str]:
    if not text:
        return []
    found = set()

    # 1. Regex patterns for structured fields in legal & police documents
    patterns = [
        r"(?:Complainant(?:\s+Name)?|Victim)\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"Accused(?:\s*\d+[\.\)]?)?\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"Witness(?:\s+Name)?\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"(?:Investigating Officer|Investigation Officer|Duty Officer|Examining Officer|Reporting Officer|Recorded by)\s*[:\s]+(?:SI\s+|Dr\.\s+|Inspector\s+|Sub-Inspector\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"(?:SI|Dr\.|Inspector|Sub-Inspector)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"(?:S/o|D/o|W/o)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            cand = clean_name(m.group(1))
            if "\n" not in cand and len(cand.split()) >= 2:
                found.add(cand)

    # 2. SpaCy PERSON entities
    if nlp:
        try:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    cand = clean_name(ent.text)
                    if "\n" not in cand and len(cand) > 3 and len(cand.split()) >= 2:
                        found.add(cand)
        except Exception:
            pass

    # 3. Filter blacklist, digits, and noise
    clean_list = []
    for n in found:
        norm = n.lower().strip(" .,;")
        if any(b in norm for b in BLACKLIST):
            continue
        if any(char.isdigit() for char in n):
            continue
        if len(norm) < 4:
            continue
        clean_list.append(n.strip(" .,;"))

    # 4. Dedup sub-names (e.g. if 'Rakesh Kumar Sharma' is present, don't keep standalone 'Kumar Sharma')
    final = []
    for n in clean_list:
        if any(n != other and n in other for other in clean_list):
            continue
        final.append(n)
    return sorted(final)

def normalize(name: str) -> str:
    return " ".join(name.lower().split())

def find_matching_entity(db, case_id: int, name: str, similarity_threshold: float = 0.80):
    norm = normalize(name)
    words = set(norm.split())

    cur = db.execute(
        "SELECT id, name, normalized_name FROM entities WHERE case_id = %s", (case_id,)
    )
    existing = cur.fetchall()

    for row in existing:
        try:
            row_id = row["id"]
            row_norm = row["normalized_name"]
        except (TypeError, IndexError):
            row_id = row[0]
            row_norm = row[1]

        if norm == row_norm:
            return row_id

        # Sub-word matching (e.g., 'Rakesh Sharma' or 'Kumar Sharma' matching 'Rakesh Kumar Sharma')
        row_words = set(row_norm.split())
        if len(words) >= 2 and len(row_words) >= 2:
            if words.issubset(row_words) or row_words.issubset(words):
                return row_id

        # If both have distinct multi-character first names and they don't match, they are different people
        list1 = norm.split()
        list2 = row_norm.split()
        if len(list1) >= 2 and len(list2) >= 2:
            first1, first2 = list1[0], list2[0]
            if len(first1) > 1 and len(first2) > 1 and first1 != first2:
                continue

        ratio = SequenceMatcher(None, norm, row_norm).ratio()
        if ratio >= similarity_threshold:
            return row_id
    return None

def classify_entity_role(text: str, name: str) -> str:
    # 1. Try Anthropic Claude model if configured
    try:
        from app.services.classify import client
        prompt = f"""In the following document text, what role does "{name}" play?
Choose exactly one: witness, accused, victim, officer, unknown.

Text:
{text[:2000]}

Respond with only the role label."""
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        label = response.content[0].text.strip().lower()
        if label in ("witness", "accused", "victim", "officer"):
            return label
    except Exception:
        pass

    # 2. Check if mentioned as parent/relative (S/o, D/o, W/o)
    if re.search(r'(?:S/o|D/o|W/o)\s+' + re.escape(name), text, flags=re.IGNORECASE):
        if not re.search(r'accused(?:\s*\d+[\.\)]?)?\s*[:\s]+' + re.escape(name), text, flags=re.IGNORECASE):
            return "unknown"

    # 3. Contextual heuristic fallback
    lines = text.split("\n")
    name_lower = name.lower()
    last_name = name.split()[-1].lower() if len(name.split()) > 1 else ""

    def check_keywords(s: str):
        if any(k in s for k in ["accused", "suspect", "arrested"]):
            return "accused"
        if any(k in s for k in ["witness", "witnessed", "statement of witness"]):
            return "witness"
        if any(k in s for k in ["complainant", "victim", "theft from", "scuffle", "bruises"]):
            return "victim"
        if any(k in s for k in ["investigating officer", "investigation officer", "duty officer", "examining officer", "reporting officer", "recorded by", "submitted by", "scientific officer", "sub-inspector", "inspector", "si ", "dr."]):
            return "officer"
        return None

    # Pass 1: Check the exact line containing the name
    for line in lines:
        line_l = line.lower()
        if name_lower in line_l:
            res = check_keywords(line_l)
            if res:
                return res

    # Pass 2: Check surrounding lines
    for i, line in enumerate(lines):
        line_l = line.lower()
        if name_lower in line_l or (last_name and len(last_name) > 3 and last_name in line_l):
            prev_line = lines[i - 1].lower() if i > 0 else ""
            next_line = lines[i + 1].lower() if i + 1 < len(lines) else ""
            res = check_keywords(prev_line + " " + line_l + " " + next_line)
            if res:
                return res

    # Pass 3: Check 150-char window around any occurrence of name
    for m in re.finditer(re.escape(name), text, flags=re.IGNORECASE):
        start = max(0, m.start() - 150)
        end = min(len(text), m.end() + 150)
        window = text[start:end].lower()
        res = check_keywords(window)
        if res:
            return res

    return "unknown"

def process_entities(db, doc_id: int, case_id: int, raw_text: str):
    if not raw_text:
        return
    names = extract_person_names(raw_text)
    for name in names:
        entity_id = find_matching_entity(db, case_id, name)
        if entity_id is None:
            role = classify_entity_role(raw_text, name)
            cur = db.execute(
                """INSERT INTO entities (case_id, name, normalized_name, role, first_seen_document_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (case_id, name, normalize(name), role, doc_id)
            )
            row = cur.fetchone()
            entity_id = row[0] if row else None

        if entity_id:
            db.execute(
                "INSERT INTO document_entities (document_id, entity_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (doc_id, entity_id)
            )
    db.commit()
