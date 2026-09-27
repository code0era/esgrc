"""
pipeline/tasks/r2.py
Cloudflare R2 file I/O helpers.

Key patterns:
  Run-scoped:   org/{org_id}/runs/{run_id}/step_{n}/{filename}
  Module handoff: org/{org_id}/module_outputs/{filename}
  Org reference: org/{org_id}/reference/{filename}

Performance: boto3 client is a module-level singleton created once per
worker process (after fork). Creating a new client per call adds ~50ms
of TLS handshake overhead on every R2 operation.

CORRECTIONS APPLIED (June 2026 audit):
1. check_esgrc_preflight(): "input_metrics_data.csv" -> "input_metric_values_esgrc.csv"
   to match the actual filename AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py reads.
   "low_performing_json_file.json" removed - confirmed via the real script that
   ESGRC Step 1 only reads esgrc_performance_json_file.json, there is no separate
   low-performing JSON input file.
2. check_apex_preflight(): module CSV name list replaced. The original list used
   placeholder names (social, cyber, gnotes, corpgov, grc, erm, audit, policy,
   reg, ethics, cgi) that do not correspond to any of TBD2's real 12 modules.
   Replaced with the real module set: brand, shared, esgrc, enterprise, customer,
   service, product, mkts, bspt, integration, ictm, resource. Note "bspt" not
   "business_partner" - confirmed against all_module_low_performance_analysis_1_0.py.
"""
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# ── Singleton boto3 client ────────────────────────────────────────────────────
_r2_client = None
_r2_lock = threading.Lock()


def _client():
    """Return the module-level singleton boto3 S3 client (thread-safe lazy init)."""
    global _r2_client
    if _r2_client is None:
        with _r2_lock:
            if _r2_client is None:
                # Optional S3 addressing-style override. Cloudflare R2 uses the
                # default (virtual-hosted); S3-compatible stores reached by a bare
                # host:port (e.g. a local MinIO at http://minio:9000) need
                # path-style so the bucket isn't prepended as a subdomain. Unset in
                # prod → identical to the previous behaviour.
                _addr = os.environ.get("S3_ADDRESSING_STYLE")
                _r2_client = boto3.client(
                    "s3",
                    endpoint_url=os.environ["CLOUDFLARE_R2_ENDPOINT"],
                    aws_access_key_id=os.environ["CLOUDFLARE_R2_ACCESS_KEY"],
                    aws_secret_access_key=os.environ["CLOUDFLARE_R2_SECRET_KEY"],
                    config=Config(
                        signature_version="s3v4",
                        retries={"max_attempts": 3, "mode": "standard"},
                        max_pool_connections=20,
                        **({"s3": {"addressing_style": _addr}} if _addr else {}),
                    ),
                    region_name="auto",
                )
    return _r2_client


def _bucket() -> str:
    return os.environ["CLOUDFLARE_R2_BUCKET"]


# ── Key builders ──────────────────────────────────────────────────────────────

def run_key(org_id: str, run_id: str, step: int, filename: str) -> str:
    return f"org/{org_id}/runs/{run_id}/step_{step}/{filename}"


def module_output_key(org_id: str, filename: str) -> str:
    return f"org/{org_id}/module_outputs/{filename}"


def module_handoff_csv_key(org_id: str, module: str) -> str:
    """Stable path Apex Step 1 consumes for a module's risk-assessment CSV."""
    return module_output_key(org_id, f"data_for_risk_assessment_{module}.csv")


def module_manifest_key(org_id: str, module: str) -> str:
    """Provenance sidecar next to a module's handoff CSV (timestamp + source run)."""
    return module_output_key(org_id, f"data_for_risk_assessment_{module}.manifest.json")


def reference_key(org_id: str, filename: str) -> str:
    return f"org/{org_id}/reference/{filename}"


def org_settings_key(org_id: str, filename: str) -> str:
    return f"org/{org_id}/settings/{filename}"


# ── R2Error ───────────────────────────────────────────────────────────────────

class R2Error(Exception):
    """Raised on any R2 operation failure. Never swallowed - always propagates."""


# ── File operations ───────────────────────────────────────────────────────────

