import anthropic

client = anthropic.Anthropic(api_key="YOUR_API_KEY")

VALID_TYPES = ["FIR", "charge_sheet", "witness_statement", "forensic_report", "court_filing"]

def classify_document(raw_text: str) -> str:
    if not raw_text:
        return "unclassified"

    prompt = f"""Classify the following legal document into exactly one of these types:
{', '.join(VALID_TYPES)}

Document text:
{raw_text[:3000]}

Respond with ONLY the type label, nothing else."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        label = response.content[0].text.strip()
        if label in VALID_TYPES:
            return label
    except Exception:
        pass

    # Heuristic rule-based fallback (check header section)
    header = raw_text[:600].lower()
    if "charge sheet" in header:
        return "charge_sheet"
    if "witness statement" in header or "statement of witness" in header:
        return "witness_statement"
    if "forensic" in header or "fsl case" in header:
        return "forensic_report"
    if "first information report" in header:
        return "FIR"
    if "court" in header or "bail" in header or "judicial magistrate" in header:
        return "court_filing"

    return "unclassified"
