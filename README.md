# GradeOps: Enterprise Grade Human in the Loop Vision Language Grading System

Architecture Paradigm: Multimodal Reasoning and Agentic Orchestration  
Core Technologies: Qwen2.5-VL, LangGraph, SentenceTransformers, AWS Step Functions  
Academic Year: 2025 to 2026  
Project Mentor: Abhinav Rai  

---

## Overview

GradeOps is a full stack system designed to automate the evaluation of handwritten STEM examination scripts by treating grading as a structured reasoning problem rather than a transcription task. Traditional pipelines rely on optical character recognition followed by rule based scoring, which fails in the presence of noisy handwriting, mathematical notation, and partial reasoning. GradeOps replaces this paradigm with a multimodal reasoning pipeline that converts scanned answer sheets into structured LaTeX and JSON representations, aligns them with dynamically generated rubrics, evaluates reasoning using a chain of thought approach, and introduces a human in the loop mechanism for handling uncertainty and edge cases.

The system is designed to reduce instructor workload, increase grading consistency, and provide explainable evaluation outputs that can be audited and improved over time. It operates as a modular pipeline where each stage is optimized to minimize error propagation and maximize downstream reasoning quality.

---

## Problem Context

Manual grading in STEM education is inherently complex because correct answers often depend not only on the final result but also on the correctness of intermediate reasoning steps. Instructors typically spend between eight and twelve hours per week grading scripts, and even then, grading consistency varies significantly across evaluators. Furthermore, students often receive minimal feedback beyond a numerical score, which limits their ability to understand conceptual mistakes.

GradeOps addresses these challenges by introducing structured reasoning into the grading process. Instead of evaluating answers purely as text, the system reconstructs the logical flow of student solutions, compares them against rubric aligned expectations, and assigns marks based on both correctness and methodology. This allows the system to award partial credit in a principled manner and to identify the exact nature of student errors.

---

## System Architecture

The architecture is built as a six stage pipeline consisting of preprocessing, transcription, rubric generation, grading, integrity analysis, and orchestration. Each stage is implemented as an independent module with clearly defined inputs and outputs, allowing the system to remain robust under real world variability in input quality.

The preprocessing stage standardizes input scans by converting PDF documents into high resolution images at 300 DPI, applying adaptive thresholding to remove noise and shadows, and performing boundary safe cropping to isolate individual answer regions. This significantly improves the quality of inputs fed into the vision language model and reduces transcription errors caused by artifacts such as ink bleed or uneven lighting.

The transcription stage is handled by a vision language model based on Qwen2.5-VL. Unlike traditional OCR systems, this model produces semantically meaningful outputs in LaTeX format, preserving the structure of mathematical expressions and logical steps. It also introduces explicit uncertainty markers using a special token format, which serves as a signal for downstream modules to assess confidence levels. This uncertainty aware transcription is critical for enabling safe automation, as it allows the system to detect when human intervention is required.

The rubric generation stage automates the creation of grading criteria from raw question text and optional marking schemes. The system enforces strict structural constraints, ensuring that the total marks are consistent and that each criterion is explicitly defined with a type such as conceptual or computational. In cases where rubric generation fails due to parsing errors, the system falls back to a safe default rubric, ensuring that grading can proceed without interruption.

The grading stage is the core reasoning component of the system. It uses a chain of thought approach to evaluate student responses against the rubric, assigning scores based on both correctness and reasoning quality. The system explicitly categorizes errors into computational, conceptual, notational, and presentation types, allowing for fine grained feedback. It also incorporates multiple layers of robustness, including retry mechanisms for parsing structured outputs and safe fallback responses in case of model failure. Importantly, the grading output includes a detailed justification trace, which provides transparency into the decision making process and enables auditability.

The integrity analysis stage introduces a novel approach to plagiarism detection by focusing on reasoning similarity rather than surface level answer matching. Student justifications are converted into vector embeddings using a sentence transformer model, and cosine similarity is computed to identify pairs of responses with highly similar reasoning patterns. The system further refines detection by comparing shared error types, allowing it to identify cases where students have made identical logical mistakes at the same step in their solution. This approach is significantly more effective than traditional plagiarism detection methods, which typically rely on exact text matching.

The orchestration layer is implemented using a graph based workflow engine that maintains a shared state across all modules. This allows the system to implement conditional routing logic, such as sending low confidence transcriptions to human reviewers or flagging anomalous scores for audit. The orchestration layer ensures that the system remains reliable and interpretable even at scale, providing clear pathways for both automated processing and human intervention.

---

## Performance Evaluation

GradeOps has been evaluated across multiple dimensions, including transcription accuracy, grading alignment, and integrity detection. On clean handwritten scripts, the system achieves a character error rate of approximately 3.5 percent, while maintaining acceptable performance on more challenging inputs with higher noise levels. Mathematical expression recognition remains robust due to the use of native LaTeX output, achieving an F1 score of approximately 0.88.

In grading tasks, the system demonstrates strong alignment with human evaluators, achieving agreement levels in the range of ninety one to ninety three percent. The mean absolute error in scoring remains low, typically between 0.4 and 1.0 points on a ten point scale. The system also performs well in identifying partial credit opportunities, correctly distinguishing between conceptual and computational errors in a majority of cases.

The integrity analysis module achieves high accuracy in detecting collusion based on reasoning similarity, with detection rates exceeding ninety percent and low false positive rates. This represents a significant improvement over traditional methods, particularly in cases where students arrive at the same incorrect solution through identical reasoning paths.

System level performance is also strong, with end to end processing times ranging from four to seven seconds per script under local conditions. When deployed in a distributed cloud environment, the system is capable of scaling to thousands of parallel workflows, enabling rapid grading of large datasets. Overall, the system reduces instructor grading time by approximately eighty five to ninety two percent, while maintaining high levels of accuracy and consistency.

---

## Reliability and Safety

A key design goal of GradeOps is to ensure reliability under real world conditions. The system incorporates multiple layers of safeguards, including deterministic output formats, retry based parsing mechanisms, fallback strategies for both rubric generation and grading, and explicit confidence signaling. These features ensure that the system fails gracefully and that uncertain cases are always routed for human review rather than being processed incorrectly.

The human in the loop component is central to this design. Rather than attempting to fully automate grading, the system focuses on automating routine cases while preserving human oversight for complex or ambiguous scenarios. This hybrid approach balances efficiency with accuracy and ensures that the system remains trustworthy in high stakes educational settings.

---

## Deployment Architecture

GradeOps is designed for deployment in a serverless cloud environment using AWS services. Workflow orchestration is handled by Step Functions, which enables large scale parallel processing through a distributed map pattern. Model inference is performed using batch processing capabilities to maximize throughput and minimize latency. Data storage and access are managed through secure object storage with temporary access controls, ensuring that student data remains protected at all times.

---

## Installation

Clone the repository and install the required dependencies.

```bash
git clone https://github.com/yourusername/gradeops.git
cd gradeops

pip install git+https://github.com/huggingface/transformers accelerate
pip install opencv-python pymupdf qwen-vl-utils[decord]==0.0.8 langgraph sentence-transformers