def upload_file(local_path: str, r2_key: str) -> str:
    """Upload a local file to R2. Returns r2_key. Raises R2Error on failure."""
    local_path = str(local_path)
    if not os.path.exists(local_path):
        raise R2Error(f"upload_file: local file not found: {local_path}")
    try:
        _client().upload_file(local_path, _bucket(), r2_key)
        logger.info("R2 upload OK: %s → %s", local_path, r2_key)
        return r2_key
    except (ClientError, BotoCoreError) as exc:
        raise R2Error(f"upload_file failed for key={r2_key}: {exc}") from exc


def download_file(r2_key: str, local_path: str) -> None:
    """Download an R2 object to disk. Creates parent dirs. Raises R2Error if missing."""
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        _client().download_file(_bucket(), r2_key, str(local_path))
        logger.info("R2 download OK: %s → %s", r2_key, local_path)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise R2Error(f"download_file: key not found: {r2_key}") from exc
        raise R2Error(f"download_file failed for key={r2_key}: {exc}") from exc
    except BotoCoreError as exc:
        raise R2Error(f"download_file failed for key={r2_key}: {exc}") from exc


def upload_text(content: str, r2_key: str) -> str:
    """Upload a string directly to R2 (no disk I/O). Returns r2_key."""
    try:
        _client().put_object(
            Bucket=_bucket(),
            Key=r2_key,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        logger.info("R2 upload_text OK: %d chars → %s", len(content), r2_key)
        return r2_key
    except (ClientError, BotoCoreError) as exc:
        raise R2Error(f"upload_text failed for key={r2_key}: {exc}") from exc


def download_text(r2_key: str) -> str:
    """Download an R2 object directly to a string (no disk I/O)."""
    try:
        response = _client().get_object(Bucket=_bucket(), Key=r2_key)
        content = response["Body"].read().decode("utf-8", errors="replace")
        logger.info("R2 download_text OK: %s (%d chars)", r2_key, len(content))
        return content
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise R2Error(f"download_text: key not found: {r2_key}") from exc
        raise R2Error(f"download_text failed for key={r2_key}: {exc}") from exc
    except BotoCoreError as exc:
        raise R2Error(f"download_text failed for key={r2_key}: {exc}") from exc


def download_bytes(r2_key: str) -> bytes:
    """Download an R2 object as raw bytes (binary-safe - csv/txt/pdf)."""
    try:
        response = _client().get_object(Bucket=_bucket(), Key=r2_key)
        data = response["Body"].read()
        logger.info("R2 download_bytes OK: %s (%d bytes)", r2_key, len(data))
        return data
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise R2Error(f"download_bytes: key not found: {r2_key}") from exc
        raise R2Error(f"download_bytes failed for key={r2_key}: {exc}") from exc
    except BotoCoreError as exc:
        raise R2Error(f"download_bytes failed for key={r2_key}: {exc}") from exc


def file_exists(r2_key: str) -> bool:
    """Return True if the key exists. Never raises."""
    try:
        _client().head_object(Bucket=_bucket(), Key=r2_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "403"):
            return False
        logger.warning("file_exists check error for key=%s: %s", r2_key, exc)
        return False
    except BotoCoreError:
        return False


def list_files(prefix: str) -> List[str]:
    """List all R2 keys under prefix. Returns [] if none. Raises R2Error on API failure."""
    try:
        paginator = _client().get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    except (ClientError, BotoCoreError) as exc:
        raise R2Error(f"list_files failed for prefix={prefix}: {exc}") from exc


def delete_file(r2_key: str) -> None:
    """Delete an R2 object. Used for GDPR erasure. Raises R2Error on failure."""
    try:
        _client().delete_object(Bucket=_bucket(), Key=r2_key)
        logger.info("R2 delete OK: %s", r2_key)
    except (ClientError, BotoCoreError) as exc:
        raise R2Error(f"delete_file failed for key={r2_key}: {exc}") from exc


def generate_presigned_url(r2_key: str, expiry_seconds: int = 3600) -> str:
    """Generate a presigned download URL. Raises R2Error on failure."""
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": r2_key},
            ExpiresIn=expiry_seconds,
        )
    except (ClientError, BotoCoreError) as exc:
        raise R2Error(f"generate_presigned_url failed for key={r2_key}: {exc}") from exc


