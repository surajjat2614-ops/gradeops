<<<<<<< HEAD
from __future__ import annotations

import os
import re
import asyncio
import threading
from dotenv import load_dotenv
load_dotenv()
import bcrypt
from jose import jwt, JWTError
import datetime
import base64
import shutil
import uuid
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

from src import database as db
from src import storage as cloud_storage
from src.integrity import detect_rejump_collusion
from src.ocr_engine import transcribe_snippet
from src.preprocess import clean_for_ocr, extract_snippet, pdf_to_images
from src.workflow import build_grading_graph

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SNIPPETS_DIR = DATA_DIR / "snippets"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
USERS_FILE = DATA_DIR / "users.json"

for required_dir in (UPLOADS_DIR, SNIPPETS_DIR, TEMPLATES_DIR, DATA_DIR, STATIC_DIR):
    required_dir.mkdir(parents=True, exist_ok=True)

db.init_db()
db.migrate_users_from_json(USERS_FILE)

app = FastAPI(title="GradeOps Vision Portal")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
grading_pipeline = build_grading_graph()

grading_jobs: dict[str, dict[str, Any]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROLE_PERMISSIONS = {
    "instructor": {"upload", "configure", "grade", "review"},
    "ta": {"review"},
}


SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# to remove th active_sessions



class CoordinateItem(BaseModel):
    question_id: str = Field(..., min_length=1)
    page_index: int = Field(..., ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)
    question_text: str = Field(..., min_length=1)
    marking_scheme: str | None = None
    max_score: float | None = None


class ConfigurePayload(BaseModel):
    coordinates: list[CoordinateItem]


class QuestionCropPayload(BaseModel):
    page_index: int = Field(..., ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)


class CropPreviewPayload(BaseModel):
    source: str = Field(..., pattern="^(question|answer)$")
    page_index: int = Field(..., ge=0)
    sheet_index: int = Field(0, ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)
    clean: bool = False


def _current_user(request: Request) -> dict[str, str]:
    token = request.cookies.get("gradeops_session")
    if not token:
        raise HTTPException(status_code=401, detail="Please log in.")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Session invalid.")

    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Session invalid.")
    return {"username": username, "role": user["role"]}


def _check_permission(role: str, action: str) -> None:
    if action not in ROLE_PERMISSIONS.get(role, set()):
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot perform '{action}'")


def _save_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload file must have a filename.")
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
    return cloud_storage.upload_file(file.file, clean_name, file.content_type)

def _make_session_id(label: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:30]
    short = uuid.uuid4().hex[:6]
    return f"{slug}-{short}" if slug else short

def _clean_student_id(sid: str) -> str:
    if len(sid) > 33 and sid[32] == '_':
        return sid[33:]
    return sid

def _images_from_path(file_path: str) -> list[np.ndarray]:
    if not file_path:
        # Sandbox or empty session fallback
        dummy = np.ones((800, 600, 3), dtype=np.uint8) * 240
        cv2.putText(dummy, "SANDBOX MODE", (150, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)
        cv2.putText(dummy, "(No images uploaded)", (140, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 1)
        return [dummy]

    # Downloading from the cloud if necessary
    local_path = cloud_storage.download_to_local_temp(file_path)

    ext = Path(local_path).suffix.lower()
    if ext == ".pdf":
        return pdf_to_images(local_path)

    # First, trying the OpenCV direct decode which works for most raster formats.
    img = cv2.imread(local_path)
    if img is not None:
        return [img]

    # Fallback via PIL for less common but still image-like inputs.
    try:
        pil = Image.open(file_path).convert("RGB")
        pil_np = np.array(pil)
        bgr = cv2.cvtColor(pil_np, cv2.COLOR_RGB2BGR)
        return [bgr]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unreadable file format: {Path(file_path).name}",
        ) from exc


def _encode_png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode preview image")
    return encoded.tobytes()


def _encode_png_base64(image: np.ndarray) -> str:
    return base64.b64encode(_encode_png_bytes(image)).decode("utf-8")


def _score_accuracy(result: dict[str, Any], transcription: str) -> float:
    confidence = 0.85
    if "[?]" in transcription:
        confidence -= 0.35
    if result.get("needs_review"):
        confidence -= 0.2
    if not result.get("justification"):
        confidence -= 0.15
    return round(max(0.0, min(1.0, confidence)), 2)


def _validate_non_empty_crop(crop: np.ndarray, context: str) -> None:
    if crop is None or crop.size == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The selected {context} region is empty. "
                "Please draw the crop box fully inside the page."
            ),
        )


def _sanitize_crop_box(image: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int, bool]:
    img_h, img_w = image.shape[:2]
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(x + w, img_w)
    y1 = min(y + h, img_h)
    adjusted = (x0 != x) or (y0 != y) or (x1 != x + w) or (y1 != y + h)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0), adjusted


def _resolve_preview_target(session: dict[str, Any], source: str, sheet_index: int) -> str:
    if source == "question":
        return session["question_paper_path"]
    sheets = session["answer_sheet_paths"]
    if sheet_index >= len(sheets):
        raise HTTPException(status_code=400, detail="Invalid sheet_index")
    return sheets[sheet_index]


def _extract_questions_from_text(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    questions: list[dict[str, str]] = []
    current_qid = None
    current_chunks: list[str] = []

    def _flush() -> None:
        nonlocal current_qid, current_chunks
        if current_qid and current_chunks:
            questions.append({"question_id": current_qid, "question_text": " ".join(current_chunks).strip()})
        current_qid = None
        current_chunks = []

    for line in lines:
        lowered = line.lower()
        if lowered.startswith("q") and ":" in line:
            _flush()
            prefix, rest = line.split(":", 1)
            qnum = "".join(ch for ch in prefix if ch.isdigit()) or str(len(questions) + 1)
            current_qid = f"q{qnum}"
            current_chunks.append(rest.strip())
            continue
        if line[:2].isdigit() and (line[2:3] in [".", ")"]):
            _flush()
            qnum = "".join(ch for ch in line.split(maxsplit=1)[0] if ch.isdigit()) or str(len(questions) + 1)
            remainder = line[line.find(".") + 1 :] if "." in line else line[line.find(")") + 1 :]
            current_qid = f"q{qnum}"
            current_chunks.append(remainder.strip())
            continue
        if current_qid is None:
            current_qid = f"q{len(questions) + 1}"
        current_chunks.append(line)

    _flush()
    return questions


def _next_question_id(existing_questions: list[dict[str, str]]) -> str:
    if not existing_questions:
        return "q1"
    nums = []
    for q in existing_questions:
        qid = str(q.get("question_id", ""))
        digits = "".join(ch for ch in qid if ch.isdigit())
        if digits:
            nums.append(int(digits))
    return f"q{(max(nums) + 1) if nums else (len(existing_questions) + 1)}"


@app.get("/", response_class=HTMLResponse)
async def portal_home(request: Request):
    try:
        user = _current_user(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "user": user},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@app.post("/api/auth/register")
async def register(username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    role = role.lower().strip()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Role must be instructor or ta.")
    if db.user_exists(username):
        raise HTTPException(status_code=400, detail="Username already exists.")
    # Using the bcrypt for hashing
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.create_user(username, hashed, role)
    return {"message": "Registered successfully."}


@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)
    # Support legacy sha256 for existing test users or bcrypt
    is_valid = False
    if user:
        if len(user["password_hash"]) == 64 and not user["password_hash"].startswith("$"):
            import hashlib
            if user["password_hash"] == hashlib.sha256(password.encode("utf-8")).hexdigest():
                is_valid = True
        else:
            # Using bcrypt directly
            try:
                is_valid = bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8'))
            except Exception:
                is_valid = False

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    expire = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    token = jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    response = JSONResponse({"message": "Login successful.", "role": user["role"]})
    response.set_cookie("gradeops_session", token, httponly=True, samesite="lax")
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    # if JWT is stateless, just delete the cookie
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("gradeops_session")
    return response


@app.get("/api/auth/me")
async def get_current_user(request: Request):
    """Get current authenticated user info."""
    try:
        user = _current_user(request)
        return {"user": user}
    except HTTPException:
        return {"user": None}


@app.post("/api/exams/upload")
async def upload_exam_bundle(
    request: Request,
    exam_name: str = Form(...),
    question_paper: UploadFile = File(...),
    answer_sheets: list[UploadFile] = File(...),
    marking_scheme: UploadFile | None = File(None),
):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "upload")
    if not answer_sheets:
        raise HTTPException(status_code=400, detail="At least one answer sheet is required.")

    session_id = _make_session_id(exam_name)
    question_paper_path = _save_upload(question_paper)
    answer_sheet_paths = [_save_upload(sheet) for sheet in answer_sheets]
    has_marking_scheme = bool(marking_scheme and (marking_scheme.filename or "").strip())
    marking_scheme_path = _save_upload(marking_scheme) if has_marking_scheme else None

    db.create_session(
        session_id=session_id,
        exam_name=exam_name,
        owner=user["username"],
        question_paper_path=question_paper_path,
        answer_sheet_paths=answer_sheet_paths,
        marking_scheme_path=marking_scheme_path,
    )
    return {
        "session_id": session_id,
        "message": "Exam bundle uploaded. Now manually crop each question and extract text.",
        "question_count": 0,
        "questions": [],
    }


@app.post("/api/exams/{session_id}/questions/from-crop")
async def add_question_from_crop(request: Request, session_id: str, payload: QuestionCropPayload):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = _images_from_path(session["question_paper_path"])
    if payload.page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid question paper page_index")

    page_image = pages[payload.page_index]
    x, y, w, h, _ = _sanitize_crop_box(page_image, payload.x, payload.y, payload.w, payload.h)
    crop = extract_snippet(page_image, x, y, w, h)
    _validate_non_empty_crop(crop, "question")
    clean_crop = clean_for_ocr(crop)

    _, encoded = cv2.imencode('.png', clean_crop)
    snippet_path = cloud_storage.upload_bytes(encoded.tobytes(), ".png", "image/png")

    # Downloading locally for temporary for transcription
    temp_path = cloud_storage.download_to_local_temp(snippet_path)
    question_text = transcribe_snippet(str(temp_path)).strip()
    if not question_text:
        question_text = "OCR returned empty text. Please re-crop this question."

    question_id = _next_question_id(session["extracted_questions"])
    question = {"question_id": question_id, "question_text": question_text}
    session["extracted_questions"].append(question)
    db.update_session_questions(session_id, session["extracted_questions"])
    return {
        "message": "Question extracted from crop.",
        "question": question,
        "questions": session["extracted_questions"],
        "crop_box": {"x": x, "y": y, "w": w, "h": h},
        "crop_preview_base64": _encode_png_base64(clean_crop),
    }


@app.post("/api/exams/{session_id}/crop/preview")
async def preview_crop_region(request: Request, session_id: str, payload: CropPreviewPayload):
    _current_user(request)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    target_path = _resolve_preview_target(session, payload.source, payload.sheet_index)
    pages = _images_from_path(target_path)
    if payload.page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page_index")

    image = pages[payload.page_index]
    x, y, w, h, adjusted = _sanitize_crop_box(image, payload.x, payload.y, payload.w, payload.h)
    crop = extract_snippet(image, x, y, w, h)
    _validate_non_empty_crop(crop, f"{payload.source} crop")
    output = clean_for_ocr(crop) if payload.clean else crop
    preview_b64 = _encode_png_base64(output)
    return {
        "message": "Crop preview generated.",
        "source": payload.source,
        "crop_box": {"x": x, "y": y, "w": w, "h": h},
        "adjusted_to_fit_page": adjusted,
        "preview_base64": preview_b64,
    }


@app.post("/api/exams/{session_id}/coordinates")
async def configure_coordinates(
    request: Request,
    session_id: str,
    payload: ConfigurePayload,
):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.update_session_coordinates(session_id, [item.model_dump() for item in payload.coordinates])
    return {"message": f"Saved {len(payload.coordinates)} coordinate mappings."}


