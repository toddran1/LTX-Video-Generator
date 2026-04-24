import json
import os
import shutil
import time
import uuid
from threading import Lock


STATE_ROOT = os.environ.get(
    "LTX_RUNTIME_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime"),
)
JOBS_PATH = os.path.join(STATE_ROOT, "v2v_jobs.json")
REQUESTS_ROOT = os.path.join(STATE_ROOT, "requests")

_LOCK = Lock()


def ensure_runtime_dirs():
    os.makedirs(STATE_ROOT, exist_ok=True)
    os.makedirs(REQUESTS_ROOT, exist_ok=True)


def _load_jobs_unlocked():
    if not os.path.exists(JOBS_PATH):
        return []
    with open(JOBS_PATH, "r", encoding="utf-8") as jobs_file:
        return json.load(jobs_file)


def _save_jobs_unlocked(jobs):
    ensure_runtime_dirs()
    with open(JOBS_PATH, "w", encoding="utf-8") as jobs_file:
        json.dump(jobs, jobs_file, indent=2)


def list_jobs():
    with _LOCK:
        return _load_jobs_unlocked()


def get_job(job_id):
    with _LOCK:
        for job in _load_jobs_unlocked():
            if job.get("id") == job_id:
                return job
    return None


def latest_active_job():
    active_statuses = {"starting", "running", "cancelling"}
    jobs = list_jobs()
    active = [job for job in jobs if job.get("status") in active_statuses]
    if not active:
        return None
    return max(active, key=lambda job: job.get("updated_at", 0))


def create_job(record):
    ensure_runtime_dirs()
    job = dict(record)
    job["id"] = job.get("id") or str(uuid.uuid4())
    timestamp = time.time()
    job["created_at"] = job.get("created_at", timestamp)
    job["updated_at"] = job.get("updated_at", timestamp)

    with _LOCK:
        jobs = _load_jobs_unlocked()
        jobs.append(job)
        _save_jobs_unlocked(jobs)
    return job


def update_job(job_id, **updates):
    with _LOCK:
        jobs = _load_jobs_unlocked()
        for index, job in enumerate(jobs):
            if job.get("id") != job_id:
                continue
            updated = dict(job)
            updated.update(updates)
            updated["updated_at"] = time.time()
            jobs[index] = updated
            _save_jobs_unlocked(jobs)
            return updated
    return None


def persist_request_files(input_video, reference_files):
    ensure_runtime_dirs()
    request_id = str(uuid.uuid4())
    request_dir = os.path.join(REQUESTS_ROOT, request_id)
    os.makedirs(request_dir, exist_ok=True)

    video_ext = os.path.splitext(input_video)[1] or ".mp4"
    video_dest = os.path.join(request_dir, f"input{video_ext}")
    shutil.copy(input_video, video_dest)

    reference_paths = []
    for index, reference_file in enumerate(reference_files or []):
        ext = os.path.splitext(reference_file)[1] or ".png"
        ref_dest = os.path.join(request_dir, f"reference_{index}{ext}")
        shutil.copy(reference_file, ref_dest)
        reference_paths.append(ref_dest)

    return request_dir, video_dest, reference_paths
