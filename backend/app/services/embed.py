try:
    from sentence_transformers import SentenceTransformer
    # We use all-MiniLM-L6-v2, which creates a 384-dimensional vector.
    model = SentenceTransformer('all-MiniLM-L6-v2')

    def get_embedding(text: str) -> list[float]:
        """Generates an embedding vector for the provided text."""
        return model.encode(text).tolist()
except Exception:
    def get_embedding(text: str) -> list[float]:
        """Fallback dummy embedding (384 dimensions) when sentence-transformers is not available."""
        return [0.0] * 384
