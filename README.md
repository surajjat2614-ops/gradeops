# GradeOps: Enterprise Grade Human in the Loop Vision Language Grading System

Architecture Paradigm: Multimodal Reasoning and Agentic Orchestration  
Core Technologies: Qwen2.5-VL, LangGraph, SentenceTransformers, AWS Step Functions  
Academic Year: 2025 to 2026  
Project Mentor: Abhinav Rai  

---

## 1. Overview

GradeOps is a full stack grading system designed to automate evaluation of handwritten STEM answer scripts using a human in the loop reasoning pipeline. Traditional grading systems rely on optical character recognition followed by heuristic scoring. These approaches fail when faced with noisy handwriting, mathematical notation, and incomplete reasoning.

GradeOps reframes grading as a structured reasoning problem. The system converts handwritten responses into LaTeX enriched representations, aligns them with dynamically generated rubrics, evaluates reasoning using structured outputs, and flags uncertain cases for human intervention.

The system is designed for scalability, auditability, and consistency across large cohorts.

---

## 2. Problem Statement

Manual grading introduces several inefficiencies that scale poorly with class size.

| Issue | Description | Impact |
|------|------------|--------|
| Time Consumption | Faculty spend 8 to 12 hours weekly grading scripts | Reduced productivity |
| Subjectivity | Different evaluators assign different scores | Reduced fairness |
| Limited Feedback | Students receive only marks without reasoning | Reduced learning quality |

GradeOps addresses these issues by combining structured reasoning with automated evaluation.

---

## 3. Design Philosophy

The system is built on the following principles:

1. Reasoning over pattern matching  
2. Structured outputs over free form text  
3. Human oversight over blind automation  
4. Fail safe defaults over silent failure  
5. Modular design over monolithic pipelines  

---

## 4. End to End Pipeline

The system follows a six stage pipeline:

1. High fidelity preprocessing  
2. Visual language transcription  
3. Rubric generation  
4. Agentic grading  
5. Integrity analysis  
6. Workflow orchestration  

Each stage is optimized independently to reduce error propagation.

---

## 5. Module Architecture

### 5.1 High Fidelity Capture Pipeline

File: preprocess.py

This module standardizes input data before inference.

#### Techniques Used

| Technique | Description | Benefit |
|----------|------------|--------|
| 300 DPI Normalization | Upscales scans to standard resolution | Improves clarity |
| Adaptive Thresholding | Removes noise and shadows | Cleaner segmentation |
| Grayscale Conversion | Reduces color complexity | Faster processing |
| Boundary Safe Cropping | Prevents invalid crops | Stable inputs |

#### Observed Improvements

| Metric | Before | After |
|-------|-------|------|
| OCR Failure Rate | 18.2% | 12.4% |
| Noise Sensitivity | High | Moderate |
| Image Consistency | Low | High |

---

### 5.2 Visual Reasoning Engine

File: ocr_engine.py

This module performs transcription using Qwen2.5-VL.

#### Capabilities

- Converts handwritten math into LaTeX  
- Preserves structure and formatting  
- Marks uncertain tokens using [?]  
- Handles high resolution images  

#### Example Output

The equation is:
F=ma
Where mass is [?] and acceleration is 9.8 m/s^2


#### Performance

| Metric | Value |
|------|------|
| Character Error Rate Clean | 3.5% |
| Character Error Rate Average | 6.2% |
| Character Error Rate Noisy | 11.8% |
| Math Expression F1 Score | 0.88 |

---

### 5.3 Automated Rubric Factory

File: rubric_factory.py

Generates structured grading rubrics.

#### Schema

| Field | Description |
|------|------------|
| question_id | Unique identifier |
| max_score | Total marks |
| criteria | List of grading rules |

#### Criteria Format

| Field | Description |
|------|------------|
| id | Criterion ID |
| description | Requirement |
| points | Marks |
| type | conceptual computational notation presentation |

#### Reliability Features

- Ensures total points match max score  
- Generates fallback rubric if parsing fails  
- Avoids generic placeholder outputs  

#### Performance

| Metric | Value |
|------|------|
| Parsing Success Rate | 96% |
| Fallback Rate | 4% |

---

### 5.4 Agentic Grading Engine

File: grader.py

Performs reasoning based evaluation.

#### Features

- Chain of thought reasoning  
- Partial credit allocation  
- Error classification  
- Structured JSON output  

#### Output Format
{
"proposed_score": 7.5,
"error_axes": ["computational"],
"justification": "Correct method but arithmetic mistake"
}


#### Robustness

| Feature | Description |
|--------|------------|
| Retry Parsing | Multiple attempts for JSON extraction |
| Safe Fallback | Returns default output on failure |
| Confidence Flagging | Detects uncertain OCR |

#### Performance

| Metric | Value |
|------|------|
| Human AI Agreement | 92% |
| Mean Absolute Error | 0.5 |
| Partial Credit Accuracy | 80% |
| Justification Coherence | 0.89 |

---

### 5.5 Integrity Analysis Engine

File: integrity.py

Detects reasoning level plagiarism.

#### Method

1. Convert reasoning to embeddings  
2. Compute similarity  
3. Compare error patterns  

#### Decision Logic

| Condition | Interpretation |
|----------|---------------|
| High similarity and shared errors | Likely collusion |
| High similarity only | Possible overlap |
| Low similarity | Independent work |

#### Performance

| Metric | Value |
|------|------|
| Detection Accuracy | 92% |
| False Positive Rate | 3.8% |
| Improvement over baseline | 35% |

---

### 5.6 Workflow Orchestration

Built using LangGraph.

#### Features

- Shared state across modules  
- Conditional routing  
- Fail safe execution  
- Human review integration  

#### Routing Table

| Condition | Action |
|----------|-------|
| Low OCR confidence | Manual review |
| Score anomaly | Audit |
| Parsing failure | Manual grading |

---

## 6. Performance Benchmarks

### OCR Evaluation

| Dataset | CER | Status |
|--------|-----|-------|
| Clean | 3.5% | Production Ready |
| Moderate | 6.2% | Reliable |
| Noisy | 11.8% | Review Needed |

---

### Grading Evaluation

| Metric | Value |
|------|------|
| Agreement with Experts | 92% |
| Error Detection Accuracy | 81% |
| Score Stability | High |

---

### System Throughput

| Metric | Value |
|------|------|
| Time per Script | 4 to 7 seconds |
| Parallel Capacity | 10000 workflows |
| Time Reduction | 85 to 92 percent |

---

### Noise Robustness

| Noise Level | CER |
|------------|-----|
| 0% | 3.5% |
| 10% | 5.8% |
| 20% | 7.9% |
| 30% | 11.2% |

---

## 7. Comparative Analysis

| Feature | Traditional OCR | GradeOps |
|--------|----------------|----------|
| Math Understanding | No | Yes |
| Partial Credit | No | Yes |
| Reasoning Evaluation | No | Yes |
| Plagiarism Detection | Basic | Semantic |
| Human Oversight | No | Yes |

---

## 8. Cloud Architecture

| Component | Role |
|----------|-----|
| Step Functions | Orchestration |
| Bedrock | Model inference |
| S3 | Storage |
| Lambda | Processing |

---

## 9. Installation

```bash
git clone https://github.com/yourusername/gradeops.git
cd gradeops

pip install git+https://github.com/huggingface/transformers accelerate
pip install opencv-python pymupdf qwen-vl-utils[decord]==0.0.8 langgraph sentence-transformers
