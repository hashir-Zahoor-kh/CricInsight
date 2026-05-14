#!/usr/bin/env python3
"""Upload local Cricsheet archives to S3.

Reads CRICSHEET_S3_BUCKET from the environment and uploads every file
under backend/cricsheet_data/ preserving directory structure as S3 keys
under the prefix cricsheet_data/.

Usage:
    CRICSHEET_S3_BUCKET=my-bucket python scripts/upload_cricsheet_to_s3.py

Useful when running the ingestion seed CLI from an ECS task that pulls
data from S3 instead of downloading fresh Cricsheet archives each deploy.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

BUCKET = os.environ.get("CRICSHEET_S3_BUCKET", "").strip()
if not BUCKET:
    print("Error: CRICSHEET_S3_BUCKET env var is not set.", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "backend" / "cricsheet_data"

if not DATA_DIR.exists():
    print(f"Error: data directory not found: {DATA_DIR}", file=sys.stderr)
    sys.exit(1)

files = sorted(f for f in DATA_DIR.rglob("*") if f.is_file())
if not files:
    print(f"No files found under {DATA_DIR} — nothing to upload.")
    sys.exit(0)

s3 = boto3.client("s3")
uploaded = 0

for path in files:
    key = "cricsheet_data/" + path.relative_to(DATA_DIR).as_posix()
    print(f"  {path.name:<40} → s3://{BUCKET}/{key}")
    try:
        s3.upload_file(str(path), BUCKET, key)
        uploaded += 1
    except (BotoCoreError, ClientError) as exc:
        print(f"  ERROR uploading {path.name}: {exc}", file=sys.stderr)

print(f"\n✓ Uploaded {uploaded}/{len(files)} file(s) to s3://{BUCKET}/cricsheet_data/")
if uploaded < len(files):
    sys.exit(1)
