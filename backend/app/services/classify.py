import anthropic

client = anthropic.Anthropic(api_key="YOUR_API_KEY")

VALID_TYPES = ["FIR", "charge_sheet", "witness_statement", "forensic_report", "court_filing"]

def classify_document(raw_text: str) -> str:
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
        return label if label in VALID_TYPES else "unclassified"
    except Exception:
        return "unclassified"
