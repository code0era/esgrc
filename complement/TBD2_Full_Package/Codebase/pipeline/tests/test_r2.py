"""
pipeline/test/test_r2.py
Unit tests for R2 file I/O helpers.
All tests mock boto3 - never touch real R2.
"""
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest
from botocore.exceptions import ClientError

os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")

from pipeline.tasks.r2 import (
    R2Error,
    delete_file,
    download_file,
    file_exists,
    generate_presigned_url,
    list_files,
    module_output_key,
    reference_key,
    run_key,
    upload_file,
)


# ── Key helpers ───────────────────────────────────────────────────────────────

class TestKeyHelpers:
    def test_run_key_format(self):
        key = run_key("42", "run-abc", 3, "report.txt")
        assert key == "org/42/runs/run-abc/step_3/report.txt"

    def test_module_output_key_format(self):
        key = module_output_key("42", "data_for_risk_assessment_esgrc.csv")
        assert key == "org/42/module_outputs/data_for_risk_assessment_esgrc.csv"

    def test_reference_key_format(self):
        key = reference_key("42", "module_mapping.csv")
        assert key == "org/42/reference/module_mapping.csv"


# ── upload_file ───────────────────────────────────────────────────────────────

class TestUploadFile:
    def test_upload_success_returns_r2_key(self, tmp_path):
        local = tmp_path / "test.txt"
        local.write_text("hello")

        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            result = upload_file(str(local), "org/42/runs/run-1/step_1/test.txt")

        assert result == "org/42/runs/run-1/step_1/test.txt"
        mock_client.upload_file.assert_called_once_with(
            str(local), "test-bucket", "org/42/runs/run-1/step_1/test.txt"
        )

    def test_upload_missing_local_file_raises_r2_error(self):
        with pytest.raises(R2Error, match="local file not found"):
            upload_file("/nonexistent/path/file.txt", "org/42/test.txt")

    def test_upload_client_error_raises_r2_error(self, tmp_path):
        local = tmp_path / "test.txt"
        local.write_text("hello")

        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.upload_file.side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
                "PutObject",
            )
            mock_client_fn.return_value = mock_client

            with pytest.raises(R2Error, match="upload_file failed"):
                upload_file(str(local), "org/42/test.txt")


# ── download_file ─────────────────────────────────────────────────────────────

class TestDownloadFile:
    def test_download_success_creates_local_file(self, tmp_path):
        local = str(tmp_path / "downloaded.txt")

        def fake_download(bucket, key, path):
            with open(path, "w") as f:
                f.write("downloaded content")

        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.download_file.side_effect = fake_download
            mock_client_fn.return_value = mock_client

            download_file("org/42/test.txt", local)

        assert os.path.exists(local)

    def test_download_creates_parent_directories(self, tmp_path):
        local = str(tmp_path / "deep" / "nested" / "dir" / "file.txt")

        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            download_file("org/42/test.txt", local)

        assert os.path.exists(os.path.dirname(local))

    def test_download_missing_key_raises_r2_error(self, tmp_path):
        local = str(tmp_path / "missing.txt")

        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.download_file.side_effect = ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
                "GetObject",
            )
            mock_client_fn.return_value = mock_client

            with pytest.raises(R2Error, match="key not found"):
                download_file("org/42/nonexistent.txt", local)


# ── file_exists ───────────────────────────────────────────────────────────────

class TestFileExists:
    def test_returns_true_when_key_exists(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.head_object.return_value = {"ContentLength": 100}
            mock_client_fn.return_value = mock_client

            assert file_exists("org/42/test.txt") is True

    def test_returns_false_when_key_missing(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.head_object.side_effect = ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
                "HeadObject",
            )
            mock_client_fn.return_value = mock_client

            assert file_exists("org/42/missing.txt") is False

    def test_returns_false_on_403(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.head_object.side_effect = ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}},
                "HeadObject",
            )
            mock_client_fn.return_value = mock_client

            assert file_exists("org/42/secret.txt") is False


# ── list_files ────────────────────────────────────────────────────────────────

class TestListFiles:
    def test_returns_keys_under_prefix(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            paginator = MagicMock()
            paginator.paginate.return_value = [
                {"Contents": [
                    {"Key": "org/42/runs/run-1/step_1/output.txt"},
                    {"Key": "org/42/runs/run-1/step_1/data.csv"},
                ]},
            ]
            mock_client.get_paginator.return_value = paginator
            mock_client_fn.return_value = mock_client

            result = list_files("org/42/runs/run-1/step_1/")

        assert len(result) == 2
        assert "org/42/runs/run-1/step_1/output.txt" in result
        assert "org/42/runs/run-1/step_1/data.csv" in result

    def test_returns_empty_list_when_no_files(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            paginator = MagicMock()
            paginator.paginate.return_value = [{"Contents": []}]
            mock_client.get_paginator.return_value = paginator
            mock_client_fn.return_value = mock_client

            result = list_files("org/42/runs/nonexistent/")

        assert result == []

    def test_client_error_raises_r2_error(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.get_paginator.side_effect = ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
                "ListObjectsV2",
            )
            mock_client_fn.return_value = mock_client

            with pytest.raises(R2Error, match="list_files failed"):
                list_files("org/42/")


# ── delete_file ───────────────────────────────────────────────────────────────

class TestDeleteFile:
    def test_delete_success(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            delete_file("org/42/runs/run-1/step_7/recommendation.txt")

        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="org/42/runs/run-1/step_7/recommendation.txt",
        )

    def test_delete_client_error_raises_r2_error(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.delete_object.side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
                "DeleteObject",
            )
            mock_client_fn.return_value = mock_client

            with pytest.raises(R2Error, match="delete_file failed"):
                delete_file("org/42/protected.txt")


# ── generate_presigned_url ────────────────────────────────────────────────────

class TestPresignedUrl:
    def test_returns_url_string(self):
        with patch("pipeline.tasks.r2._client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = (
                "https://test.r2.example.com/org/42/test.txt?signature=abc"
            )
            mock_client_fn.return_value = mock_client

            url = generate_presigned_url("org/42/test.txt", expiry_seconds=3600)

        assert url.startswith("https://")
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "org/42/test.txt"},
            ExpiresIn=3600,
        )
