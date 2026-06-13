"""
MinIO storage service for roster file management
MinIO文件儲存服務
"""

import hashlib
import io
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.config import settings
from app.core.exceptions import FileStorageError
from app.core.metrics import file_uploads_total
from app.core.path_security import secure_filename

logger = logging.getLogger(__name__)


class MinIOService:
    """MinIO storage service for managing roster files"""

    def __init__(self):
        self._client = None
        self.roster_bucket = settings.roster_minio_bucket
        self.default_bucket = settings.minio_bucket
        self._initialized = False

        # Force initialization for non-testing environments to catch errors early
        if not settings.testing:
            # Access client property to trigger initialization
            _ = self.client

    @property
    def client(self) -> Minio:
        """Lazy initialization of MinIO client"""
        if self._client is None:
            # Skip MinIO initialization in testing environments
            if settings.testing:
                from unittest.mock import MagicMock

                self._client = MagicMock()
                self._client.bucket_exists.return_value = True
                self._client.make_bucket.return_value = None
                self._client.put_object.return_value = None
                self._client.get_object.return_value = MagicMock()
                self._client.remove_object.return_value = None
                self._client.list_objects.return_value = []
                logger.info("MinIO service initialized with mock client for testing")
            else:
                self._client = Minio(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure,
                )
                logger.info("MinIO service initialized with real client")

            # Initialize buckets on first access (real or mock)
            if not self._initialized:
                self._ensure_buckets_exist()
                self._initialized = True
        return self._client

    def _ensure_buckets_exist(self):
        """確保必要的MinIO bucket存在"""
        try:
            # Skip bucket creation in testing environments
            if settings.testing:
                logger.info("Skipping bucket creation in testing environment")
                return

            buckets_to_create = [self.roster_bucket, self.default_bucket]

            for bucket_name in buckets_to_create:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Created MinIO bucket: {bucket_name}")

                    # NOTE: no explicit deny-all bucket policy here anymore.
                    # Buckets are private by default (anonymous GET → 403 with
                    # no policy attached — verified against RustFS 1.0.0-beta.8
                    # by app/scripts/storage_compat_check.py). The old
                    # deny-all s3:GetObject policy was written for MinIO,
                    # where root credentials bypass bucket policies; RustFS
                    # enforces an explicit Deny against the OWNER as well
                    # (AWS-faithful semantics), which 403'd the backend's own
                    # roster downloads.

        except Exception as e:
            logger.exception("Failed to ensure buckets exist")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="MinIO bucket initialization failed") from e

    def upload_roster_file(
        self,
        file_content: bytes,
        filename: str,
        roster_id: int,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        上傳造冊檔案到MinIO

        Args:
            file_content: 檔案內容(bytes)
            filename: 檔案名稱
            roster_id: 造冊ID
            content_type: MIME類型
            metadata: 額外的metadata

        Returns:
            Dict[str, str]: 包含object_name, file_path, file_hash, file_size等資訊
        """
        try:
            # 產生檔案路徑: rosters/{year}/{month}/{roster_id}/{filename}
            now = datetime.now()
            object_name = f"rosters/{now.year}/{now.month:02d}/{roster_id}/{filename}"

            # 計算檔案hash
            file_hash = hashlib.sha256(file_content).hexdigest()
            file_size = len(file_content)

            # 準備metadata
            upload_metadata = {
                "Content-Type": content_type,
                "roster-id": str(roster_id),
                "upload-timestamp": now.isoformat(),
                "file-hash": file_hash,
                "original-filename": filename,
            }

            if metadata:
                upload_metadata.update(metadata)

            # 上傳檔案
            file_stream = io.BytesIO(file_content)

            self.client.put_object(
                bucket_name=self.roster_bucket,
                object_name=object_name,
                data=file_stream,
                length=file_size,
                content_type=content_type,
                metadata=upload_metadata,
            )

            logger.info(f"Uploaded roster file: {object_name} (size: {file_size}, hash: {file_hash[:8]}...)")

            return {
                "object_name": object_name,
                "file_path": f"minio://{self.roster_bucket}/{object_name}",
                "file_hash": file_hash,
                "file_size": file_size,
                "bucket": self.roster_bucket,
                "content_type": content_type,
            }

        except Exception as e:
            logger.exception(f"Failed to upload roster file {filename}")
            raise FileStorageError(f"檔案上傳失敗: {str(e)}") from e

    async def upload_file(self, file, application_id: int, file_type: str) -> Tuple[str, int]:
        """
        通用檔案上傳方法 (for application files)

        Args:
            file: UploadFile對象
            application_id: 申請ID
            file_type: 檔案類型 (doc, transcript, etc.)

        Returns:
            Tuple[str, int]: (object_name, file_size)
        """
        try:
            # 讀取檔案內容
            content = await file.read()
            file_size = len(content)

            # 檢查檔案大小
            if file_size > settings.max_file_size:
                raise HTTPException(status_code=413, detail="File too large")

            # 檢查檔案類型
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")

            # Sanitize the filename first (strips path components / unsafe chars)
            # so a payload like "evil.pdf.exe" or "../../etc/passwd" cannot survive.
            safe_filename = secure_filename(file.filename)

            # Validate the extension on the *sanitized* name, taking the final
            # extension only (defends against double-extension bypass).
            file_extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
            if file_extension not in settings.allowed_file_types_list:
                raise HTTPException(status_code=415, detail="Invalid file type")

            # 生成object名稱
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 標準化 file_type 為複數形式
            if file_type == "doc":
                folder_name = "documents"
            else:
                folder_name = f"{file_type}s"
            object_name = f"applications/{application_id}/{folder_name}/{timestamp}_{safe_filename}"

            # 上傳到MinIO
            self.client.put_object(
                bucket_name=self.default_bucket,
                object_name=object_name,
                data=io.BytesIO(content),
                length=file_size,
                content_type=file.content_type,
            )

            # Log the sanitized filename (object_name is already safe) to avoid
            # log injection from control characters in the client-supplied name.
            logger.info(f"Uploaded file {safe_filename} as {object_name}")

            # Business metric: count successful application-file uploads.
            # file_type already discriminates document categories (doc,
            # transcript, etc.); status "success" pairs with the failure
            # increment in the except block (issue #159).
            file_uploads_total.labels(file_type=str(file_type), status="success").inc()

            return object_name, file_size

        except HTTPException:
            # Validation errors (size/type/filename) carry their own status code
            # and must not be masked as a generic 500.
            file_uploads_total.labels(file_type=str(file_type), status="failed").inc()
            raise
        except Exception as e:
            # SECURITY: sanitize the client-supplied filename before logging to
            # avoid log injection / control-character confusion.
            logger.exception(f"Failed to upload file {secure_filename(file.filename or '')}")

            # Business metric: count failures so the dashboard can show
            # the success-rate ratio without needing log-scraping.
            file_uploads_total.labels(file_type=str(file_type), status="failed").inc()

            raise HTTPException(status_code=500, detail="File upload failed") from e

    def get_file_stream(self, object_name: str):
        """
        取得檔案串流

        Args:
            object_name: 檔案object名稱

        Returns:
            MinIO response object
        """
        try:
            return self.client.get_object(self.default_bucket, object_name)
        except Exception as e:
            logger.exception(f"Failed to get file stream for {object_name}")
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="File not found") from e

    def delete_file(self, object_name: str) -> bool:
        """
        刪除檔案

        Args:
            object_name: 檔案object名稱

        Returns:
            bool: 是否成功刪除
        """
        try:
            self.client.remove_object(self.default_bucket, object_name)
            logger.info(f"Deleted file {object_name}")
            return True
        except Exception:
            logger.exception(f"Failed to delete file {object_name}")
            return False

    def clone_file_to_application(self, source_object_name: str, application_id: str) -> str:
        """
        複製檔案到指定的申請

        Args:
            source_object_name: 來源檔案object名稱
            application_id: 目標申請ID

        Returns:
            str: 新的object名稱
        """
        try:
            # 生成新的object名稱
            file_extension = source_object_name.split(".")[-1] if "." in source_object_name else ""
            new_object_name = f"applications/{application_id}/documents/{uuid.uuid4().hex}.{file_extension}"

            # 複製檔案到申請路徑。
            # 注意：minio 7.x 的 copy_object 參數為 source（必須是 CopySource 物件），
            # 不是字串 copy_source。若複製失敗必須直接 raise，
            # 嚴禁寫入 placeholder 假檔（違反 CLAUDE.md 原則 #1，會產生污染資料）。
            self.client.copy_object(
                bucket_name=self.default_bucket,
                object_name=new_object_name,
                source=CopySource(self.default_bucket, source_object_name),
            )
            logger.info(f"Cloned file {source_object_name} to {new_object_name}")
            return new_object_name

        except Exception as e:
            logger.exception(f"Failed to clone file {source_object_name}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="File clone failed") from e

    def extract_object_name_from_url(self, url: str) -> Optional[str]:
        """
        從URL中提取object名稱

        Args:
            url: 檔案URL

        Returns:
            Optional[str]: object名稱或None
        """
        try:
            # 移除query parameters
            if "?" in url:
                url = url.split("?")[0]

            # 檢查是否是有效的檔案路徑
            if url.startswith("/api/v1/user-profiles/files/"):
                # 提取檔案路徑部分
                return url.replace("/api/v1/user-profiles/files/", "user-profiles/")

            return None
        except Exception:
            return None

    def download_roster_file(self, object_name: str) -> Tuple[bytes, Dict[str, str]]:
        """
        下載造冊檔案

        Args:
            object_name: MinIO object名稱

        Returns:
            Tuple[bytes, Dict[str, str]]: 檔案內容和metadata
        """
        try:
            # 取得檔案資訊
            stat = self.client.stat_object(self.roster_bucket, object_name)

            # 下載檔案
            response = self.client.get_object(self.roster_bucket, object_name)
            file_content = response.read()
            response.close()
            response.release_conn()

            # 驗證檔案hash (如果metadata中有的話)。
            # Custom metadata comes back PREFIXED (x-amz-meta-*) from the SDK's
            # stat headers — the bare "file-hash" lookup was always None, so
            # this integrity check had silently never run (on MinIO either).
            stored_hash = stat.metadata.get("x-amz-meta-file-hash")
            if stored_hash:
                actual_hash = hashlib.sha256(file_content).hexdigest()
                if stored_hash != actual_hash:
                    logger.warning(f"File hash mismatch for {object_name}: stored={stored_hash}, actual={actual_hash}")

            logger.info(f"Downloaded roster file: {object_name} (size: {len(file_content)})")

            return file_content, stat.metadata

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileStorageError(f"檔案不存在: {object_name}") from e
            else:
                logger.exception(f"Failed to download roster file {object_name}")
                raise FileStorageError(f"檔案下載失敗: {str(e)}") from e
        except Exception as e:
            logger.exception(f"Failed to download roster file {object_name}")
            raise FileStorageError(f"檔案下載失敗: {str(e)}") from e

    def delete_roster_file(self, object_name: str) -> bool:
        """
        刪除造冊檔案

        Args:
            object_name: MinIO object名稱

        Returns:
            bool: 是否成功刪除
        """
        try:
            self.client.remove_object(self.roster_bucket, object_name)
            logger.info(f"Deleted roster file: {object_name}")
            return True

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"File already deleted or does not exist: {object_name}")
                return True  # 檔案不存在也算成功
            else:
                logger.exception(f"Failed to delete roster file {object_name}")
                return False
        except Exception:
            logger.exception(f"Failed to delete roster file {object_name}")
            return False

    def get_presigned_url(self, object_name: str, expires: timedelta = timedelta(hours=1), method: str = "GET") -> str:
        """
        產生預簽名URL用於直接下載

        Args:
            object_name: MinIO object名稱
            expires: URL有效期限
            method: HTTP方法 (GET/PUT)

        Returns:
            str: 預簽名URL
        """
        try:
            # SDK method is get_presigned_url — `client.presigned_url` does
            # not exist (this wrapper had zero callers, so the AttributeError
            # never fired; surfaced by storage_compat_check).
            url = self.client.get_presigned_url(
                method=method,
                bucket_name=self.roster_bucket,
                object_name=object_name,
                expires=expires,
            )

            logger.info(f"Generated presigned URL for {object_name} (expires in {expires})")
            return url

        except Exception as e:
            logger.exception(f"Failed to generate presigned URL for {object_name}")
            raise FileStorageError(f"下載連結產生失敗: {str(e)}") from e

    def health_check(self) -> Dict[str, bool]:
        """
        檢查MinIO服務健康狀態

        Returns:
            Dict[str, bool]: 健康狀態資訊
        """
        try:
            # 測試連線和bucket存在性
            bucket_exists = self.client.bucket_exists(self.roster_bucket)

            # 測試上傳/下載功能
            test_object = "health-check/test.txt"
            test_content = b"health check test"

            # 上傳測試檔案
            self.client.put_object(
                self.roster_bucket,
                test_object,
                io.BytesIO(test_content),
                len(test_content),
            )

            # 下載測試檔案
            response = self.client.get_object(self.roster_bucket, test_object)
            downloaded_content = response.read()
            response.close()
            response.release_conn()

            # 刪除測試檔案
            self.client.remove_object(self.roster_bucket, test_object)

            upload_download_ok = downloaded_content == test_content

            return {
                "connection": True,
                "bucket_exists": bucket_exists,
                "upload_download": upload_download_ok,
                "overall_healthy": bucket_exists and upload_download_ok,
            }

        except Exception as e:
            logger.exception("MinIO health check failed")
            return {
                "connection": False,
                "bucket_exists": False,
                "upload_download": False,
                "overall_healthy": False,
                "error": str(e),
            }


# 全域MinIO服務實例 - 使用懶加載
_minio_service_instance = None


def get_minio_service() -> MinIOService:
    """Get the global MinIO service instance with lazy initialization"""
    global _minio_service_instance
    if _minio_service_instance is None:
        _minio_service_instance = MinIOService()
    return _minio_service_instance


# For backward compatibility, create a lazy property that can be imported as minio_service
class MinIOServiceProxy:
    """Proxy to provide lazy access to MinIO service"""

    def __getattr__(self, name):
        return getattr(get_minio_service(), name)

    def __call__(self, *args, **kwargs):
        return get_minio_service()(*args, **kwargs)


minio_service = MinIOServiceProxy()
