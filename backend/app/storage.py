from datetime import timedelta

from fastapi import UploadFile
from minio import Minio
from urllib3 import Retry
from urllib3.poolmanager import PoolManager

from app.config import get_settings


class ObjectStorage:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.minio_bucket
        self.public_endpoint = s.minio_public_endpoint.rstrip("/")
        # MinIO 不可达时快速失败（不重试长等），避免拖垮 API 启动
        http_client = PoolManager(
            timeout=2.0,
            retries=Retry(total=1, backoff_factor=0.1),
        )
        self._client = Minio(
            s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            secure=s.minio_secure,
            http_client=http_client,
        )

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def put(self, key: str, file: UploadFile, length: int, content_type: str) -> None:
        self._client.put_object(
            self.bucket,
            key,
            file.file,
            length=length,
            content_type=content_type,
        )

    def presigned_url(self, key: str) -> str:
        # 优先给出稳定的公共路径；MinIO bucket 非匿名时回退为预签名
        try:
            return self._client.presigned_get_object(
                self.bucket, key, expires=timedelta(minutes=30)
            )
        except Exception:
            return f"{self.public_endpoint}/{self.bucket}/{key}"
