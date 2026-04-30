from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

embedder = SentenceTransformer("all-MiniLM-L6-v2")

def detect_rejump_collusion(student_results, similarity_threshold=0.90):
    """
    student_results: List of dicts containing 'justification', 'student_id' and 'error_axes'
    """
    flags = []
    
    # <-- MISSING FILTER: Ignore system errors so they aren't compared against each other
    valid_results = [
        res for res in student_results 
        if "SYSTEM ERROR:" not in res['justification'] and "AI response could not be parsed" not in res['justification']
    ]

    if len(valid_results) < 2:
        return flags

    justifications = [res['justification'] for res in valid_results]
    embeddings = embedder.encode(justifications) 

    for i, res_a in enumerate(valid_results):
        for j, res_b in enumerate(valid_results):
            if i >= j: continue

            similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
            
            # Using .get() prevents KeyError if error_axes is missing
            shared_errors = set(res_a.get('error_axes', [])) & set(res_b.get('error_axes', []))

            if similarity > similarity_threshold:
                flags.append({
                    "pair": (res_a['student_id'], res_b['student_id']),
                    "confidence": round(float(similarity), 4),
                    "shared_error_axes": list(shared_errors) if shared_errors else [],
                    "reason": "Identical logic jump detected in reasoning trace."
                })

    return flags
