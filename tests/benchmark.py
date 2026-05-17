from nltk import edit_distance
from ocr_engine import transcribe_snippet

def calculate_cer(reference_text, ai_output):

     # Normalize case before comparing
    reference_text = reference_text.lower().strip()
    ai_output = ai_output.lower().strip()

    # CER = Edit Distance / Total Reference Characters
    dist = edit_distance(reference_text, ai_output)
    cer = dist / max(len(reference_text), 1)
    
    # Target for high-stakes grading is CER < 0.15
    status = "READY" if cer < 0.15 else "RETRY PREPROCESSING"
    return {"cer": cer, "status": status}

# Example usage for your "December 2001" snippet
ground_truth = "December 2001 Parliamentary Attack The security to our temple of democracy was woefully inadequate, even after many warnings received from international security agencies of potential attacks on parliament. Though it did not succeed, the attack, as it was meant to be, but the fact that the terrorists had penetrated the first two barriers and were thwarted only by the extreme bravery and devotion to duty of two police officers in the final ring. "
prediction = transcribe_snippet("C://Users/hrima/gradeops-vision/data/snippets/page_0_question_2.png")
result = calculate_cer(ground_truth, prediction)
print(result)