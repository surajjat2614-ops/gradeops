import os
import io
import uuid
from pathlib import Path
from typing import Optional
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

# Load credentials from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

# Local fallback directory
LOCAL_STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "cloud_fallback"
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def _get_s3_client():
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_S3_BUCKET:
        try:
            return boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
            )
        except Exception as e:
            print(f"Warning: Failed to initialize S3 client: {e}")
            return None
    return None

def upload_file(file_obj, filename: str, content_type: str = "application/octet-stream") -> str:
    """Uploads a file object (like from FastAPI UploadFile) to S3 or local fallback."""
    s3_client = _get_s3_client()
    safe_name = f"{uuid.uuid4().hex}_{filename}"

    if s3_client:
        try:
            file_obj.seek(0)
            s3_client.upload_fileobj(
                file_obj,
                AWS_S3_BUCKET,
                safe_name,
                ExtraArgs={"ContentType": content_type}
            )
            # Generate a presigned URL or public URL. We'll return the object key for now.
            return f"s3://{AWS_S3_BUCKET}/{safe_name}"
        except (NoCredentialsError, PartialCredentialsError, Exception) as e:
            print(f"S3 Upload failed ({e}), falling back to local storage.")

    # Local fallback
    file_obj.seek(0)
    dest = LOCAL_STORAGE_DIR / safe_name
    with dest.open("wb") as f:
        f.write(file_obj.read())
    return f"local://{dest}"

def upload_bytes(image_bytes: bytes, extension: str = ".png", content_type: str = "image/png") -> str:
    """Uploads in-memory bytes (like OpenCV encoded images) to S3 or local fallback."""
    s3_client = _get_s3_client()
    safe_name = f"{uuid.uuid4().hex}{extension}"

    if s3_client:
        try:
            s3_client.put_object(
                Bucket=AWS_S3_BUCKET,
                Key=safe_name,
                Body=image_bytes,
                ContentType=content_type
            )
            return f"s3://{AWS_S3_BUCKET}/{safe_name}"
        except Exception as e:
            print(f"S3 byte upload failed ({e}), falling back to local storage.")

    # Local fallback
    dest = LOCAL_STORAGE_DIR / safe_name
    with dest.open("wb") as f:
        f.write(image_bytes)
    return f"local://{dest}"

def get_file_url(path: str, expiration=3600) -> str:
    """Returns a presigned URL for S3 paths, or an API route for local fallback paths."""
    if not path:
        return ""

    if path.startswith("s3://"):
        s3_client = _get_s3_client()
        if not s3_client:
            return "" # Cannot generate URL without client

        # Parse s3://bucket/key
        parts = path.replace("s3://", "").split("/", 1)
        if len(parts) != 2:
            return path
        bucket, key = parts

        try:
            return s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
        except Exception as e:
            print(f"Failed to generate presigned URL: {e}")
            return path

    elif path.startswith("local://"):
        filepath = path.replace("local://", "")
        filename = Path(filepath).name
        # Route to a local FastAPI endpoint that will serve the file
        return f"/api/storage/{filename}"

    # Legacy local paths (before migration)
    return path

def download_to_local_temp(path: str) -> str:
    """Downloads an S3 object to a local temporary file for OpenCV processing, or returns the local path."""
    if path.startswith("local://"):
        return path.replace("local://", "")

    if path.startswith("s3://"):
        s3_client = _get_s3_client()
        if not s3_client:
            raise ValueError("S3 client not configured but S3 path provided")

        parts = path.replace("s3://", "").split("/", 1)
        bucket, key = parts

        temp_dest = LOCAL_STORAGE_DIR / f"temp_{uuid.uuid4().hex}_{Path(key).name}"
        s3_client.download_file(bucket, key, str(temp_dest))
        return str(temp_dest)

    return path # Legacy local paths
