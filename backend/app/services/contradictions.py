import re
import json

COLORS = ['black', 'red', 'blue', 'white', 'silver', 'grey', 'gray', 'green', 'yellow', 'brown']
VEHICLES = ['motorcycle', 'bike', 'scooter', 'car', 'auto-rickshaw', 'rickshaw', 'van', 'vehicle']
CLOTHING = ['jacket', 'hoodie', 'shirt', 't-shirt', 'cap', 'helmet', 'coat', 'sweater']

def parse_time_to_minutes(t_str: str) -> int | None:
    t_clean = re.sub(r'[\n\r]+', ' ', t_str).strip().lower()
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|hrs)?', t_clean)
    if not m:
        return None
    h = int(m.group(1))
    mins = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)
    if meridiem == 'pm' and h < 12:
        h += 12
    elif meridiem == 'am' and h == 12:
        h = 0
    return h * 60 + mins

def extract_colored_entities(text: str, entity_list: list[str]) -> dict[str, tuple[str, str]]:
    found = {}
    for item in entity_list:
        for c in COLORS:
            pat = rf'\b({c})\s+(?:[a-zA-Z-]+\s+)?({item})\b'
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                found[item] = (c.lower(), f'{m.group(1)} {m.group(2)}'.lower())
    return found

def extract_times(text: str) -> list[tuple[str, int]]:
    # Look at the statement text past the header
    body = text[300:] if len(text) > 300 else text
    clean_body = re.sub(r'[\r\n]+', ' ', body)
    time_pat = r'(?:around|at|approx\.?|approximately)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|hrs))'
    matches = re.findall(time_pat, clean_body, flags=re.IGNORECASE)
    cleaned = []
    for m in matches:
        mins = parse_time_to_minutes(m)
        if mins is not None:
            cleaned.append((re.sub(r'\s+', ' ', m).strip(), mins))
    return cleaned

def detect_contradictions_heuristic(statements: list[dict]) -> list[dict]:
    flags = []
    for i in range(len(statements)):
        for j in range(i + 1, len(statements)):
            s1 = statements[i]
            s2 = statements[j]
            d_ids = [s1['id'], s2['id']]

            # 1. Vehicle color/type check
            v1 = extract_colored_entities(s1['raw_text'], VEHICLES)
            v2 = extract_colored_entities(s2['raw_text'], VEHICLES)
            for v_type in v1:
                if v_type in v2 and v1[v_type][0] != v2[v_type][0]:
                    flags.append({
                        'documents': d_ids,
                        'summary': f'Vehicle Discrepancy: "{s1["title"]}" (Doc #{s1["id"]}) reports a {v1[v_type][1]}, whereas "{s2["title"]}" (Doc #{s2["id"]}) reports a {v2[v_type][1]}.'
                    })

            # 2. Clothing color/item check
            c1 = extract_colored_entities(s1['raw_text'], CLOTHING)
            c2 = extract_colored_entities(s2['raw_text'], CLOTHING)
            for c_type in c1:
                if c_type in c2 and c1[c_type][0] != c2[c_type][0]:
                    flags.append({
                        'documents': d_ids,
                        'summary': f'Clothing Discrepancy: "{s1["title"]}" (Doc #{s1["id"]}) describes suspect wearing a {c1[c_type][1]}, whereas "{s2["title"]}" (Doc #{s2["id"]}) describes a {c2[c_type][1]}.'
                    })

            # 3. Incident timeline check
            t1 = extract_times(s1['raw_text'])
            t2 = extract_times(s2['raw_text'])
            if t1 and t2:
                for time1_str, m1 in t1:
                    for time2_str, m2 in t2:
                        diff = abs(m1 - m2)
                        if 30 <= diff <= 360:
                            flags.append({
                                'documents': d_ids,
                                'summary': f'Timeline Discrepancy: "{s1["title"]}" (Doc #{s1["id"]}) places incident around {time1_str}, whereas "{s2["title"]}" (Doc #{s2["id"]}) reports activity at around {time2_str} ({diff}-minute difference).'
                            })
                            break
    return flags

def detect_contradictions(db, case_id: int) -> list[dict]:
    db.execute(
        """SELECT id, title, raw_text FROM documents
           WHERE case_id = %s AND doc_type = 'witness_statement'""",
        (case_id,)
    )
    statements = db.fetchall()

    if len(statements) < 2:
        return []

    statements_dicts = []
    for s in statements:
        try:
            statements_dicts.append(dict(s))
        except TypeError:
            statements_dicts.append({"id": s[0], "title": s[1], "raw_text": s[2]})

    # 1. Try Claude model if configured
    try:
        from app.services.classify import client
        combined = "\n\n".join(
            f"--- Document: {s['title']} (id={s['id']}) ---\n{s['raw_text'][:1500]}"
            for s in statements_dicts
        )
        prompt = f"""You are assisting a human investigator, not making legal determinations.
Compare the witness statements below. Identify any factual contradictions
(time, date, location, description of events or people). For each contradiction found,
cite the specific document titles/ids involved and quote the conflicting detail briefly.
If there are no contradictions, say so explicitly. Do not speculate on which
statement is true — only flag the discrepancy for human review.

{combined}

Respond in this exact JSON format:
{{"contradictions": [{{"documents": ["id1", "id2"], "summary": "short description"}}]}}"""

        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = json.loads(response.content[0].text)
        contradictions = parsed.get("contradictions", [])
        if contradictions:
            return contradictions
    except Exception:
        pass

    # 2. Rule-based factual contradiction heuristic fallback
    return detect_contradictions_heuristic(statements_dicts)
