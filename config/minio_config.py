# config/minio_config.py

from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class MinIOConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    img_dir: str
    secure: bool
    public_read: bool
    public_endpoint: str

minio_config = MinIOConfig(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    bucket_name=os.getenv("MINIO_BUCKET_NAME"),
    img_dir=os.getenv("MINIO_IMG_DIR"),
    secure=os.getenv("MINIO_SECURE", "False").lower() in {"1", "true", "yes", "on"},
    public_read=os.getenv("MINIO_PUBLIC_READ", "False").lower() in {"1", "true", "yes", "on"},
    public_endpoint=os.getenv("MINIO_PUBLIC_ENDPOINT") or os.getenv("MINIO_ENDPOINT"),
)
