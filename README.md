<div align="center">
  <img src="https://img.shields.io/badge/GradeOps-Vision-10b981?style=for-the-badge&labelColor=0a0f1a&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+PHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiByeD0iOCIgZmlsbD0iIzEwYjk4MSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTUlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSJ3aGl0ZSIgZm9udC1mYW1pbHk9IkludGVyIiBmb250LXdlaWdodD0iODAwIiBmb250LXNpemU9IjE4Ij5HPC90ZXh0Pjwvc3ZnPg==" alt="GradeOps Vision" height="38" />

  <h1>GRADEOPS VISION</h1>
  <h3>Agentic AI Exam Grading Pipeline with Human-in-the-Loop Review</h3>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" />
    <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" />
    <img src="https://img.shields.io/badge/PyTorch-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" />
    <img src="https://img.shields.io/badge/Qwen2.5--VL-3B-F9AB00?style=flat-square&logo=huggingface&logoColor=white" />
    <img src="https://img.shields.io/badge/LangGraph-Agentic-10b981?style=flat-square" />
    <img src="https://img.shields.io/badge/4--bit_Quantized-Local_GPU-8B5CF6?style=flat-square" />
    <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" />
  </p>

  <p>
    <strong>An end-to-end AI-powered system that reads handwritten exam papers, generates rubrics, grades with partial credit, detects plagiarism and compiles per-student reports. All running locally on consumer hardware with zero cloud API costs.</strong>
  </p>
</div>

