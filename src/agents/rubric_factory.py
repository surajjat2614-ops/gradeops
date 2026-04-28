import json

def generate_rubric(question_text, marking_scheme_text):
    """
    Day 3 Pivot: Automatically generate the JSON rubric.
    """
    prompt = f"""
    Act as an Expert Curriculum Designer. Convert this Question and Marking Scheme into a structured JSON Rubric.
    
    QUESTION: {question_text}
    MARKING SCHEME: {marking_scheme_text}
    
    OUTPUT FORMAT (Strict JSON):
    {{
        "question_id": "unique_id",
        "max_score": float,
        "criteria": [
            {{"id": "c1", "description": "short description", "points": float, "type": "computational|conceptual|notation"}},
           ...
        ]
    }}
    """
    # For Day 3, we will be using  Qwen2.5-3B-Instruct (text-only) for the work
    # return json.loads(llm_call(prompt)) 
    pass
