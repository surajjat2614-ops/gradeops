
import json
import torch
from ocr_engine import model, processor
from state import GradeOpsState  

def grading_node(state: GradeOpsState):
    transcription = state["transcription"]
    rubric = state["rubric"]

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

    with torch.no_grad():  
        generated_ids = model.generate(**inputs, max_new_tokens=1024, do_sample=False)

    raw_output = processor.batch_decode(
        [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0].strip()  
    result = json.loads(raw_output)

    # Confidence gate — flag for review if transcription has [?] or is empty
    needs_review = "[?]" in transcription or not transcription.strip()

    return {
        "proposed_score": result["proposed_score"],
        "justification": result["justification"],
        "error_axes": result["error_axes"],
        "needs_review": needs_review
    }