@app.get("/api/exams/{session_id}/preview")
async def preview_sheet_page(
    request: Request,
    session_id: str,
    page_index: int = Query(0, ge=0),
    sheet_index: int = Query(0, ge=0),
    source: str = Query("answer"),
):
    _current_user(request)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if source == "question":
        target_path = session["question_paper_path"]
    else:
        sheets = session["answer_sheet_paths"]
        if sheet_index >= len(sheets):
            raise HTTPException(status_code=400, detail="Invalid sheet_index")
        target_path = sheets[sheet_index]

    pages = _images_from_path(target_path)
    if page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page_index")

    image = pages[page_index]
    payload = _encode_png_bytes(image)
    return Response(content=payload, media_type="image/png")


def _run_grading_job(job_id: str, session_id: str):
    from src.rubric_factory import generate_rubric
    job = grading_jobs[job_id]
    try:
        session = db.get_session(session_id)
        if not session or not session["coordinates"]:
            job["status"] = "failed"
            job["error"] = "Session not found or no coordinates"
            return

        total_items = len(session["answer_sheet_paths"]) * len(session["coordinates"])
        job["total"] = total_items
        job["status"] = "running"
        job["step"] = "rubrics"

        question_rubrics = {}
        for coord in session["coordinates"]:
            qid = coord["question_id"]
            if qid not in question_rubrics:
                saved = db.get_rubric_template(session_id, qid)
                if saved:
                    question_rubrics[qid] = saved["rubric_json"]
                else:
                    question_rubrics[qid] = generate_rubric(
                        coord["question_text"],
                        coord.get("marking_scheme"),
                        max_score=coord.get("max_score")
                    )

        job["step"] = "grading"
        grading_results: list[dict[str, Any]] = []
        progress = 0

        for answer_path in session["answer_sheet_paths"]:
            student_id = Path(answer_path).stem
            student_id = _clean_student_id(student_id)
            pages = _images_from_path(answer_path)

            for coordinate in session["coordinates"]:
                page_index = coordinate["page_index"]
                if page_index >= len(pages):
                    progress += 1
                    job["progress"] = progress
                    continue

                qid = coordinate["question_id"]
                page_img = pages[page_index]
                img_h, img_w = page_img.shape[:2]
                cx, cy, cw, ch = coordinate["x"], coordinate["y"], coordinate["w"], coordinate["h"]

                if cy >= img_h or cx >= img_w:
                    print(f"  [SKIP] Crop out of bounds for {student_id}/{qid}: "
                          f"crop y={cy} but image height={img_h}")
                    grading_results.append({
                        "student_id": student_id,
                        "question_id": qid,
                        "proposed_score": 0,
                        "justification": (
                            f"CROP ERROR: The answer region (y={cy}, h={ch}) is outside this "
                            f"sheet's dimensions ({img_w}x{img_h}). The crop coordinates were "
                            f"drawn on a differently-sized sheet. Please re-crop or resize."
                        ),
                        "error_axes": [],
                        "needs_review": True,
                        "transcription": "[Crop out of bounds]",
                        "snippet_path": "",
                        "accuracy": 0,
                        "rubric": question_rubrics.get(qid),
                        "verification_passed": False,
                        "verification_feedback": "Skipped — crop region does not fit this sheet.",
                    })
                    progress += 1
                    job["progress"] = progress
                    continue

                raw_crop = extract_snippet(page_img, cx, cy, cw, ch)
                if raw_crop is None or raw_crop.size == 0:
                    progress += 1
                    job["progress"] = progress
                    continue
                cleaned_crop = clean_for_ocr(raw_crop)

                _, encoded = cv2.imencode('.png', cleaned_crop)
                snippet_path = cloud_storage.upload_bytes(encoded.tobytes(), ".png", "image/png")

                temp_path = cloud_storage.download_to_local_temp(snippet_path)
                transcription = transcribe_snippet(str(temp_path), context_text=coordinate["question_text"])

                pipeline_state = {
                    "student_id": student_id,
                    "question_text": coordinate["question_text"],
                    "marking_scheme_text": coordinate.get("marking_scheme"),
                    "transcription": transcription,
                    "rubric": question_rubrics.get(qid)
                }

                result = grading_pipeline.invoke(pipeline_state)
                result["student_id"] = student_id
                result["question_id"] = qid
                result["transcription"] = transcription
                result["snippet_path"] = str(snippet_path)
                result["accuracy"] = _score_accuracy(result, transcription)
                result["rubric"] = question_rubrics.get(qid)
                grading_results.append(result)

                progress += 1
                job["progress"] = progress

        job["step"] = "plagiarism"
        plagiarism_flags = detect_rejump_collusion(grading_results)
        db.save_results(session_id, grading_results)
        db.save_plagiarism_flags(session_id, plagiarism_flags)

        review_count = sum(1 for r in grading_results if r.get("accuracy", 1) < 0.7 or r.get("needs_review"))
        job["status"] = "done"
        job["summary"] = {
            "graded_entries": len(grading_results),
            "review_required": review_count,
            "plagiarism_flags_count": len(plagiarism_flags),
        }
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.post("/api/exams/{session_id}/run")
async def run_bulk_grading(request: Request, session_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "grade")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session["coordinates"]:
        raise HTTPException(status_code=400, detail="No question coordinates configured.")

    job_id = str(uuid.uuid4())
    grading_jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "total": 0,
        "step": "init",
        "summary": None,
        "error": None,
    }
    thread = threading.Thread(target=_run_grading_job, args=(job_id, session_id), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "started"}


@app.get("/api/exams/{session_id}/job/{job_id}")
async def poll_grading_job(request: Request, session_id: str, job_id: str):
    _current_user(request)
    job = grading_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "step": job.get("step", ""),
        "summary": job.get("summary"),
        "error": job.get("error"),
    }



@app.get("/api/storage/{filename}")
async def serve_snippet(request: Request, filename: str):
    """Serve a local fallback snippet."""
    _current_user(request)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Checking fallback directory
    snippet_file = cloud_storage.LOCAL_STORAGE_DIR / filename
    if snippet_file.exists() and snippet_file.is_file():
        return Response(content=snippet_file.read_bytes(), media_type="image/png")

    # Fallback to old snippets directory for legacy compatibility
    legacy_file = SNIPPETS_DIR / filename
    if legacy_file.exists() and legacy_file.is_file():
        return Response(content=legacy_file.read_bytes(), media_type="image/png")

    raise HTTPException(status_code=404, detail="Snippet not found")


@app.get("/api/exams/{session_id}/dashboard")
async def review_dashboard_data(request: Request, session_id: str):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "review")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    results = session["results"]
    review_queue = session["review_queue"]
    plagiarism_flags = session["plagiarism_flags"]

    for r in results:
        r["student_id"] = _clean_student_id(r.get("student_id", ""))
    for r in review_queue:
        r["student_id"] = _clean_student_id(r.get("student_id", ""))

    # Build analytics summary from real pipeline data
    total = len(results)
    if total > 0:
        scores = [r.get("proposed_score", 0) for r in results]
        accuracies = [r.get("accuracy", 0) for r in results]
        avg_score = round(sum(scores) / total, 2)
        avg_accuracy = round(sum(accuracies) / total, 2)

        # Error axis distribution from grader.py outputs
        error_dist: dict[str, int] = {}
        for r in results:
            for axis in r.get("error_axes", []):
                label = axis if isinstance(axis, str) else str(axis)
                error_dist[label] = error_dist.get(label, 0) + 1

        # Rubric data (if present in pipeline results)
        rubrics = {}
        for r in results:
            qid = r.get("question_id", "")
            if qid and qid not in rubrics and r.get("rubric"):
                rubrics[qid] = r["rubric"]
    else:
        avg_score = 0
        avg_accuracy = 0
        error_dist = {}
        rubrics = {}

    return JSONResponse(
        {
            "session_id": session_id,
            "exam_name": session["exam_name"],
            "extracted_questions": session["extracted_questions"],
            "results": results,
            "review_queue": review_queue,
            "plagiarism_flags": plagiarism_flags,
            "analytics": {
                "total_graded": total,
                "review_count": len(review_queue),
                "plagiarism_count": len(plagiarism_flags),
                "avg_score": avg_score,
                "avg_accuracy": avg_accuracy,
                "error_distribution": error_dist,
                "rubrics": rubrics,
            },
        }
    )


@app.post("/api/exams/{session_id}/review/{result_id}/approve")
async def approve_result(request: Request, session_id: str, result_id: int):
    user = _current_user(request)
    _check_permission(user["role"], "review")
    db.update_result_review(result_id, "approved")
    return {"status": "success", "message": f"Result {result_id} approved"}


class OverridePayload(BaseModel):
    new_score: float


@app.post("/api/exams/{session_id}/review/{result_id}/override")
async def override_result(request: Request, session_id: str, result_id: int, payload: OverridePayload):
    user = _current_user(request)
    _check_permission(user["role"], "review")
    db.update_result_review(result_id, "overridden", new_score=payload.new_score)
    return {"status": "success", "message": f"Result {result_id} overridden to {payload.new_score}"}


# ── Rubric Template Endpoints ──

class RubricCriterion(BaseModel):
    description: str = Field(..., min_length=1)
    points: float = Field(..., ge=0)
    type: str = Field("conceptual")


class RubricPayload(BaseModel):
    question_id: str = Field(..., min_length=1)
    max_score: float = Field(..., gt=0)
    criteria: list[RubricCriterion]


@app.post("/api/exams/{session_id}/rubrics")
async def save_rubric(request: Request, session_id: str, payload: RubricPayload):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rubric_dict = {
        "question_id": payload.question_id,
        "max_score": payload.max_score,
        "criteria": [{"id": f"c{i+1}", **c.model_dump()} for i, c in enumerate(payload.criteria)],
    }
    db.save_rubric_template(session_id, payload.question_id, rubric_dict)
    return {"message": f"Rubric saved for {payload.question_id}", "rubric": rubric_dict}


@app.get("/api/exams/{session_id}/rubrics")
async def get_rubrics(request: Request, session_id: str):
    _current_user(request)
    templates = db.get_rubric_templates(session_id)
    rubrics = {t["question_id"]: t["rubric_json"] for t in templates}
    return {"rubrics": rubrics}


