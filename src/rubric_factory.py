<<<<<<< HEAD
import json
import re
import torch
from src.ocr_engine import model, processor
from src.grader import extract_json

def generate_rubric(question_text, marking_scheme_text=None, max_score=None):

    score_val = max_score if max_score else 10

    scheme_section = (
        f"MARKING SCHEME: {marking_scheme_text}"
        if marking_scheme_text
        else "No marking scheme provided. Generate sensible criteria from the question alone."
    )

    # ---> IMPROVED PROMPT FOR BETTER GROUNDING <---
    prompt = f"""
    Act as an Expert Subject Matter Specialist and Curriculum Designer.
    Your task is to create a high-precision grading rubric based STRICTLY on the provided question.

    QUESTION: {question_text}
    {scheme_section}
    TOTAL MARKS FOR THIS QUESTION: {score_val}

    STRICT OPERATIONAL GUIDELINES:
    1. GROUNDING: Every criterion MUST be directly related to the QUESTION text. Do NOT introduce external concepts, unrelated terminology, or hallucinated topics (e.g., if the question is about 'Force', do not mention 'Knots' unless specifically asked).
    2. FIDELITY: If the question is simple, keep the rubric simple. Do not over-complicate.
    3. ACCURACY: Ensure mathematical formulas or specific keywords required are technically correct for the subject.
    4. STRUCTURE: The max score MUST be {score_val}. The sum of all criteria points MUST equal {score_val}.

    Reply ONLY with this JSON schema:
    {{
        "question_id": "q1",
        "max_score": {score_val},
        "criteria": [
            {{
                "id": "c1",
                "description": "Specific, clear requirement for the student to meet.",
                "points": 5,
                "type": "conceptual"
            }}
        ]
    }}
    """

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=512, do_sample=False, use_cache=True)

    raw_output = processor.batch_decode(
        [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0].strip()

    try:
      rubric = extract_json(raw_output)
      
      # --- Post-processing to prevent hallucinations shown in screenshot ---
      criteria = rubric.get("criteria", [])
      if not criteria:
          raise ValueError("No criteria generated")

      # 1. Remove duplicate descriptions
      seen = set()
      unique_criteria = []
      for c in criteria:
          desc = str(c.get("description", "")).lower().strip()
          if desc and desc not in seen:
              seen.add(desc)
              unique_criteria.append(c)
      
      # 2. Enforce mathematical consistency
      target_max = float(max_score) if max_score else float(rubric.get("max_score", 10))
      current_total = sum(float(c.get("points", 0)) for c in unique_criteria)
      
      if current_total != target_max and current_total > 0:
          # Scale points proportionally
          factor = target_max / current_total
          for c in unique_criteria:
              c["points"] = round(float(c.get("points", 0)) * factor, 1)
          
          # Final correction to ensure exact sum (fixes the 9.8 vs 10.0 issue)
          new_total = sum(c["points"] for c in unique_criteria)
          diff = round(target_max - new_total, 1)
          if diff != 0 and unique_criteria:
              unique_criteria[-1]["points"] = round(unique_criteria[-1]["points"] + diff, 1)
      
      # Final sync
      rubric["criteria"] = unique_criteria
      rubric["max_score"] = round(sum(float(c.get("points", 0)) for c in unique_criteria), 1)
      
      return rubric

    except (json.JSONDecodeError, ValueError, Exception) as e:
      print(f"Failed to process rubric: {e}. Raw output:\n", raw_output)
      # ---> FALLBACK DICTIONARY INSTEAD OF 'None' <---
      return {
          "question_id": "error_q",
          "max_score": max_score or 10,
          "criteria": [{"id": "c1", "description": "Manual grading required due to rubric generation failure.", "points": max_score or 10, "type": "conceptual"}]
=======
import json
import re
import torch
from src.ocr_engine import model, processor
from src.grader import extract_json

def generate_rubric(question_text, marking_scheme_text=None, max_score=None):

    score_val = max_score if max_score else 10

    scheme_section = (
        f"MARKING SCHEME: {marking_scheme_text}"
        if marking_scheme_text
        else "No marking scheme provided. Generate sensible criteria from the question alone."
    )

    # ---> IMPROVED PROMPT FOR BETTER GROUNDING <---
    prompt = f"""
    Act as an Expert Subject Matter Specialist and Curriculum Designer.
    Your task is to create a high-precision grading rubric based STRICTLY on the provided question.

    QUESTION: {question_text}
    {scheme_section}
    TOTAL MARKS FOR THIS QUESTION: {score_val}

    STRICT OPERATIONAL GUIDELINES:
    1. GROUNDING: Every criterion MUST be directly related to the QUESTION text. Do NOT introduce external concepts, unrelated terminology, or hallucinated topics (e.g., if the question is about 'Force', do not mention 'Knots' unless specifically asked).
    2. FIDELITY: If the question is simple, keep the rubric simple. Do not over-complicate.
    3. ACCURACY: Ensure mathematical formulas or specific keywords required are technically correct for the subject.
    4. STRUCTURE: The max score MUST be {score_val}. The sum of all criteria points MUST equal {score_val}.

    Reply ONLY with this JSON schema:
    {{
        "question_id": "q1",
        "max_score": {score_val},
        "criteria": [
            {{
                "id": "c1",
                "description": "Specific, clear requirement for the student to meet.",
                "points": 5,
                "type": "conceptual"
            }}
        ]
    }}
    """

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=512, do_sample=False, use_cache=True)

    raw_output = processor.batch_decode(
        [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0].strip()

    try:
      rubric = extract_json(raw_output)
      
      # --- Post-processing to prevent hallucinations shown in screenshot ---
      criteria = rubric.get("criteria", [])
      if not criteria:
          raise ValueError("No criteria generated")

      # 1. Remove duplicate descriptions
      seen = set()
      unique_criteria = []
      for c in criteria:
          desc = str(c.get("description", "")).lower().strip()
          if desc and desc not in seen:
              seen.add(desc)
              unique_criteria.append(c)
      
      # 2. Enforce mathematical consistency
      target_max = float(max_score) if max_score else float(rubric.get("max_score", 10))
      current_total = sum(float(c.get("points", 0)) for c in unique_criteria)
      
      if current_total != target_max and current_total > 0:
          # Scale points proportionally
          factor = target_max / current_total
          for c in unique_criteria:
              c["points"] = round(float(c.get("points", 0)) * factor, 1)
          
          # Final correction to ensure exact sum (fixes the 9.8 vs 10.0 issue)
          new_total = sum(c["points"] for c in unique_criteria)
          diff = round(target_max - new_total, 1)
          if diff != 0 and unique_criteria:
              unique_criteria[-1]["points"] = round(unique_criteria[-1]["points"] + diff, 1)
      
      # Final sync
      rubric["criteria"] = unique_criteria
      rubric["max_score"] = round(sum(float(c.get("points", 0)) for c in unique_criteria), 1)
      
      return rubric

    except (json.JSONDecodeError, ValueError, Exception) as e:
      print(f"Failed to process rubric: {e}. Raw output:\n", raw_output)
      # ---> FALLBACK DICTIONARY INSTEAD OF 'None' <---
      return {
          "question_id": "error_q",
          "max_score": max_score or 10,
          "criteria": [{"id": "c1", "description": "Manual grading required due to rubric generation failure.", "points": max_score or 10, "type": "conceptual"}]
>>>>>>> 15b1898f1ea7244db1b396e1e9d47837e0f8d22b
      }