---

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Key Results & Capabilities](#key-results--capabilities)
- [System Architecture](#system-architecture)
- [The Agentic LangGraph Pipeline](#the-agentic-langgraph-pipeline)
- [Technical Deep Dive](#technical-deep-dive)
- [Dashboard & UI Features](#dashboard--ui-features)
- [Cropping Studio](#cropping-studio)
- [Grading Pipeline Execution](#grading-pipeline-execution)
- [Results & Analytics Dashboard](#results--analytics-dashboard)
- [Student Reports](#student-reports)
- [Review Queue (Human-in-the-Loop)](#review-queue-human-in-the-loop)
- [Rubric Engine](#rubric-engine)
- [Plagiarism Detection](#plagiarism-detection)
- [Export & Reporting](#export--reporting)
- [Role-Based Access Control](#role-based-access-control)
- [API Reference](#api-reference)
- [Tech Stack](#tech-stack)
- [Installation & Quick Start](#installation--quick-start)
- [Project Structure](#project-structure)
- [Performance & Engineering Decisions](#performance--engineering-decisions)
- [Sandbox Mode](#sandbox-mode)

---

## The Problem

Grading handwritten exams at scale is one of the most time-consuming, error-prone and inconsistent tasks in education. A typical instructor spends **40-60 hours per semester** grading exams for a single course. The challenges include:

- **Inconsistency**: The same answer graded differently depending on fatigue, mood or ordering effects
- **No partial credit standardization**: Different graders apply different mental rubrics to the same question
- **Zero traceability**: Students receive a score with no explanation of *why* they lost marks
- **Plagiarism blindness**: Identical logical errors across students are nearly impossible to catch manually across 100+ papers
- **Scalability**: The process doesn't scale. Doubling the class size doubles the grading time

## The Solution

**GradeOps Vision** is an agentic AI grading pipeline that automates the entire workflow from scanned answer sheets to publishable grade reports. The system:

1. **Reads** handwritten answers using a Vision-Language Model (Qwen2.5-VL-3B-Instruct)
2. **Generates** structured grading rubrics with weighted criteria from the question text
3. **Grades** each answer against the rubric with partial credit and detailed justifications
4. **Verifies** every grade through an independent AI auditor node that catches hallucinations and mathematical errors
5. **Detects** plagiarism using semantic embeddings and shared error pattern analysis
6. **Compiles** per-student reports with question-wise breakdowns, error analysis and focus recommendations
7. **Escalates** low-confidence results to a human review queue where instructors can approve, override, or re-grade

The entire pipeline runs **locally** on consumer hardware using 4-bit quantized models. No data ever leaves the machine, ensuring complete **FERPA/GDPR compliance** and **zero API costs**.

---

## Key Results & Capabilities

| Capability | Detail |
|:---|:---|
| **OCR Engine** | Qwen2.5-VL-3B-Instruct with NF4 quantization, reads handwriting with LaTeX math preservation |
| **Rubric Generation** | AI-generated rubrics with configurable max scores, multi-criteria weighting (conceptual, computational, notation and presentation) |
| **Grading Accuracy** | Partial credit with step-by-step justification, equivalence handling (e.g., "Watts" = "W" = "watts") |
| **Hallucination Prevention** | 3-layer defense: equivalence checker, verification auditor node and auto-correction with human escalation |
| **Plagiarism Detection** | Semantic similarity via `all-MiniLM-L6-v2` embeddings + shared error axis correlation |
| **Pipeline Architecture** | 3-node LangGraph `StateGraph` (Rubric → Grader → Auditor) with typed state propagation |
| **Privacy** | 100% local execution, no cloud API calls, no data exfiltration. FERPA/GDPR compliant |
| **GPU Requirement** | Runs on 4GB VRAM consumer GPUs via BitsAndBytes 4-bit quantization with double quantization |
| **API Endpoints** | 28 RESTful endpoints covering auth, upload, cropping, grading, review, rubrics, export and sandbox |
| **Frontend** | Glassmorphism dashboard with animated particle canvas, staggered entrance animations and real-time pipeline visualization |

---

## System Architecture

```
                                    GRADEOPS VISION: SYSTEM ARCHITECTURE
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │                                    FRONTEND                                         │
    │   ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐  ┌────────────────┐   │
    │   │  Upload   │  │   Cropping   │  │ Pipeline │  │ Results │  │ Student Reports │   │
    │   │  Portal   │→ │   Studio     │→ │ Monitor  │→ │ & Stats │→ │ & Review Queue  │   │
    │   └──────────┘  └──────────────┘  └──────────┘  └─────────┘  └────────────────┘   │
    │         HTML5 / CSS3 (Glassmorphism) / Vanilla JavaScript / Canvas Particles        │
    └──────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │ REST API (28 endpoints)
    ┌──────────────────────────────────────┴──────────────────────────────────────────────┐
    │                              FASTAPI BACKEND                                        │
    │  ┌────────────┐  ┌───────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
    │  │  Auth/RBAC  │  │ Session Mgmt  │  │  Crop Engine │  │  Background Job Runner  │  │
    │  │  JWT+bcrypt │  │  SQLite/PG    │  │  OpenCV      │  │  Async Pipeline Exec    │  │
    │  └────────────┘  └───────────────┘  └──────────────┘  └───────────┬─────────────┘  │
    └────────────────────────────────────────────────────────────────────┼─────────────────┘
                                                                        │
    ┌───────────────────────────────────────────────────────────────────┴─────────────────┐
    │                         AGENTIC LANGGRAPH PIPELINE                                  │
    │                                                                                     │
    │   ┌──────────────────┐     ┌──────────────────┐     ┌───────────────────────┐      │
    │   │  RUBRIC FACTORY   │ ──→ │  GRADING NODE    │ ──→ │  VERIFICATION NODE    │      │
    │   │                   │     │                   │     │  (Auditor)            │      │
    │   │ • Reads question  │     │ • Cross-refs OCR  │     │ • Math consistency    │      │
    │   │ • Generates JSON  │     │   against rubric  │     │ • Score ≤ max_score   │      │
    │   │   rubric w/ max   │     │ • Partial credit  │     │ • Justification logic │      │
    │   │   score + criteria│     │ • Error axis tags  │     │ • Equivalence check   │      │
    │   │ • Scaling + dedup │     │ • Hallucination    │     │ • Auto score adjust   │      │
    │   │                   │     │   detection        │     │ • Escalation flag     │      │
    │   └──────────────────┘     └──────────────────┘     └───────────────────────┘      │
    │          ↑                          ↑                          ↑                     │
    │          │                          │                          │                     │
    │   Qwen2.5-VL-3B             Qwen2.5-VL-3B              Qwen2.5-VL-3B              │
    │   (4-bit NF4)               (4-bit NF4)                (4-bit NF4)                 │
    └─────────────────────────────────────────────────────────────────────────────────────┘
                                           │
    ┌──────────────────────────────────────┴──────────────────────────────────────────────┐
    │                           POST-PIPELINE ANALYSIS                                    │
    │  ┌──────────────────────┐  ┌─────────────────────┐  ┌───────────────────────────┐  │
    │  │  Plagiarism Detector  │  │  Student Report Gen  │  │  PDF / CSV Export Engine  │  │
    │  │  all-MiniLM-L6-v2    │  │  Error Aggregation   │  │  Jinja2 Templates         │  │
    │  │  Cosine Similarity   │  │  Focus Area Analysis │  │  Print-ready Reports      │  │
    │  └──────────────────────┘  └─────────────────────┘  └───────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## The Agentic LangGraph Pipeline

The grading pipeline is not a monolithic script. It is a **typed state graph** built with [LangGraph](https://github.com/langchain-ai/langgraph). Each node is an independent AI agent with a single responsibility and state flows through the graph via a typed `GradeOpsState` dictionary.

### Pipeline State Schema

```python
class GradeOpsState(TypedDict):
    # Inputs
    student_id: str
    question_text: str
    marking_scheme_text: Optional[str]
    transcription: str                    # From OCR engine

    # Generated by Rubric Factory
    rubric: dict                          # {max_score, criteria: [{id, description, points, type}]}

    # Output from Grading Node
    proposed_score: float
    justification: str                    # Step-by-step reasoning trace
    needs_review: bool                    # Confidence-based escalation flag
    error_axes: List[str]                 # ["computational", "conceptual", "notation", "presentation"]

    # Output from Verification Node
    verification_passed: Optional[bool]
    verification_feedback: Optional[str]
```

### Node 1: Rubric Factory (`src/rubric_factory.py`)

The Rubric Factory generates a structured JSON rubric from the question text. It accepts an optional `max_score` (set by the instructor in the Cropping Studio) and an optional marking scheme.

**What it does:**
- Sends the question text + max score to the Qwen2.5-VL model with a strict prompt template
- Receives a JSON rubric with `question_id`, `max_score` and an array of `criteria` objects
- Each criterion has a `description`, `points` value and `type` (conceptual / computational / notation / presentation)
- **Post-processing pipeline:**
  - Deduplicates criteria with identical descriptions
  - Proportionally scales all criteria points to match the target `max_score`
  - Applies a final correction to ensure the point sum is mathematically exact
- Falls back to a safe single-criterion rubric if the model output fails to parse

### Node 2: Grading Node (`src/grader.py`)

The Grading Node cross-references the student's OCR transcription against the rubric to assign a score with justification.

**What it does:**
- Receives the rubric and student transcription from the pipeline state
- Prompts the model to grade step-by-step, awarding partial credit for correct methodology even if the final answer is wrong
- Classifies errors into axes: `computational`, `conceptual`, `notation`, `presentation`
- **Equivalence handling**: the prompt explicitly instructs the model that:
  - Case differences are equivalent (`"Watts" = "watts" = "WATTS"`)
  - Symbol vs. word forms are equivalent (`"W" = "Watts"`, `"J" = "Joules"`)
  - Notation variants are equivalent (`"x^2" = "x²"`, `"1/2" = "0.5"`)
  - Minor spelling differences are equivalent (`"metre" = "meter"`)
- **Hallucination detection**: `_check_equivalence_hallucination()` catches cases where the model gives a zero score despite the student's answer semantically matching the rubric criteria. It auto-corrects the score and flags for human review.
- Retries up to 2 times on JSON parse failures before returning a safe fallback

### Node 3: Verification Node (`src/grader.py`)

The Verification Node is an independent AI auditor that reviews the Grading Node's output for consistency and correctness.

**What it checks:**
1. **Mathematical validity**: Does the proposed score exceed `max_score`? Is it negative?
2. **Justification coherence**: Does the reasoning logically support the awarded points?
3. **Equivalence audit**: Did the Grading Node incorrectly penalize a student for a valid notation variant?
4. **Score adjustment**: If the auditor detects an error, it can adjust the score and provide feedback
5. **Escalation**: Failed verifications automatically set `needs_review = True`, pushing the result to the human review queue

### Pipeline Execution Flow

```
                    ┌──────────────┐
                    │  Entry Point │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ create_rubric │ ── Generates JSON rubric from question text
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  grade_paper  │ ── Grades transcription against rubric
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ verify_grade  │ ── Audits score, justification and math
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │     END      │ ── Result stored in SQLite
                    └──────────────┘
```

The pipeline runs once per `(student, question)` pair. For 30 students and 4 questions, it executes 120 iterations, with each iteration performing 3 LLM inference passes (rubric is cached after the first student).

---

## Technical Deep Dive

### Vision-Language Model

| Specification | Value |
|:---|:---|
| Model | `Qwen/Qwen2.5-VL-3B-Instruct` |
| Parameters | 3 billion |
| Quantization | NF4 (4-bit) via BitsAndBytes |
| Double Quantization | Enabled: quantizes the quantization constants for further memory savings |
| Compute Dtype | `float16` |
| Max Pixel Budget | `512 * 28 * 28 = 401,408 pixels` per image |
| VRAM Requirement | ~4GB with 4-bit quantization |
| Loading Strategy | Lazy proxy pattern: model loads only on first inference call, not at server startup |
| Inference Mode | Deterministic (`do_sample=False`, `use_cache=True`) |

### Image Preprocessing Pipeline (`src/preprocess.py`)

Before OCR, every cropped answer image goes through a 4-stage preprocessing pipeline using OpenCV:

1. **Grayscale Conversion**: Convert BGR to single-channel grayscale (0–255)
2. **Gaussian Blur Denoising**: Light 3x3 Gaussian blur to reduce high-frequency noise while preserving stroke edges
3. **Adaptive Thresholding**: `ADAPTIVE_THRESH_GAUSSIAN_C` with block size 11, converts to pure black/white, eliminating shadows, uneven lighting and background artifacts
4. **Morphological Opening**: 2x2 kernel opening operation removes small noise artifacts (dots and specks) without affecting handwriting strokes

PDF documents are first converted to high-resolution images at **300 DPI** using PyMuPDF (`fitz`), supporting grayscale, RGB and RGBA source formats.

### Plagiarism Detection Engine (`src/integrity.py`)

The plagiarism detector uses a fundamentally different approach from traditional string-matching:
1. **Semantic Embedding**: Each student's OCR transcription is encoded using `all-MiniLM-L6-v2` (a sentence-transformer model) into a 384-dimensional embedding vector
2. **Cosine Similarity Matrix**: All pairwise similarities are computed between student transcriptions for the same question
3. **Error Axis Correlation**: The shared error axes between flagged pairs are identified (e.g., both students made the same conceptual error)
4. **Threshold**: Pairs exceeding 90% cosine similarity are flagged with:
   - The student pair identifiers
   - Confidence score (0.0–1.0)
   - List of shared error axes
   - Human-readable reason

This approach catches plagiarism that traditional methods miss: students who copy logic and structure but rephrase the words, or who make identical unusual errors.

### JSON Extraction & Healing (`src/grader.py`)

Since the Qwen model outputs free-form text (sometimes with markdown artifacts), a robust JSON extraction pipeline handles malformed outputs:

1. Strips markdown code fences (`` ```json ... ``` ``)
2. Locates the first `{` and last `}` to isolate the JSON block
3. Attempts strict parsing with `json.loads(strict=False)` to allow unescaped control characters
4. Falls back to regex-based newline escaping for common AI output errors
5. Retries the full inference up to 2 times on parse failures

---

## Dashboard & UI Features

The frontend is built with **vanilla JavaScript, HTML5 and CSS3** with no React, no Vue and no build tools. The UI uses a glassmorphism design language with:

- **Animated gradient mesh background**: 4 radial gradients with a slow 18-second drift animation
- **Floating particle canvas**: 22 particles with radial gradient sprites, mouse proximity interaction and automatic pause when the tab is hidden
- **Staggered entrance animations**: Cards and elements cascade in with blur-to-focus transitions on view switch
- **Button ripple effects**: Material Design-style ripple on every button click
- **Animated stat counters**: Numbers count up from 0 with cubic ease-out on dashboard load
- **Pipeline energy pulse**: Glowing orb that travels down a connecting line between pipeline steps during execution
- **Orbiting rings**: Dual concentric spinning rings around the active pipeline step indicator
- **Completion burst particles**: 10 particles explode radially from each step indicator on completion
- **Smooth page transitions**: View sections slide in with scale and blur animations
- **`prefers-reduced-motion` support**: All animations are disabled for users with motion sensitivity

---

## Cropping Studio

The Cropping Studio is a two-panel interface for mapping questions and answer regions on exam papers.

### Panel 1: Extract Questions
- Load the question paper on an interactive canvas with zoom controls
- Draw a rectangle around each question
- The system crops and runs OCR to extract the question text
- Questions are auto-assigned sequential IDs (Q1, Q2, Q3...)

### Panel 2: Map Answer Regions
- Load any student's answer sheet as a template
- Draw a rectangle around where each question's answer appears
- Link each crop region to a question from the dropdown
- **Set the max marks** for each question. This value is passed to the Rubric Factory and determines the total points the rubric should sum to
- Crop coordinates are saved as a template. The same regions are applied to every uploaded answer sheet

### How it works end-to-end
The coordinates define a spatial template: "Q1's answer is at position (x=120, y=340, w=600, h=200) on page 0." The pipeline then iterates through every uploaded answer sheet, crops the same region from each and grades what it finds. This requires all answer sheets to have the same layout, which is standard for most exam formats.

---

## Grading Pipeline Execution

When the instructor clicks **Run Grading Pipeline**, the system:

1. **Loads all coordinates** and auto-generates rubrics for each question (or uses saved rubrics if available)
2. **Iterates through every answer sheet**: for each sheet, it:
   - Derives the `student_id` from the filename (e.g., `student_101.png` → `student_101`)
   - Crops each question's answer region using the saved coordinates
   - Preprocesses the crop (grayscale → blur → threshold → morphological clean)
   - Uploads the cleaned crop to storage and runs OCR
   - Sends the transcription through the full LangGraph pipeline (Rubric → Grade → Verify)
   - Stores the result in SQLite with the rubric, score, justification, errors and verification status
3. **Runs plagiarism detection** across all student transcriptions
4. **Stores all results** in the database and navigates to the Results view

The pipeline runs as a background job with real-time status polling (2-second intervals). The frontend displays:
- Current step (Rubrics → Grading → Plagiarism Detection)
- Progress counter (e.g., "Processing 45/120...")
- Elapsed timer
- Animated pipeline visualization

---

## Results & Analytics Dashboard

The Results view provides comprehensive analytics computed from the grading results:

### Summary Statistics
- **Total Graded**: Number of `(student, question)` pairs processed
- **Average Score**: Mean proposed score across all results
- **Average Accuracy**: Mean verification accuracy
- **Review Required**: Count of results flagged for human review

### Score Distribution Histogram
- Visual bar chart showing how scores are distributed across all graded entries
- Hover tooltips show exact counts per bin
- Responsive gradient bars with glow effects

### Error Distribution
- Breakdown of error types across all results: `computational`, `conceptual`, `notation`, `presentation`
- Horizontal bar chart with color-coded error type indicators

### Per-Question Analytics
- For each question: average score, min/max range, graded count and common error patterns
- Visual progress bar showing the class performance percentage

### Full Results Table
- Sortable table with columns: Student | Question | Score | Accuracy | Errors | Review Status
- **Expandable rows**: click any row to see the AI's justification and the raw OCR transcription side by side
- **Search**: filter by student ID, question ID or justification text
- **Filter**: show all results, only items needing review or only passing results
- **Flagged rows**: results with low accuracy or review flags are highlighted with a red left border

---

## Student Reports

The Student Reports tab groups all grading results by student and provides a comprehensive per-student breakdown.

### For each student:
- **Header card**: Student ID, number of questions graded, total score, percentage and letter grade (A+ through F) displayed in a circular badge
- **Question-wise table** (expandable on click):
  - Question ID
  - Score / Max with progress bar
  - Error tags for that specific answer
  - Truncated AI feedback/justification
- **Areas to Focus On**: The system identifies the student's top 3 error categories and provides specific improvement tips:
  - `conceptual` → "Review core concepts and definitions"
  - `computational` → "Practice numerical calculations and formulas"
  - `notation` → "Pay attention to proper notation and symbols"
  - `presentation` → "Improve answer structure and clarity"
  - `reasoning` → "Strengthen logical reasoning and proof steps"
- **Error summary badges**: Aggregate count of each error type (e.g., "conceptual x3, notation x1")

### Search
- Real-time search bar filters students by ID as you type

---

## Review Queue (Human-in-the-Loop)

The Review Queue is the critical HITL component that ensures AI grades are never blindly published. Results enter the queue when:

- The OCR transcription contains `[?]` markers (uncertain handwriting)
- The verification node failed (score inconsistency)
- The equivalence hallucination detector auto-corrected a score
- The transcription is empty or extremely short

### For each review item:
- **Cropped answer image**: the actual handwriting snippet from the student's paper
- **OCR transcription**: what the AI read from the handwriting
- **Proposed score** with accuracy badge
- **AI justification**: the model's step-by-step reasoning
- **Error axes**: tagged error types
- **Rubric context**: max score and criteria

### Actions:
| Action | Shortcut | Effect |
|:---|:---|:---|
| **Approve** | `A` | Accepts the AI's proposed score as final |
| **Override** | `O` | Opens a prompt to enter a corrected score |
| **Re-grade** | `R` | Re-runs OCR and the full pipeline for this single answer |
| **Navigate** | `← →` | Move between review items |

### Progress tracking:
- Review progress bar shows how many items have been reviewed out of total
- Status indicators: `Pending`, `Approved`, `Overridden`
- Review decisions are persisted to the database via API

---

## Rubric Engine

The Rubric Editor gives instructors full control over grading criteria before or after running the pipeline.

### Manual Rubric Creation
- Select a question, set max score
- Add criteria rows with description, point value and type (conceptual / computational / notation / presentation)
- Save to the database. Saved rubrics override AI-generated ones in subsequent pipeline runs

### AI Rubric Generation
- Click **AI Generate** on any question
- The system sends the question text to the Qwen model with rubric generation instructions
- The generated rubric populates the editor for review and modification
- The instructor can adjust criteria, reweight points, or add missing criteria before saving

### Integration with Cropping Studio
- When mapping answer regions, the instructor sets a **max marks** value per question
- This value is passed to the Rubric Factory during pipeline execution
- The AI generates rubrics whose criteria sum to exactly the specified max score

---

## Plagiarism Detection

The plagiarism detector (`src/integrity.py`) uses **ReJump Collusion Detection**, a semantic similarity approach that goes beyond string matching.

### How it works:
1. All student transcriptions for each question are encoded into 384-dimensional vectors using the `all-MiniLM-L6-v2` sentence transformer
2. Pairwise cosine similarity is computed between all student pairs
3. Pairs exceeding the **90% similarity threshold** are flagged
4. For each flagged pair, the system identifies shared error axes. If two students made the same unusual error, the flag's confidence increases

### What it catches:
- Students who copy logic structure but rephrase words
- Identical mathematical approaches with minor surface variation
- Suspiciously correlated error patterns (e.g., both students make the same conceptual mistake)

### What it shows:
- Flagged student pairs with confidence percentage
- Shared error axes between the pair
- Human-readable reason for the flag

---

## Export & Reporting

### CSV Export
- One-click export of all grading results to CSV
- Columns: Student ID, Question ID, Score, Accuracy, Errors, Needs Review, Justification, Transcription

### PDF Report
- Full grade report rendered as a print-ready HTML page via Jinja2
- Organized by student with per-question breakdowns
- Each question shows: score/max, AI feedback, error tags and the raw OCR transcription
- Uses `@media print` CSS for clean print output
- Browser's native Print → Save as PDF

---

## Role-Based Access Control

GradeOps Vision enforces RBAC using JWT tokens and bcrypt-hashed passwords.

| Role | Permissions |
|:---|:---|
| **Instructor** | Upload exams, configure crop coordinates, run grading pipeline and review results |
| **TA (Teaching Assistant)** | Review queue only: approve, override or re-grade individual results |

- Authentication via `POST /api/auth/login` returns a JWT cookie
- All API endpoints verify the JWT and check role permissions before executing
- Registration via `POST /api/auth/register` with role assignment

---

## API Reference

GradeOps Vision exposes **28 RESTful endpoints** across 7 domains:

### Authentication (4 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/auth/register` | Register a new user with role |
| `POST` | `/api/auth/login` | Authenticate and receive JWT cookie |
| `POST` | `/api/auth/logout` | Clear authentication cookie |
| `GET` | `/api/auth/me` | Get current user profile |

### Upload & Configuration (4 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/exams/upload` | Upload question paper + answer sheets + optional marking scheme |
| `POST` | `/api/exams/{id}/questions/from-crop` | Extract question text from a crop region |
| `POST` | `/api/exams/{id}/crop/preview` | Preview a crop region and get coordinates |
| `POST` | `/api/exams/{id}/coordinates` | Save coordinate mappings with max scores |

### Pipeline Execution (3 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/exams/{id}/run` | Start the grading pipeline as a background job |
| `GET` | `/api/exams/{id}/job/{job_id}` | Poll pipeline job status and progress |
| `GET` | `/api/exams/{id}/preview` | Preview answer sheet pages |

### Results & Dashboard (2 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/api/exams/{id}/dashboard` | Full dashboard data with analytics, results and review queue |
| `GET` | `/api/exams/{id}/report` | Generate print-ready PDF grade report |

### Review (4 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/exams/{id}/review/{result_id}` | Submit review decision (approve/override) |
| `POST` | `/api/exams/{id}/review/{result_id}/approve` | Approve a grading result |
| `POST` | `/api/exams/{id}/review/{result_id}/override` | Override with a new score |
| `POST` | `/api/exams/{id}/regrade/{result_id}` | Re-run OCR and grading for a single result |

### Rubrics (4 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/exams/{id}/rubrics` | Save a rubric template |
| `GET` | `/api/exams/{id}/rubrics` | Get all saved rubric templates |
| `DELETE` | `/api/exams/{id}/rubrics/{question_id}` | Delete a rubric template |
| `POST` | `/api/exams/{id}/rubrics/{question_id}/generate` | AI-generate a rubric for a question |

### Sandbox & Utilities (4 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/api/sandbox/create` | Generate sandbox data from a preset |
| `POST` | `/api/sandbox/generate` | Generate custom sandbox data |
| `GET` | `/api/storage/{filename}` | Serve uploaded files |
| `GET` | `/health` | Health check |

### Pages (2 endpoints)
| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/` | Main dashboard (requires auth) |
| `GET` | `/login` | Login page |

---

## Tech Stack

| Layer | Technology | Purpose |
|:---|:---|:---|
| **Backend Framework** | FastAPI + Uvicorn | Async REST API server with automatic OpenAPI docs |
| **Database** | SQLite (dev) / PostgreSQL (prod) | Session, results, rubric and user storage |
| **Authentication** | python-jose (JWT) + passlib + bcrypt | Token-based auth with secure password hashing |
| **ML Model** | Qwen2.5-VL-3B-Instruct | Vision-language model for OCR, grading, rubric generation and verification |
| **Quantization** | BitsAndBytes (NF4, double quant) | 4-bit model compression for consumer GPU deployment |
| **Pipeline** | LangGraph + LangChain Core | Typed state graph for agentic multi-node pipeline |
| **Embeddings** | Sentence-Transformers (all-MiniLM-L6-v2) | Semantic embeddings for plagiarism detection |
| **Image Processing** | OpenCV + Pillow + PyMuPDF | PDF conversion, image preprocessing, crop extraction |
| **Cloud Storage** | Boto3 (AWS S3) / Local FS fallback | File upload with automatic fallback |
| **Frontend** | Vanilla JS + CSS3 + HTML5 | Zero-dependency glassmorphism dashboard |
| **Templating** | Jinja2 | Server-side HTML rendering for dashboard and PDF reports |
| **Data Validation** | Pydantic v2 | Request/response schema validation |

---

## Installation & Quick Start

### Prerequisites
- Python 3.10+
- NVIDIA GPU with 4GB+ VRAM (for local model inference)
- CUDA toolkit installed

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/gradeops-vision.git
cd gradeops-vision
```

### 2. Create virtual environment and install dependencies
```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. Environment variables (optional)
GradeOps runs locally out of the box with SQLite and local file storage. For cloud deployment:
```bash
cp .env.example .env
# Edit .env with your PostgreSQL / AWS S3 credentials
```

### 4. Start the server
```bash
python main_api.py
```

### 5. Open the dashboard
Navigate to **`http://localhost:8000`** in your browser.

Login with default credentials or register a new account. Use **Sandbox** mode to instantly generate test data and explore the full UI without uploading real exam papers.

---

## Project Structure

```
gradeops-vision/
├── main_api.py                  # FastAPI application: all 28 API endpoints, job runner, auth
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable reference
│
├── src/
│   ├── __init__.py
│   ├── ocr_engine.py            # Qwen2.5-VL model loading (lazy proxy) + OCR transcription
│   ├── grader.py                # Grading node + verification node + hallucination detection
│   ├── rubric_factory.py        # AI rubric generation with max_score + post-processing
│   ├── workflow.py              # LangGraph StateGraph wiring (3 nodes → END)
│   ├── state.py                 # GradeOpsState TypedDict definition
│   ├── integrity.py             # Plagiarism detection via semantic embeddings
│   ├── preprocess.py            # Image preprocessing (grayscale, threshold, morphology)
│   ├── storage.py               # S3 upload with local filesystem fallback
│   └── database.py              # SQLite/PostgreSQL schema, CRUD operations
│
├── static/
│   ├── css/index.css            # Glassmorphism dashboard styles + animations
│   └── js/app.js                # Frontend logic: views, charts, particles and pipeline animations
│
├── templates/
│   ├── index.html               # Main dashboard SPA template
│   ├── login.html               # Authentication page
│   └── report.html              # PDF grade report (Jinja2 + print CSS)
│
└── tests/
    ├── benchmark.py             # Performance benchmarking suite
    └── ocr_engine.py            # OCR accuracy tests
```

---

## Performance & Engineering Decisions

### Why local models instead of cloud APIs?
- **Privacy**: Student exam data is sensitive (FERPA/GDPR). Local execution means zero data exfiltration risk
- **Cost**: Cloud API calls for 120+ grading iterations would cost $5-15 per exam session. Local inference is free after the initial GPU investment
- **Latency**: No network round-trips. Model stays loaded in VRAM across iterations

### Why 4-bit quantization?
- Full-precision Qwen2.5-VL-3B requires ~12GB VRAM. NF4 quantization with double quantization reduces this to ~4GB
- NF4 (Normal Float 4-bit) is specifically designed for normally-distributed neural network weights, preserving more information than uniform 4-bit
- Double quantization quantizes the quantization constants themselves, saving an additional ~0.4 bits per parameter

### Why vanilla JavaScript instead of React/Vue?
- Zero build step: no webpack, no npm, no node_modules
- Single HTML file serves the entire SPA
- Canvas particle system and animations run directly on the main thread with `requestAnimationFrame`
- Total frontend is 3 files (HTML + CSS + JS) with no transpilation

### Why LangGraph instead of a sequential script?
- **Typed state propagation**: each node reads and writes to a typed dictionary, preventing field name typos and missing data
- **Independent nodes**: each node can be tested, replaced or disabled independently
- **Extensibility**: adding a new pipeline stage (e.g., a plagiarism check node) is one `add_node` + one `add_edge` call
- **Future-proofing**: LangGraph supports conditional edges, loops and parallel branches for more complex pipelines

### Graceful Fallbacks
| Component | Production | Development |
|:---|:---|:---|
| Database | PostgreSQL (via `DATABASE_URL` env var) | SQLite file (auto-created) |
| File Storage | AWS S3 (via `AWS_*` env vars) | Local `data/cloud_fallback/` directory |
| Model Loading | Lazy proxy: loads on first inference, not at server startup | Same |

---

## Sandbox Mode

Sandbox mode generates realistic simulated grading data for UI exploration and testing without running ML inference.

### Available Presets

| Preset | Students | Questions | Max Score | Description |
|:---|:---|:---|:---|:---|
| **Math** | 80 | 5 | 20 | Calculus I Midterm: derivatives, integrals and limits |
| **Science** | 60 | 4 | 15 | Physics: force, energy and circuits |
| **Humanities** | 40 | 3 | 25 | Essay-based: longer justifications and presentation errors |
| **Custom** | Configurable | Configurable | Configurable | Set your own parameters + toggle plagiarism/low-confidence items |

Each preset generates:
- Realistic student IDs (`student_000` through `student_N`)
- Plausible score distributions (not uniform random, follows a bell curve)
- Diverse error axes and justifications
- Simulated plagiarism flags between random student pairs
- Items flagged for review with low accuracy scores

---

<div align="center">
  <br/>
  <strong>Built to revolutionize academic grading, one pipeline at a time.</strong>
  <br/><br/>
  <sub>GradeOps Vision: Agentic AI Exam Grading | FastAPI | Qwen2.5-VL | LangGraph | Human-in-the-Loop</sub>
</div>
