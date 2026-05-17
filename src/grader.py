import re
import json
import torch
from src.ocr_engine import model, processor
from src.state import GradeOpsState

def extract_json(text: str) -> dict:
    """Hunts for a JSON object in a string, ignoring markdown and conversational filler."""
    # Aggressive cleaning of markdown artifacts seen in screenshots
    text = text.replace("```json", "").replace("```", "").strip()

    # Locate the JSON block
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")

    candidate = text[start:end+1]

    try:
        # strict=False allows unescaped control characters
        return json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        # AI often fails to escape double quotes inside strings.
        # This is a heuristic to escape quotes that aren't followed by a colon (keys)
        # or preceded by a brace/comma (start of key/value).
        # We'll try common string-based healing.
        cleaned = re.sub(r'(?<!\\)\n', r'\\n', candidate) # Raw newlines

        # Last resort: try to find common key-value patterns and fix strings
        try:
            return json.loads(cleaned, strict=False)
        except:
             raise


def _normalize(text):
    """Lowercase, strip punctuation/whitespace for fuzzy comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _check_equivalence_hallucination(transcription, rubric, proposed_score, justification):
    """Detect when the model gave 0 but the student clearly answered correctly.

    Returns (corrected_score, corrected_justification, was_corrected).
    """
    max_score = float(rubric.get("max_score", 10))
    if proposed_score > max_score * 0.15:
        return proposed_score, justification, False

    norm_trans = _normalize(transcription)
    if not norm_trans:
        return proposed_score, justification, False

    hallucination_phrases = [
        "does not match", "is incorrect", "should be corrected",
        "lacks the necessary", "does not meet", "fails to match",
    ]
    justification_lower = justification.lower()
    has_hallucination_language = any(p in justification_lower for p in hallucination_phrases)
    if not has_hallucination_language:
        return proposed_score, justification, False

    criteria = rubric.get("criteria", [])
    for criterion in criteria:
        desc = criterion.get("description", "")
        desc_words = re.findall(r'[a-zA-Z]{3,}', desc)
        for word in desc_words:
            if _normalize(word) in norm_trans:
                corrected = max_score
                note = (
                    f"[AUTO-CORRECTED] Original score was {proposed_score}. "
                    f"The model hallucinated a false distinction — the student's answer "
                    f"'{transcription.strip()}' semantically matches the rubric criterion "
                    f"'{desc[:80]}'. Score corrected to {corrected}. Flagged for human review."
                )
                return corrected, note, True

    return proposed_score, justification, False

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
    4. EQUIVALENCE — these are ALL correct and MUST receive full marks:
       - Case differences: "Watts" = "watts" = "WATTS"
       - Symbol vs word: "W" = "Watts" = "watt", "J" = "Joules", "m/s" = "meters per second"
       - Notation variants: "x^2" = "x²", "1/2" = "0.5", "delta" = "Δ"
       - Minor spelling: "metre" = "meter", "colour" = "color"
       - Phrasing: "force equals mass times acceleration" = "F = ma"
       NEVER mark an answer wrong just because it uses a different but equivalent form.
       If the MEANING is correct, the answer is correct. Only flag 'notation' errors for genuinely wrong notation, not stylistic differences.
    5. IMPORTANT: In your JSON response, ensure all double quotes inside strings are escaped with a backslash (\\").

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
            generated_ids = model.generate(**inputs, max_new_tokens=1024, do_sample=False, use_cache=True)

        raw_output = processor.batch_decode(
            [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0].strip()

        try:

            result = extract_json(raw_output)

            score = float(result.get("proposed_score", 0))
            justification = result.get("justification", "No justification provided.")
            error_axes = result.get("error_axes", [])

            score, justification, was_corrected = _check_equivalence_hallucination(
                transcription, rubric, score, justification
            )
            if was_corrected:
                error_axes = []
                needs_review = True

            return {
                "proposed_score": score,
                "justification": justification,
                "error_axes": error_axes,
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

def verification_node(state: GradeOpsState):
    """Reviews the proposed score and justification against the rubric to catch hallucinations."""
    if "SYSTEM ERROR:" in state.get("justification", ""):
        return {"verification_passed": False, "verification_feedback": "Skipped verification due to previous system error."}

    prompt = f"""
    Act as a Senior Auditor. Verify the following AI-generated grading result.

    RUBRIC: {json.dumps(state["rubric"])}
    STUDENT WORK: {state["transcription"]}
    AI PROPOSED SCORE: {state["proposed_score"]}
    AI JUSTIFICATION: {state["justification"]}

    TASK:
    1. Check if the score is mathematically possible given the rubric (e.g., does it exceed max_score?).
    2. Check if the justification logically supports the awarded points.
    3. If there is a major discrepancy, fail the verification.
    4. EQUIVALENCE: Do NOT fail verification because of case, symbol vs word, or formatting differences.
       "Watts" = "watts" = "W", "Joules" = "J", "m/s" = "meters per second" are ALL equivalent.
       If the AI grader penalized a correct answer due to notation style, you MUST adjust the score UP and pass verification.

    Reply ONLY with this JSON:
    {{
        "verification_passed": <bool>,
        "feedback": "<reasoning for pass/fail>",
        "adjusted_score": <float or null>
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
        result = extract_json(raw_output)
        passed = result.get("verification_passed", True)
        feedback = result.get("feedback", "No feedback provided.")
        adjusted_score = result.get("adjusted_score")

        update = {
            "verification_passed": passed,
            "verification_feedback": feedback
        }

        if adjusted_score is not None and passed:
             update["proposed_score"] = float(adjusted_score)

        if not passed:
            update["needs_review"] = True

        return update

    except Exception as e:
        return {
            "verification_passed": True,
            "verification_feedback": f"Verification system error: {str(e)}. Defaulting to PASS."
        }