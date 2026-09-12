def suggest_related_case(db, new_doc_embedding, current_case_id, threshold=0.5):
    """After uploading a doc, check if it's semantically closer to a DIFFERENT case
    than the one it was uploaded under — flags likely misfiled documents."""
    # We use a lower threshold here than 0.82 because all-MiniLM-L6-v2 distances 
    # can scale differently than OpenAI text-embedding-3.
    sql = """
        SELECT case_id, id AS document_id, title,
               1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        WHERE case_id != %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """
    db.execute(sql, (new_doc_embedding, current_case_id, new_doc_embedding))
    candidates = db.fetchall()
    
    # We need to access by index or column name depending on how psycopg2 returns data
    # Assuming db returns dict-like or we just use positions:
    results = []
    for c in candidates:
        # If c is a tuple, indices are: 0=case_id, 1=document_id, 2=title, 3=similarity
        # If it's psycopg2.extras.DictRow or RealDictRow it has keys.
        # Let's assume it's dict-like since the original plan used `dict(c)`.
        try:
            similarity = c["similarity"]
        except (TypeError, IndexError):
            similarity = c[3]
            
        if similarity > threshold:
            # Let's rebuild the dict to be safe
            if isinstance(c, tuple) and not hasattr(c, 'keys'):
                results.append({
                    "case_id": c[0],
                    "document_id": c[1],
                    "title": c[2],
                    "similarity": c[3]
                })
            else:
                results.append(dict(c))
                
    return results
