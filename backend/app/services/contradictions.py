from app.services.classify import client
import json

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

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = json.loads(response.content[0].text)
        return parsed.get("contradictions", [])
    except Exception as e:
        print(f"Error parsing contradictions: {e}")
        return []
