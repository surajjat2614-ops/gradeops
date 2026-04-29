# rubric_factory.py

import json
import torch
from ocr_engine import model, processor

def generate_rubric(question_text, marking_scheme_text=None):

    scheme_section = (
        f"MARKING SCHEME: {marking_scheme_text}"
        if marking_scheme_text
        else "No marking scheme provided. Generate sensible criteria from the question alone."
    )

    prompt = f"""
    Act as an Expert Curriculum Designer. Convert this into a structured JSON Rubric.

    QUESTION: {question_text}
    {scheme_section}

    Reply ONLY with this exact JSON, nothing else:
    {{
        "question_id": "q1",
        "max_score": <total marks>,
        "criteria": [
            {{
                "id": "c1",
                "description": "what student must mention",
                "points": <marks>,
                "type": "computational|conceptual|notation"
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

    return json.loads(raw_output)