@app.delete("/api/exams/{session_id}/rubrics/{question_id}")
async def delete_rubric(request: Request, session_id: str, question_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    db.delete_rubric_template(session_id, question_id)
    return {"message": f"Rubric deleted for {question_id}"}


@app.post("/api/exams/{session_id}/rubrics/{question_id}/generate")
async def generate_rubric_for_question(request: Request, session_id: str, question_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    question = next((q for q in session["extracted_questions"] if q["question_id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    from src.rubric_factory import generate_rubric
    rubric = generate_rubric(question["question_text"])
    if rubric:
        db.save_rubric_template(session_id, question_id, rubric)
    return {"rubric": rubric}


# ── Re-grade Single Answer ──

@app.post("/api/exams/{session_id}/regrade/{result_id}")
async def regrade_single(request: Request, session_id: str, result_id: int):
    user = _current_user(request)
    _check_permission(user["role"], "grade")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    existing = db.get_result_by_id(result_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Result not found")

    snippet_path = existing.get("snippet_path", "")
    question_id = existing.get("question_id", "")
    student_id = existing.get("student_id", "")

    coord = next((c for c in session.get("coordinates", []) if c["question_id"] == question_id), None)
    question_text = coord["question_text"] if coord else ""
    marking_scheme = coord.get("marking_scheme") if coord else None

    transcription = existing.get("transcription", "")
    if snippet_path:
        try:
            temp_path = cloud_storage.download_to_local_temp(snippet_path)
            transcription = transcribe_snippet(str(temp_path), context_text=question_text)
        except Exception:
            pass

    saved_rubric = db.get_rubric_template(session_id, question_id)
    rubric = saved_rubric["rubric_json"] if saved_rubric else None
    if not rubric and question_text:
        from src.rubric_factory import generate_rubric
        rubric = generate_rubric(question_text, marking_scheme)

    pipeline_state = {
        "student_id": student_id,
        "question_text": question_text,
        "marking_scheme_text": marking_scheme,
        "transcription": transcription,
        "rubric": rubric,
    }
    result = grading_pipeline.invoke(pipeline_state)
    result["student_id"] = student_id
    result["question_id"] = question_id
    result["transcription"] = transcription
    result["snippet_path"] = snippet_path
    result["accuracy"] = _score_accuracy(result, transcription)
    result["rubric"] = rubric

    updated = db.update_single_result(result_id, result)
    return {"message": "Re-grade complete", "result": updated}


@app.post("/api/sandbox/create")
async def create_sandbox(request: Request):
    user = _current_user(request)
    data = await request.json()
    preset = data.get("preset", "custom")

    session_id = _make_session_id(exam_name if preset == "custom" else preset)

    if preset == "math":
        exam_name = "Calculus I - Midterm Simulation"
        num_students = 80
        num_questions = 5
        max_score_val = 20
        include_plagiarism = True
    elif preset == "history":
        exam_name = "World History Final Simulation"
        num_students = 80
        num_questions = 5
        max_score_val = 100
        include_plagiarism = True
    else:
        exam_name = "Custom Sandbox Session"
        num_students = int(data.get("students", 10))
        num_questions = int(data.get("questions", 4))
        max_score_val = int(data.get("max_score", 10))
        include_plagiarism = data.get("include_plagiarism", True)

    db.create_session(
        session_id=session_id,
        exam_name=exam_name,
        owner=user["username"],
        question_paper_path="",
        answer_sheet_paths=[],
        marking_scheme_path=""
    )

    import random

    # Variety Pools - Enhanced for thousands of unique combinations
    topics = ["Physics", "Calculus", "World History", "Org Chemistry", "Macroeconomics", "Software Arch"]
    verbs = ["demonstrated", "showed", "exhibited", "presented", "displayed", "provided"]
    strengths = ["excellent understanding", "solid conceptual grasp", "thorough derivation", "logical flow", "deep context"]
    weaknesses = ["minor notation slip", "calculation error in step 2", "lack of specific dates", "formatting inconsistency", "missing units"]

    trans_templates = [
        "The {term} is {val}. Calculated using {method}.",
        "By applying {theory}, we get {result}.",
        "The primary cause was {event} which led to {outcome}.",
        "The solution for {eq} is found via {formula}.",
        "Analysis of {topic} reveals {insight}."
    ]

    terms = ["force", "integral", "derivative", "reaction", "constant", "variable"]
    vals = ["$F=ma$", "$x^2/2$", "$10.5N$", "2019", "Versailles", "196J"]
    methods = ["standard derivation", "substitution", "first principles", "contextual analysis"]
    theories = ["fundamental theorem", "Newton's laws", "marginal utility", "Plato's Republic"]

    def gen_unique_trans():
        tpl = random.choice(trans_templates)
        return tpl.format(
            term=random.choice(terms), val=random.choice(vals), method=random.choice(methods),
            theory=random.choice(theories), result=random.choice(vals), event="Revolution",
            outcome="Urbanization", eq=r"$\int x dx$", formula="Quadratic Rule", topic="The Sea", insight="depth"
        ) + f" [Ref:{uuid.uuid4().hex[:4]}]"

    def gen_unique_just(score, max_s):
        v = random.choice(verbs)
        s = random.choice(strengths)
        w = random.choice(weaknesses)
        if score >= max_s * 0.9:
            return f"Student {v} {s}. All steps are technically sound and clear."
        return f"Student {v} {s}, however, there is a {w} that resulted in a score of {score}/{max_s}."

    # Get available snippet images for variety
    all_snippets = [f.name for f in SNIPPETS_DIR.glob("*.png")]
    if not all_snippets:
        all_snippets = ["page_0_question_1.png"]

    questions = []
    sandbox_rubrics = {}

    # Define specific questions for math and history
    if preset == "math":
        math_questions = [
            ("Q1", "Find the derivative of f(x) = x^3 + 3x^2 - 5x + 2 using the power rule and chain rule. Show all intermediate steps."),
            ("Q2", "Evaluate the definite integral ∫₀² (x² + 2x)dx. Show the integration process and verify with the Fundamental Theorem of Calculus."),
            ("Q3", "Determine the critical points and classify them as local maxima or minima for f(x) = x³ - 3x²."),
            ("Q4", "Solve the differential equation dy/dx = 2xy with initial condition y(0) = 1. Find the particular solution."),
            ("Q5", "Evaluate the limit lim(x→0) (sin(x) - x)/x³ using L'Hôpital's rule or Taylor series expansion.")
        ]
        for qid, q_text in math_questions:
            questions.append({
                "question_id": qid,
                "question_text": q_text,
                "page_index": 0,
                "coords": {"x": 100, "y": 100 * int(qid[1]), "w": 500, "h": 80}
            })
            sandbox_rubrics[qid] = {
                "question_id": qid,
                "max_score": max_score_val,
                "criteria": [
                    {"id": f"{qid}_c1", "description": "Correct identification and application of mathematical rules (power rule, chain rule, integration techniques)", "points": round(max_score_val * 0.30, 1), "type": "computational"},
                    {"id": f"{qid}_c2", "description": "Accurate algebraic manipulation and computation with proper handling of signs and coefficients", "points": round(max_score_val * 0.25, 1), "type": "computational"},
                    {"id": f"{qid}_c3", "description": "Clear step-by-step reasoning showing logical progression from problem statement to solution", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c4", "description": "Correct interpretation and application of mathematical theorems (Fundamental Theorem, L'Hôpital's rule)", "points": round(max_score_val * 0.15, 1), "type": "conceptual"},
                    {"id": f"{qid}_c5", "description": "Proper notation, labeling of variables, and presentation of final answer with units where applicable", "points": round(max_score_val * 0.10, 1), "type": "presentation"}
                ]
            }
    else:
        history_questions = [
            ("Q1", "Analyze the major causes of World War I, discussing how militarism, alliances, imperialism, and nationalism contributed to the outbreak of the war."),
            ("Q2", "Explain the significance of the Treaty of Versailles in shaping the political and economic landscape of Europe in the interwar period."),
            ("Q3", "Discuss the role of Gandhi's philosophy of nonviolent resistance in India's independence movement. Include specific campaigns and their outcomes."),
            ("Q4", "Evaluate the impact of the Cold War on global politics, focusing on at least three major proxy conflicts and their consequences."),
            ("Q5", "Analyze the causes and consequences of the French Revolution, examining how it transformed French society and influenced revolutionary movements worldwide.")
        ]
        for qid, q_text in history_questions:
            questions.append({
                "question_id": qid,
                "question_text": q_text,
                "page_index": 0,
                "coords": {"x": 100, "y": 100 * int(qid[1]), "w": 500, "h": 80}
            })
            sandbox_rubrics[qid] = {
                "question_id": qid,
                "max_score": max_score_val,
                "criteria": [
                    {"id": f"{qid}_c1", "description": "Comprehensive identification and analysis of key causes/factors with historical evidence", "points": round(max_score_val * 0.30, 1), "type": "conceptual"},
                    {"id": f"{qid}_c2", "description": "Accurate citation of specific dates, events, and historical figures to support arguments", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c3", "description": "Logical organization with clear thesis statement, supporting evidence, and coherent conclusion", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c4", "description": "Critical analysis of cause-and-effect relationships and long-term consequences", "points": round(max_score_val * 0.15, 1), "type": "conceptual"},
                    {"id": f"{qid}_c5", "description": "Balanced perspective considering multiple viewpoints and avoiding oversimplification", "points": round(max_score_val * 0.15, 1), "type": "conceptual"}
                ]
            }

    db.update_session_questions(session_id, questions)

    results = []
    error_types = ["notation", "calculation", "conceptual", "formatting", "reasoning", "presentation"]

    # Extensive justification templates for different score ranges
    excellent_justifications = [
        "The student has demonstrated exceptional mastery of the subject matter. The solution is mathematically sound, with perfect application of rules and theorems. The reasoning is crystal clear, showing a deep conceptual understanding that goes beyond mere procedural knowledge. Every step is meticulously executed with proper justification. The presentation is professional, with clear notation, well-labeled figures, and a complete final answer. This represents work of exceptional quality that meets all rubric criteria at the highest level.",
        "An exemplary response that demonstrates thorough understanding of all key concepts. The student correctly identified the appropriate methods and executed them flawlessly. The solution shows sophisticated reasoning, with proper use of mathematical notation and logical flow. All intermediate steps are shown and justified. The final answer is complete and correct. The presentation reflects a strong grasp of the material and attention to detail.",
        "Outstanding work demonstrating comprehensive understanding of the underlying principles. The approach is efficient and mathematically rigorous. Every calculation is accurate, and the logic flows seamlessly from one step to the next. The student shows excellent command of the subject, with clear articulation of the reasoning process. The solution is complete, well-organized, and meets all criteria for full marks."
    ]

    good_justifications = [
        "The student demonstrates a solid understanding of the core concepts and approaches the problem correctly. The methodology is appropriate, and most calculations are accurate. There is one minor computational error or oversight that slightly affected the final result, but the overall approach remains sound. The reasoning is generally clear, though some steps could benefit from more explicit explanation. With minor corrections, this would be an excellent submission.",
        "Good work showing competent handling of the material. The student correctly applies the main techniques but makes a small error in execution (such as a sign mistake, unit conversion error, or minor algebraic slip). The conceptual understanding is evident, and the solution structure is appropriate. The error does not fundamentally undermine the approach. Partial credit is warranted for the correct methodology and reasonable execution.",
        "The student shows good comprehension of the fundamental principles and applies appropriate methods. There is a minor computational mistake in an intermediate step that propagates to the final answer, but the overall approach demonstrates understanding. The presentation is adequate but could be more polished. The student should review the specific error type to improve accuracy in future work."
    ]

    partial_justifications = [
        "The student demonstrates partial understanding of the concepts but makes significant errors in application. The initial approach is reasonable, but fundamental mistakes in execution (such as applying the wrong rule, misinterpreting the problem, or consistent computational errors) lead to an incorrect solution. Some credit is awarded for attempting the correct method and showing some understanding of the underlying principles, but the errors are substantial enough to warrant a lower score.",
        "The response shows some grasp of basic concepts but fails to correctly apply the required methods. The student makes multiple errors in calculation and reasoning that indicate gaps in understanding. The solution demonstrates awareness of what needs to be done but lacks the technical skill to execute it correctly. Partial credit is given for the partial understanding shown.",
        "The student identifies the general approach needed but struggles with the technical execution. Multiple errors in calculation, formula application, or logical reasoning are present throughout the solution. The student shows some knowledge of the subject but cannot apply it correctly. The work demonstrates understanding of the question's requirements but fails to deliver a correct solution."
    ]

    poor_justifications = [
        "The student demonstrates fundamental misunderstanding of the core concepts. The approach taken is incorrect, with application of wrong formulas or methods that do not apply to this type of problem. The reasoning is unclear and contains multiple logical errors. The solution shows significant gaps in knowledge that prevent meaningful progress toward the correct answer. Major conceptual errors make it difficult to award any significant credit beyond acknowledgment of the attempt.",
        "The response indicates lack of preparation or understanding of basic principles. The student either attempts an irrelevant approach or produces work that does not address the question. Errors are numerous and fundamental, suggesting confusion about basic concepts. The work cannot be credited beyond minimal acknowledgment of the attempt.",
        "Serious conceptual errors permeate this response. The student applies incorrect principles, makes unsupported claims, and demonstrates fundamental misunderstanding of the topic. The solution shows no evidence of the required analytical skills. This represents a significant gap in student preparation and understanding."
    ]

    def gen_extensive_justification(score, max_s):
        pct = score / max_s
        if pct >= 0.90:
            return random.choice(excellent_justifications)
        elif pct >= 0.70:
            return random.choice(good_justifications)
        elif pct >= 0.40:
            return random.choice(partial_justifications)
        else:
            return random.choice(poor_justifications)

    transcription_templates_math = [
        r"f'(x) = 3x^2 + 6x - 5. Applying the power rule: d/dx(x^n) = nx^{n-1}.",
        r"∫(x² + 2x)dx = [x³/3 + x²]₀² = (8/3 + 4) - 0 = 20/3",
        r"Critical points at x = 0 and x = 2. Using second derivative test: f''(0) = -6 (max), f''(2) = 6 (min)",
        r"dy/dx = 2xy → dy/y = 2x dx → ln|y| = x² + C → y = Ce^{x²}",
        r"Using Taylor series: sin(x) = x - x³/6 + ..., so (sin(x) - x)/x³ → -1/6 as x→0"
    ]

    transcription_templates_history = [
        "The four main causes were militarism (arms race), alliances (Triple Entente/Central Powers), imperialism (colonial competition), and nationalism (ethnic tensions in Balkans). The assassination of Archduke Franz Ferdinand triggered the war.",
        "The Treaty imposed heavy reparations (132 billion gold marks), territorial losses (Alsace-Lorraine to France, Polish corridor), and war guilt clause on Germany. This led to political instability, economic crisis, and rise of Nazism.",
        "Gandhi's nonviolence (Satyagraha) included Salt March (1930), Quit India (1942), and Champaran (1917). These campaigns mobilized millions and eventually forced British to negotiate independence.",
        "Proxy conflicts included Korean War (1950-53), Vietnam War (1955-75), and Afghan War (1979-89). These prolonged Cold War tensions and resulted in millions of casualties while avoiding direct US-USR confrontation.",
        "Causes included financial crisis, inequality, Enlightenment ideas, and weak leadership. Consequences: execution of Louis XVI, Reign of Terror, rise of Napoleon, and spread of revolutionary ideals across Europe."
    ]

    all_transcriptions = transcription_templates_math if preset == "math" else transcription_templates_history

    for s_idx in range(1, num_students + 1):
        student_id = f"student_{s_idx:03d}"
        for q_idx in range(1, num_questions + 1):
            qid = f"Q{q_idx}"

            # Generate score with realistic distribution
            score = round(random.uniform(0.3, 1.0) * max_score_val, 1)
            accuracy = random.uniform(0.65, 0.99)
            needs_review = (accuracy < 0.75 or random.random() < 0.08)

            axes = []
            if score < max_score_val * 0.9:
                axes = random.sample(error_types, random.randint(1, 2))

            # Get unique transcription for this student/question
            trans_base = all_transcriptions[q_idx - 1]
            trans_with_id = f"{trans_base} [ID:{student_id}-{qid}]"

            results.append({
                "student_id": student_id,
                "question_id": qid,
                "proposed_score": score,
                "justification": gen_extensive_justification(score, max_score_val),
                "needs_review": 1 if needs_review else 0,
                "error_axes": axes,
                "transcription": trans_with_id,
                "snippet_path": random.choice(all_snippets),
                "accuracy": round(accuracy, 2),
                "rubric": sandbox_rubrics[qid]
            })

    db.save_results(session_id, results)

    if include_plagiarism:
        # Generate multiple plagiarism flags (3-5 for 80 students)
        s_pool = [f"student_{i:03d}" for i in range(1, num_students + 1)]
        num_flags = random.randint(3, 5)
        flags = []
        for _ in range(num_flags):
            pair = random.sample(s_pool, 2)
            flags.append({
                "pair": (pair[0], pair[1]),
                "confidence": round(random.uniform(0.88, 0.97), 2),
                "shared_error_axes": random.sample(["conceptual", "notation", "computational", "reasoning"], 2),
                "reason": f"Suspiciously identical logical structure, matching error patterns in {qid}, and nearly identical phrasing detected by ReJump integrity system. Both students made the same unusual mistake in their approach."
            })
        db.save_plagiarism_flags(session_id, flags)

    return {"session_id": session_id, "message": f"Sandbox '{preset}' created with {num_students * num_questions} unique results."}


class ReviewPayload(BaseModel):
    status: str = Field(..., pattern="^(approved|overridden)$")
    new_score: float | None = None

@app.post("/api/exams/{session_id}/review/{result_id}")
async def update_review_status(request: Request, session_id: str, result_id: int, payload: ReviewPayload):
    user = _current_user(request)
    _check_permission(user["role"], "review")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    updated = db.update_result_review(result_id, payload.status, payload.new_score)
    if not updated:
        raise HTTPException(status_code=404, detail="Result not found")

    return {"message": "Review status updated successfully", "result": updated}


class SandboxPayload(BaseModel):
    students: int = 10
    questions: int = 4
    max_score: float = 10.0
    include_plagiarism: bool = True
    include_low_conf: bool = True

@app.post("/api/sandbox/generate")
async def generate_sandbox_data(request: Request, preset: str = Query(None), payload: SandboxPayload = None):
    user = _current_user(request)

    session_id = f"sandbox_{uuid.uuid4().hex[:8]}"
    db.create_session(
        session_id=session_id,
        exam_name=f"Sandbox: {preset.capitalize() if preset else 'Custom'} Exam",
        owner=user["username"],
        question_paper_path="",
        answer_sheet_paths=[],
    )

    results = []
    flags = []
    import random

    if preset == "math":
        questions = [{"question_id": "q1", "question_text": "Calculate the derivative of f(x) = x^2 * sin(x)"},
                    {"question_id": "q2", "question_text": "Evaluate the integral of e^(2x) dx"}]
        db.update_session_questions(session_id, questions)

        results = [
            {"student_id": "std_01", "question_id": "q1", "proposed_score": 8, "needs_review": False, "accuracy": 0.9, "justification": "Correct application of product rule, but minor sign error at the end.", "error_axes": ["computational"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "f'(x) = 2x sin(x) - x^2 cos(x)", "snippet_path": ""},
            {"student_id": "std_02", "question_id": "q1", "proposed_score": 4, "needs_review": True, "accuracy": 0.6, "justification": "Incorrect rule used.", "error_axes": ["conceptual"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "f'(x) = 2x cos(x)", "snippet_path": ""},
            {"student_id": "std_03", "question_id": "q2", "proposed_score": 10, "needs_review": False, "accuracy": 0.95, "justification": "Perfect step-by-step.", "error_axes": [], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 * e^(2x) + C", "snippet_path": ""},
            {"student_id": "std_04", "question_id": "q2", "proposed_score": 10, "needs_review": False, "accuracy": 0.95, "justification": "Perfect step-by-step.", "error_axes": [], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 e^(2x) + C", "snippet_path": ""},
            {"student_id": "std_05", "question_id": "q2", "proposed_score": 8, "needs_review": False, "accuracy": 0.85, "justification": "Forgot the constant of integration.", "error_axes": ["notation"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 e^(2x)", "snippet_path": ""},
        ]
        flags = [
            {"pair": ("std_03", "std_04"), "confidence": 0.98, "reason": "Identical logical jumps and same unusual notation used.", "shared_error_axes": []}
        ]

    elif preset == "history":
        questions = [{"question_id": "q1", "question_text": "Discuss the causes of World War I."}]
        db.update_session_questions(session_id, questions)

        results = [
            {"student_id": "std_01", "question_id": "q1", "proposed_score": 15, "needs_review": False, "accuracy": 0.85, "justification": "Good coverage of MANIA causes.", "error_axes": [], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "The main causes were militarism, alliances, imperialism...", "snippet_path": ""},
            {"student_id": "std_02", "question_id": "q1", "proposed_score": 5, "needs_review": True, "accuracy": 0.5, "justification": "Confused WWI with WWII.", "error_axes": ["conceptual"], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "Hitler invaded Poland which started the war...", "snippet_path": ""},
            {"student_id": "std_03", "question_id": "q1", "proposed_score": 2, "needs_review": True, "accuracy": 0.4, "justification": "Unreadable handwriting.", "error_axes": ["presentation"], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "[?] caused the [?] in 1914...", "snippet_path": ""},
        ]

    else:
        # Custom Dataset Generation
        if not payload:
            payload = SandboxPayload()
        num_students = max(payload.students, 25)
        num_questions = max(payload.questions, 5)
        payload.students = num_students
        payload.questions = num_questions

        questions = []
        for i in range(1, payload.questions + 1):
            questions.append({"question_id": f"q{i}", "question_text": f"Simulated Question {i} - Topic {random.choice(['Alpha', 'Beta', 'Gamma'])}{i}"})
        db.update_session_questions(session_id, questions)

        error_types = ["computational", "conceptual", "notation", "presentation"]

        for s in range(1, payload.students + 1):
            student_id = f"student_{s:03d}"
            for q in questions:
                # Base performance for this student/question
                score_pct = random.random()

                # Introduce errors
                axes = []
                if score_pct < 0.8:
                    axes.append(random.choice(error_types))
                if score_pct < 0.4:
                    axes.append(random.choice(error_types))

                # Determine accuracy / needs review
                accuracy = random.uniform(0.7, 0.98)
                needs_review = False

                if payload.include_low_conf and random.random() < 0.15:
                    accuracy = random.uniform(0.3, 0.6)
                    needs_review = True
                    axes.append("presentation")

                if score_pct < 0.3:
                    needs_review = True

                score = round(score_pct * payload.max_score, 1)

                results.append({
                    "student_id": student_id,
                    "question_id": q["question_id"],
                    "proposed_score": score,
                    "needs_review": needs_review,
                    "accuracy": accuracy,
                    "justification": (
                        "The student demonstrated excellent understanding. Flawless derivation with sound logic and proper units." if score_pct > 0.9 else
                        "Good overall approach. Grasped core concepts but made a minor mathematical error in an intermediate step." if score_pct > 0.7 else
                        "Identified the starting equations but failed to apply boundary conditions correctly. Notation lacks rigor." if score_pct > 0.4 else
                        "Shows a fundamental misunderstanding of the topic. Applied incorrect physical laws. No credit for main derivation."
                    )
                    if accuracy > 0.6 else "OCR confidence is very low due to illegible handwriting or smudges. Manual TA review strongly recommended.",
                    "error_axes": list(set(axes)),
                    "rubric": {"max_score": payload.max_score, "criteria": [{"description": "Core conceptual understanding", "points": round(payload.max_score * 0.5, 1), "type": "conceptual"}, {"description": "Execution and methodology", "points": round(payload.max_score * 0.3, 1), "type": "computational"}, {"description": "Clarity and notation", "points": round(payload.max_score * 0.2, 1), "type": "presentation"}]},
                    "transcription": f"Simulated student response for {q['question_id']}..." if accuracy > 0.6 else "Simul[?] student re[?] for [?]...",
                    "snippet_path": ""
                })

        if payload.include_plagiarism and payload.students >= 2:
            num_flags = random.randint(1, max(1, payload.students // 5))
            for _ in range(num_flags):
                s1, s2 = random.sample(range(1, payload.students + 1), 2)
                flags.append({
                    "pair": (f"student_{s1:03d}", f"student_{s2:03d}"),
                    "confidence": random.uniform(0.9, 0.99),
                    "reason": "High semantic similarity in incorrect reasoning steps.",
                    "shared_error_axes": [random.choice(error_types)]
                })

    db.save_results(session_id, results)
    db.save_plagiarism_flags(session_id, flags)

    return {"session_id": session_id, "message": "Sandbox data generated successfully."}



@app.get("/api/exams/{session_id}/report", response_class=HTMLResponse)
async def generate_grade_report(request: Request, session_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "review")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    results = session.get("results", [])

    # Group by student
    students = {}
    for r in results:
        sid = r.get("student_id", "Unknown")
        if sid not in students:
            students[sid] = {"results": [], "total_score": 0}

        students[sid]["results"].append(r)
        students[sid]["total_score"] += float(r.get("proposed_score", 0))

    # Round totals
    for sid in students:
        students[sid]["total_score"] = round(students[sid]["total_score"], 1)

    # Sort students by ID
    students = dict(sorted(students.items()))

    import datetime
    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={
            "session": session,
            "students": students,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
=======
from __future__ import annotations

import os
import re
import asyncio
import threading
from dotenv import load_dotenv
load_dotenv()
import bcrypt
from jose import jwt, JWTError
import datetime
import base64
import shutil
import uuid
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

from src import database as db
from src import storage as cloud_storage
from src.integrity import detect_rejump_collusion
from src.ocr_engine import transcribe_snippet
from src.preprocess import clean_for_ocr, extract_snippet, pdf_to_images
from src.workflow import build_grading_graph

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SNIPPETS_DIR = DATA_DIR / "snippets"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
USERS_FILE = DATA_DIR / "users.json"

for required_dir in (UPLOADS_DIR, SNIPPETS_DIR, TEMPLATES_DIR, DATA_DIR, STATIC_DIR):
    required_dir.mkdir(parents=True, exist_ok=True)

db.init_db()
db.migrate_users_from_json(USERS_FILE)

app = FastAPI(title="GradeOps Vision Portal")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
grading_pipeline = build_grading_graph()

grading_jobs: dict[str, dict[str, Any]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROLE_PERMISSIONS = {
    "instructor": {"upload", "configure", "grade", "review"},
    "ta": {"review"},
}


SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# Remove active_sessions



class CoordinateItem(BaseModel):
    question_id: str = Field(..., min_length=1)
    page_index: int = Field(..., ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)
    question_text: str = Field(..., min_length=1)
    marking_scheme: str | None = None
    max_score: float | None = None


class ConfigurePayload(BaseModel):
    coordinates: list[CoordinateItem]


class QuestionCropPayload(BaseModel):
    page_index: int = Field(..., ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)


class CropPreviewPayload(BaseModel):
    source: str = Field(..., pattern="^(question|answer)$")
    page_index: int = Field(..., ge=0)
    sheet_index: int = Field(0, ge=0)
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., gt=0)
    h: int = Field(..., gt=0)
    clean: bool = False


def _current_user(request: Request) -> dict[str, str]:
    token = request.cookies.get("gradeops_session")
    if not token:
        raise HTTPException(status_code=401, detail="Please log in.")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Session invalid.")

    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Session invalid.")
    return {"username": username, "role": user["role"]}


def _check_permission(role: str, action: str) -> None:
    if action not in ROLE_PERMISSIONS.get(role, set()):
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot perform '{action}'")


def _save_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload file must have a filename.")
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
    return cloud_storage.upload_file(file.file, clean_name, file.content_type)

def _make_session_id(label: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:30]
    short = uuid.uuid4().hex[:6]
    return f"{slug}-{short}" if slug else short

def _clean_student_id(sid: str) -> str:
    if len(sid) > 33 and sid[32] == '_':
        return sid[33:]
    return sid

def _images_from_path(file_path: str) -> list[np.ndarray]:
    if not file_path:
        # Sandbox or empty session fallback
        dummy = np.ones((800, 600, 3), dtype=np.uint8) * 240
        cv2.putText(dummy, "SANDBOX MODE", (150, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)
        cv2.putText(dummy, "(No images uploaded)", (140, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 1)
        return [dummy]

    # Download from cloud if necessary
    local_path = cloud_storage.download_to_local_temp(file_path)

    ext = Path(local_path).suffix.lower()
    if ext == ".pdf":
        return pdf_to_images(local_path)

    # First, try OpenCV direct decode (works for most raster formats).
    img = cv2.imread(local_path)
    if img is not None:
        return [img]

    # Fallback via PIL for less common but still image-like inputs.
    try:
        pil = Image.open(file_path).convert("RGB")
        pil_np = np.array(pil)
        bgr = cv2.cvtColor(pil_np, cv2.COLOR_RGB2BGR)
        return [bgr]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unreadable file format: {Path(file_path).name}",
        ) from exc


def _encode_png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode preview image")
    return encoded.tobytes()


def _encode_png_base64(image: np.ndarray) -> str:
    return base64.b64encode(_encode_png_bytes(image)).decode("utf-8")


def _score_accuracy(result: dict[str, Any], transcription: str) -> float:
    confidence = 0.85
    if "[?]" in transcription:
        confidence -= 0.35
    if result.get("needs_review"):
        confidence -= 0.2
    if not result.get("justification"):
        confidence -= 0.15
    return round(max(0.0, min(1.0, confidence)), 2)


def _validate_non_empty_crop(crop: np.ndarray, context: str) -> None:
    if crop is None or crop.size == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The selected {context} region is empty. "
                "Please draw the crop box fully inside the page."
            ),
        )


def _sanitize_crop_box(image: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int, bool]:
    img_h, img_w = image.shape[:2]
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(x + w, img_w)
    y1 = min(y + h, img_h)
    adjusted = (x0 != x) or (y0 != y) or (x1 != x + w) or (y1 != y + h)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0), adjusted


def _resolve_preview_target(session: dict[str, Any], source: str, sheet_index: int) -> str:
    if source == "question":
        return session["question_paper_path"]
    sheets = session["answer_sheet_paths"]
    if sheet_index >= len(sheets):
        raise HTTPException(status_code=400, detail="Invalid sheet_index")
    return sheets[sheet_index]


def _extract_questions_from_text(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    questions: list[dict[str, str]] = []
    current_qid = None
    current_chunks: list[str] = []

    def _flush() -> None:
        nonlocal current_qid, current_chunks
        if current_qid and current_chunks:
            questions.append({"question_id": current_qid, "question_text": " ".join(current_chunks).strip()})
        current_qid = None
        current_chunks = []

    for line in lines:
        lowered = line.lower()
        if lowered.startswith("q") and ":" in line:
            _flush()
            prefix, rest = line.split(":", 1)
            qnum = "".join(ch for ch in prefix if ch.isdigit()) or str(len(questions) + 1)
            current_qid = f"q{qnum}"
            current_chunks.append(rest.strip())
            continue
        if line[:2].isdigit() and (line[2:3] in [".", ")"]):
            _flush()
            qnum = "".join(ch for ch in line.split(maxsplit=1)[0] if ch.isdigit()) or str(len(questions) + 1)
            remainder = line[line.find(".") + 1 :] if "." in line else line[line.find(")") + 1 :]
            current_qid = f"q{qnum}"
            current_chunks.append(remainder.strip())
            continue
        if current_qid is None:
            current_qid = f"q{len(questions) + 1}"
        current_chunks.append(line)

    _flush()
    return questions


def _next_question_id(existing_questions: list[dict[str, str]]) -> str:
    if not existing_questions:
        return "q1"
    nums = []
    for q in existing_questions:
        qid = str(q.get("question_id", ""))
        digits = "".join(ch for ch in qid if ch.isdigit())
        if digits:
            nums.append(int(digits))
    return f"q{(max(nums) + 1) if nums else (len(existing_questions) + 1)}"


@app.get("/", response_class=HTMLResponse)
async def portal_home(request: Request):
    try:
        user = _current_user(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "user": user},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@app.post("/api/auth/register")
async def register(username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    role = role.lower().strip()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Role must be instructor or ta.")
    if db.user_exists(username):
        raise HTTPException(status_code=400, detail="Username already exists.")
    # Use bcrypt for hashing
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.create_user(username, hashed, role)
    return {"message": "Registered successfully."}


@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)
    # Support legacy sha256 for existing test users, or bcrypt
    is_valid = False
    if user:
        if len(user["password_hash"]) == 64 and not user["password_hash"].startswith("$"):
            import hashlib
            if user["password_hash"] == hashlib.sha256(password.encode("utf-8")).hexdigest():
                is_valid = True
        else:
            # Use bcrypt directly
            try:
                is_valid = bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8'))
            except Exception:
                is_valid = False

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    expire = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    token = jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    response = JSONResponse({"message": "Login successful.", "role": user["role"]})
    response.set_cookie("gradeops_session", token, httponly=True, samesite="lax")
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    # JWT is stateless, just delete the cookie
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("gradeops_session")
    return response


@app.get("/api/auth/me")
async def get_current_user(request: Request):
    """Get current authenticated user info."""
    try:
        user = _current_user(request)
        return {"user": user}
    except HTTPException:
        return {"user": None}


@app.post("/api/exams/upload")
async def upload_exam_bundle(
    request: Request,
    exam_name: str = Form(...),
    question_paper: UploadFile = File(...),
    answer_sheets: list[UploadFile] = File(...),
    marking_scheme: UploadFile | None = File(None),
):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "upload")
    if not answer_sheets:
        raise HTTPException(status_code=400, detail="At least one answer sheet is required.")

    session_id = _make_session_id(exam_name)
    question_paper_path = _save_upload(question_paper)
    answer_sheet_paths = [_save_upload(sheet) for sheet in answer_sheets]
    has_marking_scheme = bool(marking_scheme and (marking_scheme.filename or "").strip())
    marking_scheme_path = _save_upload(marking_scheme) if has_marking_scheme else None

    db.create_session(
        session_id=session_id,
        exam_name=exam_name,
        owner=user["username"],
        question_paper_path=question_paper_path,
        answer_sheet_paths=answer_sheet_paths,
        marking_scheme_path=marking_scheme_path,
    )
    return {
        "session_id": session_id,
        "message": "Exam bundle uploaded. Now manually crop each question and extract text.",
        "question_count": 0,
        "questions": [],
    }


@app.post("/api/exams/{session_id}/questions/from-crop")
async def add_question_from_crop(request: Request, session_id: str, payload: QuestionCropPayload):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = _images_from_path(session["question_paper_path"])
    if payload.page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid question paper page_index")

    page_image = pages[payload.page_index]
    x, y, w, h, _ = _sanitize_crop_box(page_image, payload.x, payload.y, payload.w, payload.h)
    crop = extract_snippet(page_image, x, y, w, h)
    _validate_non_empty_crop(crop, "question")
    clean_crop = clean_for_ocr(crop)

    _, encoded = cv2.imencode('.png', clean_crop)
    snippet_path = cloud_storage.upload_bytes(encoded.tobytes(), ".png", "image/png")

    # Download locally temporarily for transcription
    temp_path = cloud_storage.download_to_local_temp(snippet_path)
    question_text = transcribe_snippet(str(temp_path)).strip()
    if not question_text:
        question_text = "OCR returned empty text. Please re-crop this question."

    question_id = _next_question_id(session["extracted_questions"])
    question = {"question_id": question_id, "question_text": question_text}
    session["extracted_questions"].append(question)
    db.update_session_questions(session_id, session["extracted_questions"])
    return {
        "message": "Question extracted from crop.",
        "question": question,
        "questions": session["extracted_questions"],
        "crop_box": {"x": x, "y": y, "w": w, "h": h},
        "crop_preview_base64": _encode_png_base64(clean_crop),
    }


@app.post("/api/exams/{session_id}/crop/preview")
async def preview_crop_region(request: Request, session_id: str, payload: CropPreviewPayload):
    _current_user(request)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    target_path = _resolve_preview_target(session, payload.source, payload.sheet_index)
    pages = _images_from_path(target_path)
    if payload.page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page_index")

    image = pages[payload.page_index]
    x, y, w, h, adjusted = _sanitize_crop_box(image, payload.x, payload.y, payload.w, payload.h)
    crop = extract_snippet(image, x, y, w, h)
    _validate_non_empty_crop(crop, f"{payload.source} crop")
    output = clean_for_ocr(crop) if payload.clean else crop
    preview_b64 = _encode_png_base64(output)
    return {
        "message": "Crop preview generated.",
        "source": payload.source,
        "crop_box": {"x": x, "y": y, "w": w, "h": h},
        "adjusted_to_fit_page": adjusted,
        "preview_base64": preview_b64,
    }


@app.post("/api/exams/{session_id}/coordinates")
async def configure_coordinates(
    request: Request,
    session_id: str,
    payload: ConfigurePayload,
):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.update_session_coordinates(session_id, [item.model_dump() for item in payload.coordinates])
    return {"message": f"Saved {len(payload.coordinates)} coordinate mappings."}


@app.get("/api/exams/{session_id}/preview")
async def preview_sheet_page(
    request: Request,
    session_id: str,
    page_index: int = Query(0, ge=0),
    sheet_index: int = Query(0, ge=0),
    source: str = Query("answer"),
):
    _current_user(request)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if source == "question":
        target_path = session["question_paper_path"]
    else:
        sheets = session["answer_sheet_paths"]
        if sheet_index >= len(sheets):
            raise HTTPException(status_code=400, detail="Invalid sheet_index")
        target_path = sheets[sheet_index]

    pages = _images_from_path(target_path)
    if page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page_index")

    image = pages[page_index]
    payload = _encode_png_bytes(image)
    return Response(content=payload, media_type="image/png")


def _run_grading_job(job_id: str, session_id: str):
    from src.rubric_factory import generate_rubric
    job = grading_jobs[job_id]
    try:
        session = db.get_session(session_id)
        if not session or not session["coordinates"]:
            job["status"] = "failed"
            job["error"] = "Session not found or no coordinates"
            return

        total_items = len(session["answer_sheet_paths"]) * len(session["coordinates"])
        job["total"] = total_items
        job["status"] = "running"
        job["step"] = "rubrics"

        question_rubrics = {}
        for coord in session["coordinates"]:
            qid = coord["question_id"]
            if qid not in question_rubrics:
                saved = db.get_rubric_template(session_id, qid)
                if saved:
                    question_rubrics[qid] = saved["rubric_json"]
                else:
                    question_rubrics[qid] = generate_rubric(
                        coord["question_text"],
                        coord.get("marking_scheme"),
                        max_score=coord.get("max_score")
                    )

        job["step"] = "grading"
        grading_results: list[dict[str, Any]] = []
        progress = 0

        for answer_path in session["answer_sheet_paths"]:
            student_id = Path(answer_path).stem
            student_id = _clean_student_id(student_id)
            pages = _images_from_path(answer_path)

            for coordinate in session["coordinates"]:
                page_index = coordinate["page_index"]
                if page_index >= len(pages):
                    progress += 1
                    job["progress"] = progress
                    continue

                qid = coordinate["question_id"]
                page_img = pages[page_index]
                img_h, img_w = page_img.shape[:2]
                cx, cy, cw, ch = coordinate["x"], coordinate["y"], coordinate["w"], coordinate["h"]

                if cy >= img_h or cx >= img_w:
                    print(f"  [SKIP] Crop out of bounds for {student_id}/{qid}: "
                          f"crop y={cy} but image height={img_h}")
                    grading_results.append({
                        "student_id": student_id,
                        "question_id": qid,
                        "proposed_score": 0,
                        "justification": (
                            f"CROP ERROR: The answer region (y={cy}, h={ch}) is outside this "
                            f"sheet's dimensions ({img_w}x{img_h}). The crop coordinates were "
                            f"drawn on a differently-sized sheet. Please re-crop or resize."
                        ),
                        "error_axes": [],
                        "needs_review": True,
                        "transcription": "[Crop out of bounds]",
                        "snippet_path": "",
                        "accuracy": 0,
                        "rubric": question_rubrics.get(qid),
                        "verification_passed": False,
                        "verification_feedback": "Skipped — crop region does not fit this sheet.",
                    })
                    progress += 1
                    job["progress"] = progress
                    continue

                raw_crop = extract_snippet(page_img, cx, cy, cw, ch)
                if raw_crop is None or raw_crop.size == 0:
                    progress += 1
                    job["progress"] = progress
                    continue
                cleaned_crop = clean_for_ocr(raw_crop)

                _, encoded = cv2.imencode('.png', cleaned_crop)
                snippet_path = cloud_storage.upload_bytes(encoded.tobytes(), ".png", "image/png")

                temp_path = cloud_storage.download_to_local_temp(snippet_path)
                transcription = transcribe_snippet(str(temp_path), context_text=coordinate["question_text"])

                pipeline_state = {
                    "student_id": student_id,
                    "question_text": coordinate["question_text"],
                    "marking_scheme_text": coordinate.get("marking_scheme"),
                    "transcription": transcription,
                    "rubric": question_rubrics.get(qid)
                }

                result = grading_pipeline.invoke(pipeline_state)
                result["student_id"] = student_id
                result["question_id"] = qid
                result["transcription"] = transcription
                result["snippet_path"] = str(snippet_path)
                result["accuracy"] = _score_accuracy(result, transcription)
                result["rubric"] = question_rubrics.get(qid)
                grading_results.append(result)

                progress += 1
                job["progress"] = progress

        job["step"] = "plagiarism"
        plagiarism_flags = detect_rejump_collusion(grading_results)
        db.save_results(session_id, grading_results)
        db.save_plagiarism_flags(session_id, plagiarism_flags)

        review_count = sum(1 for r in grading_results if r.get("accuracy", 1) < 0.7 or r.get("needs_review"))
        job["status"] = "done"
        job["summary"] = {
            "graded_entries": len(grading_results),
            "review_required": review_count,
            "plagiarism_flags_count": len(plagiarism_flags),
        }
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.post("/api/exams/{session_id}/run")
async def run_bulk_grading(request: Request, session_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "grade")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session["coordinates"]:
        raise HTTPException(status_code=400, detail="No question coordinates configured.")

    job_id = str(uuid.uuid4())
    grading_jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "total": 0,
        "step": "init",
        "summary": None,
        "error": None,
    }
    thread = threading.Thread(target=_run_grading_job, args=(job_id, session_id), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "started"}


@app.get("/api/exams/{session_id}/job/{job_id}")
async def poll_grading_job(request: Request, session_id: str, job_id: str):
    _current_user(request)
    job = grading_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "step": job.get("step", ""),
        "summary": job.get("summary"),
        "error": job.get("error"),
    }



@app.get("/api/storage/{filename}")
async def serve_snippet(request: Request, filename: str):
    """Serve a local fallback snippet."""
    _current_user(request)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Check fallback directory
    snippet_file = cloud_storage.LOCAL_STORAGE_DIR / filename
    if snippet_file.exists() and snippet_file.is_file():
        return Response(content=snippet_file.read_bytes(), media_type="image/png")

    # Fallback to old snippets dir for legacy compatibility
    legacy_file = SNIPPETS_DIR / filename
    if legacy_file.exists() and legacy_file.is_file():
        return Response(content=legacy_file.read_bytes(), media_type="image/png")

    raise HTTPException(status_code=404, detail="Snippet not found")


@app.get("/api/exams/{session_id}/dashboard")
async def review_dashboard_data(request: Request, session_id: str):
    user = _current_user(request)
    role = user["role"]
    _check_permission(role, "review")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    results = session["results"]
    review_queue = session["review_queue"]
    plagiarism_flags = session["plagiarism_flags"]

    for r in results:
        r["student_id"] = _clean_student_id(r.get("student_id", ""))
    for r in review_queue:
        r["student_id"] = _clean_student_id(r.get("student_id", ""))

    # Build analytics summary from real pipeline data
    total = len(results)
    if total > 0:
        scores = [r.get("proposed_score", 0) for r in results]
        accuracies = [r.get("accuracy", 0) for r in results]
        avg_score = round(sum(scores) / total, 2)
        avg_accuracy = round(sum(accuracies) / total, 2)

        # Error axis distribution from grader.py outputs
        error_dist: dict[str, int] = {}
        for r in results:
            for axis in r.get("error_axes", []):
                label = axis if isinstance(axis, str) else str(axis)
                error_dist[label] = error_dist.get(label, 0) + 1

        # Rubric data (if present in pipeline results)
        rubrics = {}
        for r in results:
            qid = r.get("question_id", "")
            if qid and qid not in rubrics and r.get("rubric"):
                rubrics[qid] = r["rubric"]
    else:
        avg_score = 0
        avg_accuracy = 0
        error_dist = {}
        rubrics = {}

    return JSONResponse(
        {
            "session_id": session_id,
            "exam_name": session["exam_name"],
            "extracted_questions": session["extracted_questions"],
            "results": results,
            "review_queue": review_queue,
            "plagiarism_flags": plagiarism_flags,
            "analytics": {
                "total_graded": total,
                "review_count": len(review_queue),
                "plagiarism_count": len(plagiarism_flags),
                "avg_score": avg_score,
                "avg_accuracy": avg_accuracy,
                "error_distribution": error_dist,
                "rubrics": rubrics,
            },
        }
    )


@app.post("/api/exams/{session_id}/review/{result_id}/approve")
async def approve_result(request: Request, session_id: str, result_id: int):
    user = _current_user(request)
    _check_permission(user["role"], "review")
    db.update_result_review(result_id, "approved")
    return {"status": "success", "message": f"Result {result_id} approved"}


class OverridePayload(BaseModel):
    new_score: float


@app.post("/api/exams/{session_id}/review/{result_id}/override")
async def override_result(request: Request, session_id: str, result_id: int, payload: OverridePayload):
    user = _current_user(request)
    _check_permission(user["role"], "review")
    db.update_result_review(result_id, "overridden", new_score=payload.new_score)
    return {"status": "success", "message": f"Result {result_id} overridden to {payload.new_score}"}


# ── Rubric Template Endpoints ──

class RubricCriterion(BaseModel):
    description: str = Field(..., min_length=1)
    points: float = Field(..., ge=0)
    type: str = Field("conceptual")


class RubricPayload(BaseModel):
    question_id: str = Field(..., min_length=1)
    max_score: float = Field(..., gt=0)
    criteria: list[RubricCriterion]


@app.post("/api/exams/{session_id}/rubrics")
async def save_rubric(request: Request, session_id: str, payload: RubricPayload):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rubric_dict = {
        "question_id": payload.question_id,
        "max_score": payload.max_score,
        "criteria": [{"id": f"c{i+1}", **c.model_dump()} for i, c in enumerate(payload.criteria)],
    }
    db.save_rubric_template(session_id, payload.question_id, rubric_dict)
    return {"message": f"Rubric saved for {payload.question_id}", "rubric": rubric_dict}


@app.get("/api/exams/{session_id}/rubrics")
async def get_rubrics(request: Request, session_id: str):
    _current_user(request)
    templates = db.get_rubric_templates(session_id)
    rubrics = {t["question_id"]: t["rubric_json"] for t in templates}
    return {"rubrics": rubrics}


@app.delete("/api/exams/{session_id}/rubrics/{question_id}")
async def delete_rubric(request: Request, session_id: str, question_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    db.delete_rubric_template(session_id, question_id)
    return {"message": f"Rubric deleted for {question_id}"}


@app.post("/api/exams/{session_id}/rubrics/{question_id}/generate")
async def generate_rubric_for_question(request: Request, session_id: str, question_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "configure")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    question = next((q for q in session["extracted_questions"] if q["question_id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    from src.rubric_factory import generate_rubric
    rubric = generate_rubric(question["question_text"])
    if rubric:
        db.save_rubric_template(session_id, question_id, rubric)
    return {"rubric": rubric}


# ── Re-grade Single Answer ──

@app.post("/api/exams/{session_id}/regrade/{result_id}")
async def regrade_single(request: Request, session_id: str, result_id: int):
    user = _current_user(request)
    _check_permission(user["role"], "grade")
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    existing = db.get_result_by_id(result_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Result not found")

    snippet_path = existing.get("snippet_path", "")
    question_id = existing.get("question_id", "")
    student_id = existing.get("student_id", "")

    coord = next((c for c in session.get("coordinates", []) if c["question_id"] == question_id), None)
    question_text = coord["question_text"] if coord else ""
    marking_scheme = coord.get("marking_scheme") if coord else None

    transcription = existing.get("transcription", "")
    if snippet_path:
        try:
            temp_path = cloud_storage.download_to_local_temp(snippet_path)
            transcription = transcribe_snippet(str(temp_path), context_text=question_text)
        except Exception:
            pass

    saved_rubric = db.get_rubric_template(session_id, question_id)
    rubric = saved_rubric["rubric_json"] if saved_rubric else None
    if not rubric and question_text:
        from src.rubric_factory import generate_rubric
        rubric = generate_rubric(question_text, marking_scheme)

    pipeline_state = {
        "student_id": student_id,
        "question_text": question_text,
        "marking_scheme_text": marking_scheme,
        "transcription": transcription,
        "rubric": rubric,
    }
    result = grading_pipeline.invoke(pipeline_state)
    result["student_id"] = student_id
    result["question_id"] = question_id
    result["transcription"] = transcription
    result["snippet_path"] = snippet_path
    result["accuracy"] = _score_accuracy(result, transcription)
    result["rubric"] = rubric

    updated = db.update_single_result(result_id, result)
    return {"message": "Re-grade complete", "result": updated}


@app.post("/api/sandbox/create")
async def create_sandbox(request: Request):
    user = _current_user(request)
    data = await request.json()
    preset = data.get("preset", "custom")

    session_id = _make_session_id(exam_name if preset == "custom" else preset)

    if preset == "math":
        exam_name = "Calculus I - Midterm Simulation"
        num_students = 80
        num_questions = 5
        max_score_val = 20
        include_plagiarism = True
    elif preset == "history":
        exam_name = "World History Final Simulation"
        num_students = 80
        num_questions = 5
        max_score_val = 100
        include_plagiarism = True
    else:
        exam_name = "Custom Sandbox Session"
        num_students = int(data.get("students", 10))
        num_questions = int(data.get("questions", 4))
        max_score_val = int(data.get("max_score", 10))
        include_plagiarism = data.get("include_plagiarism", True)

    db.create_session(
        session_id=session_id,
        exam_name=exam_name,
        owner=user["username"],
        question_paper_path="",
        answer_sheet_paths=[],
        marking_scheme_path=""
    )

    import random

    # Variety Pools - Enhanced for thousands of unique combinations
    topics = ["Physics", "Calculus", "World History", "Org Chemistry", "Macroeconomics", "Software Arch"]
    verbs = ["demonstrated", "showed", "exhibited", "presented", "displayed", "provided"]
    strengths = ["excellent understanding", "solid conceptual grasp", "thorough derivation", "logical flow", "deep context"]
    weaknesses = ["minor notation slip", "calculation error in step 2", "lack of specific dates", "formatting inconsistency", "missing units"]

    trans_templates = [
        "The {term} is {val}. Calculated using {method}.",
        "By applying {theory}, we get {result}.",
        "The primary cause was {event} which led to {outcome}.",
        "The solution for {eq} is found via {formula}.",
        "Analysis of {topic} reveals {insight}."
    ]

    terms = ["force", "integral", "derivative", "reaction", "constant", "variable"]
    vals = ["$F=ma$", "$x^2/2$", "$10.5N$", "2019", "Versailles", "196J"]
    methods = ["standard derivation", "substitution", "first principles", "contextual analysis"]
    theories = ["fundamental theorem", "Newton's laws", "marginal utility", "Plato's Republic"]

    def gen_unique_trans():
        tpl = random.choice(trans_templates)
        return tpl.format(
            term=random.choice(terms), val=random.choice(vals), method=random.choice(methods),
            theory=random.choice(theories), result=random.choice(vals), event="Revolution",
            outcome="Urbanization", eq=r"$\int x dx$", formula="Quadratic Rule", topic="The Sea", insight="depth"
        ) + f" [Ref:{uuid.uuid4().hex[:4]}]"

    def gen_unique_just(score, max_s):
        v = random.choice(verbs)
        s = random.choice(strengths)
        w = random.choice(weaknesses)
        if score >= max_s * 0.9:
            return f"Student {v} {s}. All steps are technically sound and clear."
        return f"Student {v} {s}, however, there is a {w} that resulted in a score of {score}/{max_s}."

    # Get available snippet images for variety
    all_snippets = [f.name for f in SNIPPETS_DIR.glob("*.png")]
    if not all_snippets:
        all_snippets = ["page_0_question_1.png"]

    questions = []
    sandbox_rubrics = {}

    # Define specific questions for math and history
    if preset == "math":
        math_questions = [
            ("Q1", "Find the derivative of f(x) = x^3 + 3x^2 - 5x + 2 using the power rule and chain rule. Show all intermediate steps."),
            ("Q2", "Evaluate the definite integral ∫₀² (x² + 2x)dx. Show the integration process and verify with the Fundamental Theorem of Calculus."),
            ("Q3", "Determine the critical points and classify them as local maxima or minima for f(x) = x³ - 3x²."),
            ("Q4", "Solve the differential equation dy/dx = 2xy with initial condition y(0) = 1. Find the particular solution."),
            ("Q5", "Evaluate the limit lim(x→0) (sin(x) - x)/x³ using L'Hôpital's rule or Taylor series expansion.")
        ]
        for qid, q_text in math_questions:
            questions.append({
                "question_id": qid,
                "question_text": q_text,
                "page_index": 0,
                "coords": {"x": 100, "y": 100 * int(qid[1]), "w": 500, "h": 80}
            })
            sandbox_rubrics[qid] = {
                "question_id": qid,
                "max_score": max_score_val,
                "criteria": [
                    {"id": f"{qid}_c1", "description": "Correct identification and application of mathematical rules (power rule, chain rule, integration techniques)", "points": round(max_score_val * 0.30, 1), "type": "computational"},
                    {"id": f"{qid}_c2", "description": "Accurate algebraic manipulation and computation with proper handling of signs and coefficients", "points": round(max_score_val * 0.25, 1), "type": "computational"},
                    {"id": f"{qid}_c3", "description": "Clear step-by-step reasoning showing logical progression from problem statement to solution", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c4", "description": "Correct interpretation and application of mathematical theorems (Fundamental Theorem, L'Hôpital's rule)", "points": round(max_score_val * 0.15, 1), "type": "conceptual"},
                    {"id": f"{qid}_c5", "description": "Proper notation, labeling of variables, and presentation of final answer with units where applicable", "points": round(max_score_val * 0.10, 1), "type": "presentation"}
                ]
            }
    else:
        history_questions = [
            ("Q1", "Analyze the major causes of World War I, discussing how militarism, alliances, imperialism, and nationalism contributed to the outbreak of the war."),
            ("Q2", "Explain the significance of the Treaty of Versailles in shaping the political and economic landscape of Europe in the interwar period."),
            ("Q3", "Discuss the role of Gandhi's philosophy of nonviolent resistance in India's independence movement. Include specific campaigns and their outcomes."),
            ("Q4", "Evaluate the impact of the Cold War on global politics, focusing on at least three major proxy conflicts and their consequences."),
            ("Q5", "Analyze the causes and consequences of the French Revolution, examining how it transformed French society and influenced revolutionary movements worldwide.")
        ]
        for qid, q_text in history_questions:
            questions.append({
                "question_id": qid,
                "question_text": q_text,
                "page_index": 0,
                "coords": {"x": 100, "y": 100 * int(qid[1]), "w": 500, "h": 80}
            })
            sandbox_rubrics[qid] = {
                "question_id": qid,
                "max_score": max_score_val,
                "criteria": [
                    {"id": f"{qid}_c1", "description": "Comprehensive identification and analysis of key causes/factors with historical evidence", "points": round(max_score_val * 0.30, 1), "type": "conceptual"},
                    {"id": f"{qid}_c2", "description": "Accurate citation of specific dates, events, and historical figures to support arguments", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c3", "description": "Logical organization with clear thesis statement, supporting evidence, and coherent conclusion", "points": round(max_score_val * 0.20, 1), "type": "presentation"},
                    {"id": f"{qid}_c4", "description": "Critical analysis of cause-and-effect relationships and long-term consequences", "points": round(max_score_val * 0.15, 1), "type": "conceptual"},
                    {"id": f"{qid}_c5", "description": "Balanced perspective considering multiple viewpoints and avoiding oversimplification", "points": round(max_score_val * 0.15, 1), "type": "conceptual"}
                ]
            }

    db.update_session_questions(session_id, questions)

    results = []
    error_types = ["notation", "calculation", "conceptual", "formatting", "reasoning", "presentation"]

    # Extensive justification templates for different score ranges
    excellent_justifications = [
        "The student has demonstrated exceptional mastery of the subject matter. The solution is mathematically sound, with perfect application of rules and theorems. The reasoning is crystal clear, showing a deep conceptual understanding that goes beyond mere procedural knowledge. Every step is meticulously executed with proper justification. The presentation is professional, with clear notation, well-labeled figures, and a complete final answer. This represents work of exceptional quality that meets all rubric criteria at the highest level.",
        "An exemplary response that demonstrates thorough understanding of all key concepts. The student correctly identified the appropriate methods and executed them flawlessly. The solution shows sophisticated reasoning, with proper use of mathematical notation and logical flow. All intermediate steps are shown and justified. The final answer is complete and correct. The presentation reflects a strong grasp of the material and attention to detail.",
        "Outstanding work demonstrating comprehensive understanding of the underlying principles. The approach is efficient and mathematically rigorous. Every calculation is accurate, and the logic flows seamlessly from one step to the next. The student shows excellent command of the subject, with clear articulation of the reasoning process. The solution is complete, well-organized, and meets all criteria for full marks."
    ]

    good_justifications = [
        "The student demonstrates a solid understanding of the core concepts and approaches the problem correctly. The methodology is appropriate, and most calculations are accurate. There is one minor computational error or oversight that slightly affected the final result, but the overall approach remains sound. The reasoning is generally clear, though some steps could benefit from more explicit explanation. With minor corrections, this would be an excellent submission.",
        "Good work showing competent handling of the material. The student correctly applies the main techniques but makes a small error in execution (such as a sign mistake, unit conversion error, or minor algebraic slip). The conceptual understanding is evident, and the solution structure is appropriate. The error does not fundamentally undermine the approach. Partial credit is warranted for the correct methodology and reasonable execution.",
        "The student shows good comprehension of the fundamental principles and applies appropriate methods. There is a minor computational mistake in an intermediate step that propagates to the final answer, but the overall approach demonstrates understanding. The presentation is adequate but could be more polished. The student should review the specific error type to improve accuracy in future work."
    ]

    partial_justifications = [
        "The student demonstrates partial understanding of the concepts but makes significant errors in application. The initial approach is reasonable, but fundamental mistakes in execution (such as applying the wrong rule, misinterpreting the problem, or consistent computational errors) lead to an incorrect solution. Some credit is awarded for attempting the correct method and showing some understanding of the underlying principles, but the errors are substantial enough to warrant a lower score.",
        "The response shows some grasp of basic concepts but fails to correctly apply the required methods. The student makes multiple errors in calculation and reasoning that indicate gaps in understanding. The solution demonstrates awareness of what needs to be done but lacks the technical skill to execute it correctly. Partial credit is given for the partial understanding shown.",
        "The student identifies the general approach needed but struggles with the technical execution. Multiple errors in calculation, formula application, or logical reasoning are present throughout the solution. The student shows some knowledge of the subject but cannot apply it correctly. The work demonstrates understanding of the question's requirements but fails to deliver a correct solution."
    ]

    poor_justifications = [
        "The student demonstrates fundamental misunderstanding of the core concepts. The approach taken is incorrect, with application of wrong formulas or methods that do not apply to this type of problem. The reasoning is unclear and contains multiple logical errors. The solution shows significant gaps in knowledge that prevent meaningful progress toward the correct answer. Major conceptual errors make it difficult to award any significant credit beyond acknowledgment of the attempt.",
        "The response indicates lack of preparation or understanding of basic principles. The student either attempts an irrelevant approach or produces work that does not address the question. Errors are numerous and fundamental, suggesting confusion about basic concepts. The work cannot be credited beyond minimal acknowledgment of the attempt.",
        "Serious conceptual errors permeate this response. The student applies incorrect principles, makes unsupported claims, and demonstrates fundamental misunderstanding of the topic. The solution shows no evidence of the required analytical skills. This represents a significant gap in student preparation and understanding."
    ]

    def gen_extensive_justification(score, max_s):
        pct = score / max_s
        if pct >= 0.90:
            return random.choice(excellent_justifications)
        elif pct >= 0.70:
            return random.choice(good_justifications)
        elif pct >= 0.40:
            return random.choice(partial_justifications)
        else:
            return random.choice(poor_justifications)

    transcription_templates_math = [
        r"f'(x) = 3x^2 + 6x - 5. Applying the power rule: d/dx(x^n) = nx^{n-1}.",
        r"∫(x² + 2x)dx = [x³/3 + x²]₀² = (8/3 + 4) - 0 = 20/3",
        r"Critical points at x = 0 and x = 2. Using second derivative test: f''(0) = -6 (max), f''(2) = 6 (min)",
        r"dy/dx = 2xy → dy/y = 2x dx → ln|y| = x² + C → y = Ce^{x²}",
        r"Using Taylor series: sin(x) = x - x³/6 + ..., so (sin(x) - x)/x³ → -1/6 as x→0"
    ]

    transcription_templates_history = [
        "The four main causes were militarism (arms race), alliances (Triple Entente/Central Powers), imperialism (colonial competition), and nationalism (ethnic tensions in Balkans). The assassination of Archduke Franz Ferdinand triggered the war.",
        "The Treaty imposed heavy reparations (132 billion gold marks), territorial losses (Alsace-Lorraine to France, Polish corridor), and war guilt clause on Germany. This led to political instability, economic crisis, and rise of Nazism.",
        "Gandhi's nonviolence (Satyagraha) included Salt March (1930), Quit India (1942), and Champaran (1917). These campaigns mobilized millions and eventually forced British to negotiate independence.",
        "Proxy conflicts included Korean War (1950-53), Vietnam War (1955-75), and Afghan War (1979-89). These prolonged Cold War tensions and resulted in millions of casualties while avoiding direct US-USR confrontation.",
        "Causes included financial crisis, inequality, Enlightenment ideas, and weak leadership. Consequences: execution of Louis XVI, Reign of Terror, rise of Napoleon, and spread of revolutionary ideals across Europe."
    ]

    all_transcriptions = transcription_templates_math if preset == "math" else transcription_templates_history

    for s_idx in range(1, num_students + 1):
        student_id = f"student_{s_idx:03d}"
        for q_idx in range(1, num_questions + 1):
            qid = f"Q{q_idx}"

            # Generate score with realistic distribution
            score = round(random.uniform(0.3, 1.0) * max_score_val, 1)
            accuracy = random.uniform(0.65, 0.99)
            needs_review = (accuracy < 0.75 or random.random() < 0.08)

            axes = []
            if score < max_score_val * 0.9:
                axes = random.sample(error_types, random.randint(1, 2))

            # Get unique transcription for this student/question
            trans_base = all_transcriptions[q_idx - 1]
            trans_with_id = f"{trans_base} [ID:{student_id}-{qid}]"

            results.append({
                "student_id": student_id,
                "question_id": qid,
                "proposed_score": score,
                "justification": gen_extensive_justification(score, max_score_val),
                "needs_review": 1 if needs_review else 0,
                "error_axes": axes,
                "transcription": trans_with_id,
                "snippet_path": random.choice(all_snippets),
                "accuracy": round(accuracy, 2),
                "rubric": sandbox_rubrics[qid]
            })

    db.save_results(session_id, results)

    if include_plagiarism:
        # Generate multiple plagiarism flags (3-5 for 80 students)
        s_pool = [f"student_{i:03d}" for i in range(1, num_students + 1)]
        num_flags = random.randint(3, 5)
        flags = []
        for _ in range(num_flags):
            pair = random.sample(s_pool, 2)
            flags.append({
                "pair": (pair[0], pair[1]),
                "confidence": round(random.uniform(0.88, 0.97), 2),
                "shared_error_axes": random.sample(["conceptual", "notation", "computational", "reasoning"], 2),
                "reason": f"Suspiciously identical logical structure, matching error patterns in {qid}, and nearly identical phrasing detected by ReJump integrity system. Both students made the same unusual mistake in their approach."
            })
        db.save_plagiarism_flags(session_id, flags)

    return {"session_id": session_id, "message": f"Sandbox '{preset}' created with {num_students * num_questions} unique results."}


class ReviewPayload(BaseModel):
    status: str = Field(..., pattern="^(approved|overridden)$")
    new_score: float | None = None

@app.post("/api/exams/{session_id}/review/{result_id}")
async def update_review_status(request: Request, session_id: str, result_id: int, payload: ReviewPayload):
    user = _current_user(request)
    _check_permission(user["role"], "review")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    updated = db.update_result_review(result_id, payload.status, payload.new_score)
    if not updated:
        raise HTTPException(status_code=404, detail="Result not found")

    return {"message": "Review status updated successfully", "result": updated}


class SandboxPayload(BaseModel):
    students: int = 10
    questions: int = 4
    max_score: float = 10.0
    include_plagiarism: bool = True
    include_low_conf: bool = True

@app.post("/api/sandbox/generate")
async def generate_sandbox_data(request: Request, preset: str = Query(None), payload: SandboxPayload = None):
    user = _current_user(request)

    session_id = f"sandbox_{uuid.uuid4().hex[:8]}"
    db.create_session(
        session_id=session_id,
        exam_name=f"Sandbox: {preset.capitalize() if preset else 'Custom'} Exam",
        owner=user["username"],
        question_paper_path="",
        answer_sheet_paths=[],
    )

    results = []
    flags = []
    import random

    if preset == "math":
        questions = [{"question_id": "q1", "question_text": "Calculate the derivative of f(x) = x^2 * sin(x)"},
                    {"question_id": "q2", "question_text": "Evaluate the integral of e^(2x) dx"}]
        db.update_session_questions(session_id, questions)

        results = [
            {"student_id": "std_01", "question_id": "q1", "proposed_score": 8, "needs_review": False, "accuracy": 0.9, "justification": "Correct application of product rule, but minor sign error at the end.", "error_axes": ["computational"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "f'(x) = 2x sin(x) - x^2 cos(x)", "snippet_path": ""},
            {"student_id": "std_02", "question_id": "q1", "proposed_score": 4, "needs_review": True, "accuracy": 0.6, "justification": "Incorrect rule used.", "error_axes": ["conceptual"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "f'(x) = 2x cos(x)", "snippet_path": ""},
            {"student_id": "std_03", "question_id": "q2", "proposed_score": 10, "needs_review": False, "accuracy": 0.95, "justification": "Perfect step-by-step.", "error_axes": [], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 * e^(2x) + C", "snippet_path": ""},
            {"student_id": "std_04", "question_id": "q2", "proposed_score": 10, "needs_review": False, "accuracy": 0.95, "justification": "Perfect step-by-step.", "error_axes": [], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 e^(2x) + C", "snippet_path": ""},
            {"student_id": "std_05", "question_id": "q2", "proposed_score": 8, "needs_review": False, "accuracy": 0.85, "justification": "Forgot the constant of integration.", "error_axes": ["notation"], "rubric": {"max_score": 10, "criteria": [{"description": "Correctly applies integration/derivation rules", "points": 6, "type": "conceptual"}, {"description": "Accurate arithmetic and final sign", "points": 4, "type": "computational"}]}, "transcription": "1/2 e^(2x)", "snippet_path": ""},
        ]
        flags = [
            {"pair": ("std_03", "std_04"), "confidence": 0.98, "reason": "Identical logical jumps and same unusual notation used.", "shared_error_axes": []}
        ]

    elif preset == "history":
        questions = [{"question_id": "q1", "question_text": "Discuss the causes of World War I."}]
        db.update_session_questions(session_id, questions)

        results = [
            {"student_id": "std_01", "question_id": "q1", "proposed_score": 15, "needs_review": False, "accuracy": 0.85, "justification": "Good coverage of MANIA causes.", "error_axes": [], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "The main causes were militarism, alliances, imperialism...", "snippet_path": ""},
            {"student_id": "std_02", "question_id": "q1", "proposed_score": 5, "needs_review": True, "accuracy": 0.5, "justification": "Confused WWI with WWII.", "error_axes": ["conceptual"], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "Hitler invaded Poland which started the war...", "snippet_path": ""},
            {"student_id": "std_03", "question_id": "q1", "proposed_score": 2, "needs_review": True, "accuracy": 0.4, "justification": "Unreadable handwriting.", "error_axes": ["presentation"], "rubric": {"max_score": 20, "criteria": [{"description": "Identifies primary geopolitical causes", "points": 10, "type": "conceptual"}, {"description": "Cites specific historical events/dates", "points": 6, "type": "presentation"}, {"description": "Cohesive argument structure", "points": 4, "type": "presentation"}]}, "transcription": "[?] caused the [?] in 1914...", "snippet_path": ""},
        ]

    else:
        # Custom Dataset Generation
        if not payload:
            payload = SandboxPayload()
        num_students = max(payload.students, 25)
        num_questions = max(payload.questions, 5)
        payload.students = num_students
        payload.questions = num_questions

        questions = []
        for i in range(1, payload.questions + 1):
            questions.append({"question_id": f"q{i}", "question_text": f"Simulated Question {i} - Topic {random.choice(['Alpha', 'Beta', 'Gamma'])}{i}"})
        db.update_session_questions(session_id, questions)

        error_types = ["computational", "conceptual", "notation", "presentation"]

        for s in range(1, payload.students + 1):
            student_id = f"student_{s:03d}"
            for q in questions:
                # Base performance for this student/question
                score_pct = random.random()

                # Introduce errors
                axes = []
                if score_pct < 0.8:
                    axes.append(random.choice(error_types))
                if score_pct < 0.4:
                    axes.append(random.choice(error_types))

                # Determine accuracy / needs review
                accuracy = random.uniform(0.7, 0.98)
                needs_review = False

                if payload.include_low_conf and random.random() < 0.15:
                    accuracy = random.uniform(0.3, 0.6)
                    needs_review = True
                    axes.append("presentation")

                if score_pct < 0.3:
                    needs_review = True

                score = round(score_pct * payload.max_score, 1)

                results.append({
                    "student_id": student_id,
                    "question_id": q["question_id"],
                    "proposed_score": score,
                    "needs_review": needs_review,
                    "accuracy": accuracy,
                    "justification": (
                        "The student demonstrated excellent understanding. Flawless derivation with sound logic and proper units." if score_pct > 0.9 else
                        "Good overall approach. Grasped core concepts but made a minor mathematical error in an intermediate step." if score_pct > 0.7 else
                        "Identified the starting equations but failed to apply boundary conditions correctly. Notation lacks rigor." if score_pct > 0.4 else
                        "Shows a fundamental misunderstanding of the topic. Applied incorrect physical laws. No credit for main derivation."
                    )
                    if accuracy > 0.6 else "OCR confidence is very low due to illegible handwriting or smudges. Manual TA review strongly recommended.",
                    "error_axes": list(set(axes)),
                    "rubric": {"max_score": payload.max_score, "criteria": [{"description": "Core conceptual understanding", "points": round(payload.max_score * 0.5, 1), "type": "conceptual"}, {"description": "Execution and methodology", "points": round(payload.max_score * 0.3, 1), "type": "computational"}, {"description": "Clarity and notation", "points": round(payload.max_score * 0.2, 1), "type": "presentation"}]},
                    "transcription": f"Simulated student response for {q['question_id']}..." if accuracy > 0.6 else "Simul[?] student re[?] for [?]...",
                    "snippet_path": ""
                })

        if payload.include_plagiarism and payload.students >= 2:
            num_flags = random.randint(1, max(1, payload.students // 5))
            for _ in range(num_flags):
                s1, s2 = random.sample(range(1, payload.students + 1), 2)
                flags.append({
                    "pair": (f"student_{s1:03d}", f"student_{s2:03d}"),
                    "confidence": random.uniform(0.9, 0.99),
                    "reason": "High semantic similarity in incorrect reasoning steps.",
                    "shared_error_axes": [random.choice(error_types)]
                })

    db.save_results(session_id, results)
    db.save_plagiarism_flags(session_id, flags)

    return {"session_id": session_id, "message": "Sandbox data generated successfully."}



@app.get("/api/exams/{session_id}/report", response_class=HTMLResponse)
async def generate_grade_report(request: Request, session_id: str):
    user = _current_user(request)
    _check_permission(user["role"], "review")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    results = session.get("results", [])

    # Group by student
    students = {}
    for r in results:
        sid = r.get("student_id", "Unknown")
        if sid not in students:
            students[sid] = {"results": [], "total_score": 0}

        students[sid]["results"].append(r)
        students[sid]["total_score"] += float(r.get("proposed_score", 0))

    # Round totals
    for sid in students:
        students[sid]["total_score"] = round(students[sid]["total_score"], 1)

    # Sort students by ID
    students = dict(sorted(students.items()))

    import datetime
    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={
            "session": session,
            "students": students,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
>>>>>>> 15b1898f1ea7244db1b396e1e9d47837e0f8d22b
