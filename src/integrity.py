from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

embedder = SentenceTransformer("all-MiniLM-L6-v2")

def _normalize_error_axes(raw_axes):
    """
    Convert heterogeneous model outputs into hashable string labels.
    Handles values like:
    - ["conceptual", "computational"]
    - [{"type": "conceptual"}, {"axis": "notation"}]
    - single strings or None
    """
    if raw_axes is None:
        return []
    if not isinstance(raw_axes, list):
        raw_axes = [raw_axes]

    normalized = []
    for item in raw_axes:
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, dict):
            normalized.append(
                str(item.get("type") or item.get("axis") or item.get("label") or "unknown")
            )
        else:
            normalized.append(str(item))
    return normalized

def detect_rejump_collusion(student_results, similarity_threshold=0.90):
    """
    student_results: List of dicts containing 'transcription', 'justification', 'student_id' and 'error_axes'
    """
    flags = []

    valid_results = [
        res for res in student_results
        if "SYSTEM ERROR:" not in res['justification'] and "AI response could not be parsed" not in res['justification'] and res.get('transcription') and "[?]" not in res['transcription']
    ]

    if len(valid_results) < 2:
        return flags

    # We use transcription to detect plagiarism as that is the actual student's work
    # We still check for shared error_axes to strengthen the signal
    transcriptions = [res['transcription'] for res in valid_results]
    embeddings = embedder.encode(transcriptions)

    for i, res_a in enumerate(valid_results):
        for j, res_b in enumerate(valid_results):
            if i >= j: continue

            similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]

            axes_a = _normalize_error_axes(res_a.get("error_axes"))
            axes_b = _normalize_error_axes(res_b.get("error_axes"))
            shared_errors = set(axes_a) & set(axes_b)

            if similarity > similarity_threshold:
                flags.append({
                    "pair": (res_a['student_id'], res_b['student_id']),
                    "confidence": round(float(similarity), 4),
                    "shared_error_axes": list(shared_errors) if shared_errors else [],
                    "reason": "High semantic similarity detected in the student's handwritten answer text."
                })

    return flags