from workflow import build_grading_graph
from integrity import detect_rejump_collusion

# 1. Setup Class Submissions
submissions = [
    {"student_id": "std_01", "transcription": "Step 1: x=5. Step 2: y=10. [Computational Error]"},  # Suspicious
    {"student_id": "std_02", "transcription": "Step 1: x=5. Step 2: y=10. [Computational Error]"},  # Suspicious
    {"student_id": "std_03", "transcription": "Step 1: x=5. Step 2: y=12. Correct result."}
]

app = build_grading_graph()
cohort_results = []  

print(" Starting Batch Grading...")
for sub in submissions:
    result = app.invoke({
        "transcription"       : sub["transcription"],
        "question_text"       : "Solve for y...",
        "marking_scheme_text" : "5 marks for..."
    })
    result["student_id"] = sub["student_id"]
    cohort_results.append(result)

# 2. Run ReJump Plagiarism Detection
plagiarism_flags = detect_rejump_collusion(cohort_results)
print(f" Detected Collusion: {plagiarism_flags}")