try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    def redact_pii(text: str) -> str:
        if not text:
            return ""
        results = analyzer.analyze(text=text, entities=["PERSON", "PHONE_NUMBER", "LOCATION"], language="en")
        anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text
except Exception:
    import re

    def redact_pii(text: str) -> str:
        if not text:
            return ""
        # Regex fallback for email and phone numbers
        redacted = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', '<EMAIL>', text)
        redacted = re.sub(r'\b\d{10}\b', '<PHONE_NUMBER>', redacted)
        return redacted