# The 12 real TBD2 modules. "bspt" (not "business_partner") confirmed against
# all_module_low_performance_analysis_1_0.py's column-key usage.
#
# check_esgrc_preflight/check_apex_preflight (which used to live here) were
# deleted 2026-08-17 as dead code: pipeline_router.trigger_pipeline's own
# inline file_exists() loop over config_json["required_input_files"] is the
# one actually in use, and it's config-driven rather than hardcoding this
# module list a second time.
APEX_MODULE_NAMES = [
    "brand",
    "shared",
    "esgrc",
    "enterprise",
    "customer",
    "service",
    "product",
    "mkts",
    "bspt",
    "ictm",
    "resource",
    "integration",
]


# ── Module handoff (auto-copy + provenance timestamps) ────────────────────────
#
# Each module pipeline (ESGRC today; the other 11 as they come online) produces a
# data_for_risk_assessment_{module}.csv. Apex Step 1 consumes these from the stable
# module_outputs/ path - NOT from the run-scoped path - so a module's latest output
# must be auto-copied there when the run finishes. write_module_handoff does that
# copy AND drops a provenance manifest (which run produced it, and when) beside the
# CSV, so Apex and the UI can show data freshness ("Data as of … · Run #…") instead
# of consuming an undated file blindly.

HANDOFF_SCHEMA_VERSION = 1


def write_module_handoff(
    local_csv_path: str,
    org_id: str,
    module: str,
    source_run_id: str,
    produced_at: Optional[str] = None,
) -> Dict[str, str]:
    """
    Copy a module's risk-assessment CSV to the stable Apex handoff path and write a
    provenance manifest beside it. Returns {"csv_key", "manifest_key", "produced_at"}.

    The manifest is uploaded via upload_file (a temp JSON file) rather than raw text
    so it flows through the same single R2 write path as every other artifact.
    """
    csv_key = module_handoff_csv_key(org_id, module)
    upload_file(local_csv_path, csv_key)

    produced_at = produced_at or datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "module": module,
        "csv_filename": f"data_for_risk_assessment_{module}.csv",
        "csv_key": csv_key,
        "source_run_id": source_run_id,
        "produced_at": produced_at,
    }
    manifest_key = module_manifest_key(org_id, module)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".manifest.json", delete=False, encoding="utf-8"
    )
    try:
        json.dump(manifest, tmp, indent=2)
        tmp.close()
        upload_file(tmp.name, manifest_key)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    logger.info(
        "Module handoff written: %s (source_run=%s, produced_at=%s)",
        csv_key, source_run_id, produced_at,
    )
    return {"csv_key": csv_key, "manifest_key": manifest_key, "produced_at": produced_at}


def read_module_handoff_manifest(org_id: str, module: str) -> Optional[Dict]:
    """
    Return a module's handoff provenance manifest, or None if absent/unreadable.
    Never raises - provenance is best-effort telemetry, not a hard dependency.
    """
    key = module_manifest_key(org_id, module)
    if not file_exists(key):
        return None
    try:
        return json.loads(download_text(key))
    except (R2Error, ValueError, TypeError):
        logger.warning("Unreadable handoff manifest at %s", key)
        return None


def get_apex_handoff_provenance(org_id: str) -> List[Dict]:
    """
    Per-module handoff provenance for an org (for the freshness badge / Apex logging).
    One entry per known module: {module, present, produced_at, source_run_id}.
    present=False means that module has not produced a handoff yet.
    """
    provenance: List[Dict] = []
    for module in APEX_MODULE_NAMES:
        manifest = read_module_handoff_manifest(org_id, module)
        if manifest is None:
            provenance.append(
                {"module": module, "present": file_exists(module_handoff_csv_key(org_id, module)),
                 "produced_at": None, "source_run_id": None}
            )
        else:
            provenance.append(
                {"module": module, "present": True,
                 "produced_at": manifest.get("produced_at"),
                 "source_run_id": manifest.get("source_run_id")}
            )
    return provenance