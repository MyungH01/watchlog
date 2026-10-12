"""설정은 전부 환경 변수에서 읽는다. 목록과 설명은 .env.example 참고."""
import os


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
S3_BUCKET = os.environ.get("S3_BUCKET", "watchlog-local")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
# 브라우저가 접근할 S3 주소가 서버가 쓰는 주소와 다를 때만 지정 (로컬 LocalStack)
S3_PUBLIC_ENDPOINT_URL = os.environ.get("S3_PUBLIC_ENDPOINT_URL") or None
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
COOKIE_SECURE = _bool("COOKIE_SECURE", "true")
STATIC_DIR = os.environ.get("STATIC_DIR", "")
PORT = int(os.environ.get("PORT", "8000"))
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_PHOTO_BYTES = 8 * 1024 * 1024
UPLOAD_URL_SECONDS = 300
