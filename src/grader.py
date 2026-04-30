import re
import json
import torch
from ocr_engine import model, processor
from state import GradeOpsState

def extract_json(text: str) -> dict:
    """Hunts for a JSON object in a string, ignoring markdown and conversational filler."""
    # First, try to find the outermost curly braces
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: aggressive cleaning
    clean_text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def grading_node(state: GradeOpsState):
    transcription = state["transcription"]
    rubric = state["rubric"]
    needs_review = "[?]" in transcription or not transcription.strip()
    prompt = f"""
    Act as a Senior University Professor. Grade the STUDENT WORK against the RUBRIC provided.

    RUBRIC: {json.dumps(rubric)}
    STUDENT WORK: {transcription}

    GRADING RULES:
    1. Think step-by-step. Identify where the student's logic matches the rubric.
    2. Award partial credit for correct methodology even if the final answer is wrong.
    3. Categorize errors into: 'computational', 'conceptual', 'notation', or 'presentation'.

    Reply ONLY with this JSON:
    {{
        "proposed_score": <float>,
        "error_axes": [<list of error types>],
        "justification": "<detailed reasoning trace>"
    }}
    """

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt").to(model.device)

    max_retries = 2
    for attempt in range(max_retries):
        with torch.no_grad():
            generated_ids = model.generate(**inputs, max_new_tokens=1024, do_sample=False)

        raw_output = processor.batch_decode(
            [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0].strip()

        try:

            result = extract_json(raw_output)

            return {
                "proposed_score": float(result.get("proposed_score", 0)),
                "justification": result.get("justification", "No justification provided."),
                "error_axes": result.get("error_axes", []),
                "needs_review": needs_review
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"  [Warning] Attempt {attempt + 1} failed to parse JSON. Retrying...")
            continue  # Try again

    # If all retries fail, return the safe fallback
    return {
        "proposed_score": 0,
        "justification": f"SYSTEM ERROR: AI response could not be parsed after {max_retries} attempts. Manual review needed. Raw output: {raw_output[:100]}...",
        "error_axes": [],
        "needs_review": True
    }
