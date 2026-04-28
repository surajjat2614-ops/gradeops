from typing import TypedDict, List

class GradeOpsState(TypedDict):
    # Inputs
    question_paper: str
    marking_scheme: str
    transcription: str      # From Day 2 OCR
    
    # Generated in Day 3
    rubric: dict            # The Output from the Rubric Factory
    
    # Final Output
    proposed_score: float
    justification: str      # Chain-of-Thought (CoT) reasoning [5, 6]
    needs_review: bool      # Confidence Flag