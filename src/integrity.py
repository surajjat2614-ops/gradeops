from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

embedder = SentenceTransformer("all-MiniLM-L6-v2")

def detect_rejump_collusion(student_results, similarity_threshold=0.90):
    """
    student_results: List of dicts containing 'justification', 'student_id' and 'error_axes'
    """
    justifications = [res['justification'] for res in student_results]
    embeddings = embedder.encode(justifications)  # Convert reasoning traces to vectors

    flags = [] 
    for i, res_a in enumerate(student_results):
        for j, res_b in enumerate(student_results):
            if i >= j: continue

            # Cosine similarity between reasoning vectors — captures meaning not just words
            similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]

            # Shared error axes — same wrong reasoning AND same error type is suspicious
            shared_errors = set(res_a['error_axes']) & set(res_b['error_axes'])

            # Flag if reasoning is nearly identical AND error types match
            if similarity > similarity_threshold and shared_errors:
                flags.append({
                    "pair": (res_a['student_id'], res_b['student_id']),
                    "confidence": round(float(similarity), 4),
                    "shared_error_axes": list(shared_errors),
                    "reason": "Identical logic jump detected in reasoning trace."
                })

    return flags