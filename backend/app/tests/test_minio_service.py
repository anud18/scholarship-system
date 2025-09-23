"""
Unit tests for MinioService

Tests file storage operations including:
- File upload and download
- File deletion and management
- Presigned URL generation
- Error handling for storage operations
- Security and permission validation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.services.minio_service import MinIOService
from app.core.exceptions import ValidationError


@pytest.mark.unit
class TestMinIOService:
    """Test suite for MinioService"""

    @pytest.fixture
    def mock_minio_client(self):
        """Mock MinIO client"""
        return Mock(spec=Minio)

    @pytest.fixture
    def minio_service_instance(self, mock_minio_client):
        """Create MinIOService instance with mocked client"""
        service = MinIOService()
        service.client = mock_minio_client
        return service

    @pytest.fixture
    def sample_file_data(self):
        """Sample file data for testing"""
        return {
            "content": BytesIO(b"Test file content for upload testing"),
            "filename": "test_document.pdf",
            "content_type": "application/pdf",
            "size": 1024
        }

    @pytest.mark.asyncio
    async def test_upload_file_success(self, minio_service_instance, mock_minio_client, sample_file_data):
        """Test successful file upload"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/test_document.pdf"
        expected_url = f"https://minio.example.com/{bucket_name}/{object_name}"

        mock_minio_client.bucket_exists.return_value = True
        mock_minio_client.put_object.return_value = Mock(etag="test-etag")

        with patch.object(minio_service_instance, 'get_file_url', return_value=expected_url):
            # Act
            result = await minio_service_instance.upload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=sample_file_data["content"],
                content_type=sample_file_data["content_type"]
            )

            # Assert
            assert result == expected_url
            mock_minio_client.put_object.assert_called_once()
            args, kwargs = mock_minio_client.put_object.call_args
            assert args[0] == bucket_name
            assert args[1] == object_name
            assert kwargs["content_type"] == sample_file_data["content_type"]

    @pytest.mark.asyncio
    async def test_upload_file_bucket_not_exists_creates_bucket(self, minio_service_instance, mock_minio_client, sample_file_data):
        """Test file upload creates bucket if it doesn't exist"""
        # Arrange
        bucket_name = "new-bucket"
        object_name = "test_file.pdf"

        mock_minio_client.bucket_exists.return_value = False
        mock_minio_client.make_bucket.return_value = None
        mock_minio_client.put_object.return_value = Mock(etag="test-etag")

        with patch.object(minio_service_instance, 'get_file_url', return_value="test-url"):
            # Act
            await minio_service_instance.upload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=sample_file_data["content"],
                content_type=sample_file_data["content_type"]
            )

            # Assert
            mock_minio_client.make_bucket.assert_called_once_with(bucket_name)
            mock_minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_file_s3_error(self, minio_service_instance, mock_minio_client, sample_file_data):
        """Test file upload with S3 error"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "test_file.pdf"

        mock_minio_client.bucket_exists.return_value = True
        mock_minio_client.put_object.side_effect = S3Error(
            "PutObject",
            "Access denied",
            resource="test-bucket/test_file.pdf",
            request_id="test-request-id",
            host_id="test-host-id",
            response=Mock()
        )

        # Act & Assert
        with pytest.raises(FileStorageError, match="Failed to upload file"):
            await minio_service_instance.upload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=sample_file_data["content"],
                content_type=sample_file_data["content_type"]
            )

    @pytest.mark.asyncio
    async def test_download_file_success(self, minio_service_instance, mock_minio_client):
        """Test successful file download"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/test_file.pdf"
        expected_content = b"Test file content"

        mock_response = Mock()
        mock_response.read.return_value = expected_content
        mock_minio_client.get_object.return_value = mock_response

        # Act
        result = await minio_service_instance.download_file(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result == expected_content
        mock_minio_client.get_object.assert_called_once_with(bucket_name, object_name)
        mock_response.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, minio_service_instance, mock_minio_client):
        """Test download of non-existent file"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "nonexistent/file.pdf"

        mock_minio_client.get_object.side_effect = S3Error("GetObject", "Object not found", resource="", request_id="", host_id="", response=Mock())

        # Act & Assert
        with pytest.raises(FileStorageError, match="File not found"):
            await minio_service_instance.download_file(
                bucket_name=bucket_name,
                object_name=object_name
            )

    @pytest.mark.asyncio
    async def test_delete_file_success(self, minio_service_instance, mock_minio_client):
        """Test successful file deletion"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/old_file.pdf"

        mock_minio_client.remove_object.return_value = None

        # Act
        result = await minio_service_instance.delete_file(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result is True
        mock_minio_client.remove_object.assert_called_once_with(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_delete_file_not_found_returns_true(self, minio_service_instance, mock_minio_client):
        """Test deletion of non-existent file returns True (idempotent)"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "nonexistent/file.pdf"

        mock_minio_client.remove_object.side_effect = S3Error("RemoveObject", "Object not found", resource="", request_id="", host_id="", response=Mock())

        # Act
        result = await minio_service_instance.delete_file(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result is True  # Idempotent operation

    @pytest.mark.asyncio
    async def test_get_presigned_url_success(self, minio_service_instance, mock_minio_client):
        """Test successful presigned URL generation"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/secret_file.pdf"
        expiry_seconds = 3600
        expected_url = "https://minio.example.com/test-bucket/documents/secret_file.pdf?signature=xyz"

        mock_minio_client.presigned_get_object.return_value = expected_url

        # Act
        result = await minio_service_instance.get_presigned_url(
            bucket_name=bucket_name,
            object_name=object_name,
            expiry_seconds=expiry_seconds
        )

        # Assert
        assert result == expected_url
        mock_minio_client.presigned_get_object.assert_called_once()
        args, kwargs = mock_minio_client.presigned_get_object.call_args
        assert args[0] == bucket_name
        assert args[1] == object_name
        assert kwargs["expires"] == timedelta(seconds=expiry_seconds)

    @pytest.mark.asyncio
    async def test_get_presigned_url_invalid_expiry(self, minio_service_instance, mock_minio_client):
        """Test presigned URL generation with invalid expiry time"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/file.pdf"
        invalid_expiry = 0

        # Act & Assert
        with pytest.raises(ValidationError, match="Expiry time must be positive"):
            await minio_service_instance.get_presigned_url(
                bucket_name=bucket_name,
                object_name=object_name,
                expiry_seconds=invalid_expiry
            )

    @pytest.mark.asyncio
    async def test_list_files_success(self, minio_service_instance, mock_minio_client):
        """Test successful file listing"""
        # Arrange
        bucket_name = "test-bucket"
        prefix = "documents/"

        mock_objects = [
            Mock(object_name="documents/file1.pdf", size=1024, last_modified=datetime.now()),
            Mock(object_name="documents/file2.pdf", size=2048, last_modified=datetime.now()),
            Mock(object_name="documents/subfolder/file3.pdf", size=512, last_modified=datetime.now())
        ]

        mock_minio_client.list_objects.return_value = mock_objects

        # Act
        result = await minio_service_instance.list_files(
            bucket_name=bucket_name,
            prefix=prefix
        )

        # Assert
        assert len(result) == 3
        mock_minio_client.list_objects.assert_called_once()
        args, kwargs = mock_minio_client.list_objects.call_args
        assert args[0] == bucket_name
        assert kwargs["prefix"] == prefix

    @pytest.mark.asyncio
    async def test_list_files_empty_bucket(self, minio_service_instance, mock_minio_client):
        """Test file listing from empty bucket"""
        # Arrange
        bucket_name = "empty-bucket"
        mock_minio_client.list_objects.return_value = []

        # Act
        result = await minio_service_instance.list_files(bucket_name=bucket_name)

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_file_exists_true(self, minio_service_instance, mock_minio_client):
        """Test file existence check returns True"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/existing_file.pdf"

        mock_minio_client.stat_object.return_value = Mock(size=1024)

        # Act
        result = await minio_service_instance.file_exists(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result is True
        mock_minio_client.stat_object.assert_called_once_with(bucket_name, object_name)

    @pytest.mark.asyncio
    async def test_file_exists_false(self, minio_service_instance, mock_minio_client):
        """Test file existence check returns False"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/nonexistent_file.pdf"

        mock_minio_client.stat_object.side_effect = S3Error("StatObject", "Object not found", resource="", request_id="", host_id="", response=Mock())

        # Act
        result = await minio_service_instance.file_exists(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_get_file_info_success(self, minio_service_instance, mock_minio_client):
        """Test successful file info retrieval"""
        # Arrange
        bucket_name = "test-bucket"
        object_name = "documents/info_file.pdf"

        mock_stat = Mock(
            size=1024,
            last_modified=datetime.now(),
            etag="test-etag",
            content_type="application/pdf"
        )
        mock_minio_client.stat_object.return_value = mock_stat

        # Act
        result = await minio_service_instance.get_file_info(
            bucket_name=bucket_name,
            object_name=object_name
        )

        # Assert
        assert result["size"] == 1024
        assert result["content_type"] == "application/pdf"
        assert result["etag"] == "test-etag"
        assert "last_modified" in result

    @pytest.mark.asyncio
    async def test_validate_file_type_allowed(self, minio_service_instance):
        """Test file type validation for allowed types"""
        # Arrange
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]

        # Act & Assert
        assert minio_service_instance._validate_file_type("test.pdf", "application/pdf", allowed_types) is True
        assert minio_service_instance._validate_file_type("image.jpg", "image/jpeg", allowed_types) is True

    @pytest.mark.asyncio
    async def test_validate_file_type_disallowed(self, minio_service_instance):
        """Test file type validation for disallowed types"""
        # Arrange
        allowed_types = ["application/pdf", "image/jpeg"]

        # Act & Assert
        assert minio_service_instance._validate_file_type("script.exe", "application/exe", allowed_types) is False
        assert minio_service_instance._validate_file_type("doc.txt", "text/plain", allowed_types) is False

    @pytest.mark.asyncio
    async def test_validate_file_size_within_limit(self, minio_service_instance):
        """Test file size validation within limits"""
        # Arrange
        max_size = 10 * 1024 * 1024  # 10MB

        # Act & Assert
        assert minio_service_instance._validate_file_size(1024, max_size) is True
        assert minio_service_instance._validate_file_size(5 * 1024 * 1024, max_size) is True

    @pytest.mark.asyncio
    async def test_validate_file_size_exceeds_limit(self, minio_service_instance):
        """Test file size validation exceeding limits"""
        # Arrange
        max_size = 10 * 1024 * 1024  # 10MB

        # Act & Assert
        assert minio_service_instance._validate_file_size(15 * 1024 * 1024, max_size) is False

    @pytest.mark.asyncio
    async def test_sanitize_object_name(self, minio_service_instance):
        """Test object name sanitization"""
        # Act & Assert
        assert minio_service_instance._sanitize_object_name("normal_file.pdf") == "normal_file.pdf"
        assert minio_service_instance._sanitize_object_name("file with spaces.pdf") == "file_with_spaces.pdf"
        assert minio_service_instance._sanitize_object_name("файл.pdf") == "файл.pdf"  # Should handle unicode
        assert "/" not in minio_service_instance._sanitize_object_name("../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_bulk_upload_success(self, minio_service_instance, mock_minio_client):
        """Test successful bulk file upload"""
        # Arrange
        files = [
            {"object_name": "file1.pdf", "content": BytesIO(b"content1"), "content_type": "application/pdf"},
            {"object_name": "file2.pdf", "content": BytesIO(b"content2"), "content_type": "application/pdf"}
        ]
        bucket_name = "test-bucket"

        mock_minio_client.bucket_exists.return_value = True
        mock_minio_client.put_object.return_value = Mock(etag="test-etag")

        with patch.object(minio_service_instance, 'get_file_url', return_value="test-url"):
            # Act
            results = await minio_service_instance.bulk_upload(
                bucket_name=bucket_name,
                files=files
            )

            # Assert
            assert len(results) == 2
            assert all(result["success"] for result in results)
            assert mock_minio_client.put_object.call_count == 2

    @pytest.mark.asyncio
    async def test_bulk_upload_partial_failure(self, minio_service_instance, mock_minio_client):
        """Test bulk upload with partial failures"""
        # Arrange
        files = [
            {"object_name": "file1.pdf", "content": BytesIO(b"content1"), "content_type": "application/pdf"},
            {"object_name": "file2.pdf", "content": BytesIO(b"content2"), "content_type": "application/pdf"}
        ]
        bucket_name = "test-bucket"

        mock_minio_client.bucket_exists.return_value = True
        mock_minio_client.put_object.side_effect = [
            Mock(etag="test-etag"),  # First upload succeeds
            S3Error("PutObject", "Error", resource="", request_id="", host_id="", response=Mock())  # Second fails
        ]

        with patch.object(minio_service_instance, 'get_file_url', return_value="test-url"):
            # Act
            results = await minio_service_instance.bulk_upload(
                bucket_name=bucket_name,
                files=files
            )

            # Assert
            assert len(results) == 2
            assert results[0]["success"] is True
            assert results[1]["success"] is False
            assert "error" in results[1]

    @pytest.mark.asyncio
    async def test_cleanup_old_files(self, minio_service_instance, mock_minio_client):
        """Test cleanup of old files"""
        # Arrange
        bucket_name = "test-bucket"
        prefix = "temp/"
        cutoff_date = datetime.now() - timedelta(days=7)

        old_files = [
            Mock(object_name="temp/old_file1.pdf", last_modified=cutoff_date - timedelta(days=1)),
            Mock(object_name="temp/old_file2.pdf", last_modified=cutoff_date - timedelta(days=2))
        ]
        recent_files = [
            Mock(object_name="temp/recent_file.pdf", last_modified=cutoff_date + timedelta(days=1))
        ]

        mock_minio_client.list_objects.return_value = old_files + recent_files
        mock_minio_client.remove_object.return_value = None

        # Act
        cleaned_count = await minio_service_instance.cleanup_old_files(
            bucket_name=bucket_name,
            prefix=prefix,
            cutoff_date=cutoff_date
        )

        # Assert
        assert cleaned_count == 2
        assert mock_minio_client.remove_object.call_count == 2

    # TODO: Add tests for concurrent file operations
    # TODO: Add tests for file encryption/decryption
    # TODO: Add tests for file versioning support
    # TODO: Add tests for bandwidth limiting
    # TODO: Add performance tests for large file operations