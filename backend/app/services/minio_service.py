"""
MinIO storage service for roster file management
MinIO文件儲存服務
"""

import hashlib
import io
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.exceptions import FileStorageError

logger = logging.getLogger(__name__)


class MinIOService:
    """MinIO storage service for managing roster files"""

    def __init__(self):
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.roster_bucket = settings.roster_minio_bucket
        self.default_bucket = settings.minio_bucket

        # Initialize buckets
        self._ensure_buckets_exist()

    def _ensure_buckets_exist(self):
        """確保必要的MinIO bucket存在"""
        try:
            buckets_to_create = [self.roster_bucket, self.default_bucket]

            for bucket_name in buckets_to_create:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Created MinIO bucket: {bucket_name}")

                    # Set bucket policy for roster files (private by default)
                    if bucket_name == self.roster_bucket:
                        self._set_bucket_policy(bucket_name, private=True)

        except Exception as e:
            logger.error(f"Failed to ensure buckets exist: {e}")
            raise FileStorageError(f"MinIO bucket initialization failed: {str(e)}")

    def _set_bucket_policy(self, bucket_name: str, private: bool = True):
        """設定bucket政策"""
        try:
            if private:
                # Private bucket policy - no public access
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:GetObject",
                            "Resource": f"arn:aws:s3:::{bucket_name}/*",
                        }
                    ],
                }
                import json

                self.client.set_bucket_policy(bucket_name, json.dumps(policy))

        except Exception as e:
            logger.warning(f"Failed to set bucket policy for {bucket_name}: {e}")

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
            logger.error(f"Failed to upload roster file {filename}: {e}")
            raise FileStorageError(f"檔案上傳失敗: {str(e)}")

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

            # 驗證檔案hash (如果metadata中有的話)
            stored_hash = stat.metadata.get("file-hash")
            if stored_hash:
                actual_hash = hashlib.sha256(file_content).hexdigest()
                if stored_hash != actual_hash:
                    logger.warning(f"File hash mismatch for {object_name}: stored={stored_hash}, actual={actual_hash}")

            logger.info(f"Downloaded roster file: {object_name} (size: {len(file_content)})")

            return file_content, stat.metadata

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileStorageError(f"檔案不存在: {object_name}")
            else:
                logger.error(f"Failed to download roster file {object_name}: {e}")
                raise FileStorageError(f"檔案下載失敗: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to download roster file {object_name}: {e}")
            raise FileStorageError(f"檔案下載失敗: {str(e)}")

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
                logger.error(f"Failed to delete roster file {object_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete roster file {object_name}: {e}")
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
            url = self.client.presigned_url(
                method=method,
                bucket_name=self.roster_bucket,
                object_name=object_name,
                expires=expires,
            )

            logger.info(f"Generated presigned URL for {object_name} (expires in {expires})")
            return url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
            raise FileStorageError(f"下載連結產生失敗: {str(e)}")

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
            logger.error(f"MinIO health check failed: {e}")
            return {
                "connection": False,
                "bucket_exists": False,
                "upload_download": False,
                "overall_healthy": False,
                "error": str(e),
            }


# 全域MinIO服務實例
minio_service = MinIOService()
