import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("TIKDOWNLOAD_DB_PATH", "/tmp/tikdownload.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection

def initialize():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, path TEXT NOT NULL, filename TEXT NOT NULL, size INTEGER NOT NULL, content_type TEXT NOT NULL, expires_at REAL NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL, created_at REAL NOT NULL, media_id TEXT NOT NULL, operation TEXT NOT NULL, resolution TEXT NOT NULL, output_id TEXT, filename TEXT, size_bytes INTEGER, original_size_bytes INTEGER, size_change_bytes INTEGER, download_url TEXT, expires_in_seconds INTEGER)")
        db.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")

def save_media(media_id, record):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO media(id,path,filename,size,content_type,expires_at) VALUES(?,?,?,?,?,?)",
            (media_id, record["path"], record["filename"], record["size"], record["content_type"], record["expires_at"]))

def get_media(media_id):
    with connect() as db:
        row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        return dict(row) if row else None

def list_media():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM media").fetchall()]

def delete_media(media_id):
    with connect() as db:
        db.execute("DELETE FROM media WHERE id=?", (media_id,))

def create_job(job):
    with connect() as db:
        db.execute("INSERT INTO jobs(id,status,progress,message,created_at,media_id,operation,resolution) VALUES(?,?,?,?,?,?,?,?)",
            (job["id"], job["status"], job["progress"], job["message"], job["created_at"], job["media_id"], job["operation"], job["resolution"]))

def update_job(job_id, **fields):
    allowed = {"status","progress","message","output_id","filename","size_bytes","original_size_bytes","size_change_bytes","download_url","expires_in_seconds"}
    fields = {k:v for k,v in fields.items() if k in allowed}
    if not fields:
        return
    columns = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect() as db:
        db.execute(f"UPDATE jobs SET {columns} WHERE id=?", values)

def get_job(job_id):
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

def list_queued_jobs():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at").fetchall()]

initialize()
