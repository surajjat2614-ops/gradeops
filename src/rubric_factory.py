import json
import re
import torch
from ocr_engine import model, processor
from grader import extract_json

def generate_rubric(question_text, marking_scheme_text=None):

    scheme_section = (
        f"MARKING SCHEME: {marking_scheme_text}"
        if marking_scheme_text
        else "No marking scheme provided. Generate sensible criteria from the question alone."
    )

    # ---> UPDATED PROMPT HERE <---
    prompt = f"""
    Act as an Expert Curriculum Designer. Convert the QUESTION and MARKING SCHEME into a structured JSON Rubric.

    QUESTION: {question_text}
    {scheme_section}

    STRICT RULES:
    1. DO NOT copy placeholder text like "what student must mention". Write actual, specific grading criteria based on the subject matter.
    2. The `max_score` MUST be the exact mathematical sum of all the `points` in the criteria array.
    3. If no marking scheme is provided, use your domain knowledge to deduce the exact formulas, keywords, or steps the student needs to show.

    Reply ONLY with this exact JSON schema (this is an example format, replace with actual data):
    {{
        "question_id": "q1",
        "max_score": 10,
        "criteria": [
            {{
                "id": "c1",
                "description": "Student correctly identifies the primary cause.",
                "points": 5,
                "type": "conceptual"
            }},
            {{
                "id": "c2",
                "description": "Student uses the correct formula.",
                "points": 5,
                "type": "computational"
            }}
        ]
    }}
    """

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=512, do_sample=False)

    raw_output = processor.batch_decode(
        [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0].strip()

    try:
      return extract_json(raw_output)
    except (json.JSONDecodeError, ValueError):
      print("Failed to parse rubric. Raw output:\n", raw_output)
      # ---> FALLBACK DICTIONARY INSTEAD OF 'None' <---
      return {
          "question_id": "error_q",
          "max_score": 10,
          "criteria": [{"id": "c1", "description": "Manual grading required due to rubric generation failure.", "points": 10, "type": "conceptual"}]
      }
