import json
import os
import sqlite3
import time
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = Path(os.getenv("TIKDOWNLOAD_DB_PATH", "/tmp/tikdownload.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection

def initialize():
    with connect() as db:
        if not DATABASE_URL:
            db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS media (
            id TEXT PRIMARY KEY, path TEXT NOT NULL, filename TEXT NOT NULL, size BIGINT NOT NULL,
            content_type TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, media_id TEXT NOT NULL,
            operation TEXT NOT NULL, resolution TEXT NOT NULL, output_id TEXT, filename TEXT,
            size_bytes BIGINT, original_size_bytes BIGINT, size_change_bytes BIGINT,
            download_url TEXT, expires_in_seconds INTEGER)""")
        db.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")

def _sql(query):
    return query.replace("?", "%s") if DATABASE_URL else query

def save_media(media_id, record):
    with connect() as db:
        db.execute(_sql("INSERT INTO media(id,path,filename,size,content_type,expires_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,filename=excluded.filename,size=excluded.size,content_type=excluded.content_type,expires_at=excluded.expires_at"),
            (media_id, record["path"], record["filename"], record["size"], record["content_type"], record["expires_at"]))

def get_media(media_id):
    with connect() as db:
        row = db.execute(_sql("SELECT * FROM media WHERE id=?"), (media_id,)).fetchone()
        return dict(row) if row else None

def list_media():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM media").fetchall()]

def delete_media(media_id):
    with connect() as db:
        db.execute(_sql("DELETE FROM media WHERE id=?"), (media_id,))

def create_job(job):
    with connect() as db:
        db.execute(_sql("INSERT INTO jobs(id,status,progress,message,created_at,media_id,operation,resolution) VALUES(?,?,?,?,?,?,?,?)"),
            (job["id"], job["status"], job["progress"], job["message"], job["created_at"], job["media_id"], job["operation"], job["resolution"]))

def update_job(job_id, **fields):
    allowed = {"status","progress","message","output_id","filename","size_bytes","original_size_bytes","size_change_bytes","download_url","expires_in_seconds"}
    fields = {k:v for k,v in fields.items() if k in allowed}
    if not fields: return
    columns = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect() as db:
        db.execute(_sql(f"UPDATE jobs SET {columns} WHERE id=?"), values)

def get_job(job_id):
    with connect() as db:
        row = db.execute(_sql("SELECT * FROM jobs WHERE id=?"), (job_id,)).fetchone()
        return dict(row) if row else None

def list_queued_jobs():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at").fetchall()]
