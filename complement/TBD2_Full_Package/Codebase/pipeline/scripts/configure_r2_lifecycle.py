"""
pipeline/scripts/configure_r2_lifecycle.py
Configure Cloudflare R2 lifecycle rules per architecture decision D5:
  - Transition to Infrequent Access after 30 days

No automatic Expiration/delete rule. S3-compatible lifecycle filters only
support a single static prefix - no wildcards - so a rule cannot be scoped to
"each org's runs/ folder" without enumerating every org_id (impractical, and
would need re-running whenever an org is added). The "org/" prefix is the
only expressible filter, but it also covers org/{org_id}/reference/
(analyst-uploaded config reused by every future run) and
org/{org_id}/module_outputs/ (the stable Apex handoff CSVs + manifests,
pipeline/tasks/r2.py) - a 365-day blanket Expiration on that prefix would
silently delete those the first time an org goes over a year without
re-triggering a given module, breaking its next Apex run with no warning
until it fails. The IA transition is safe to apply broadly (cheaper storage,
still available); deletion is not, so it is left out here. GDPR erasure
already has its own explicit, targeted mechanism (DELETE
/pipelines/runs/{run_id}/files) - this script does not need to duplicate it
with a blanket time-based rule.

Run once during initial deployment:
    python pipeline/scripts/configure_r2_lifecycle.py

Requirements:
    CLOUDFLARE_R2_BUCKET, CLOUDFLARE_R2_ENDPOINT,
    CLOUDFLARE_R2_ACCESS_KEY, CLOUDFLARE_R2_SECRET_KEY
"""
import json
import os
import sys

import boto3
from botocore.config import Config


def configure_lifecycle():
    bucket = os.environ["CLOUDFLARE_R2_BUCKET"]
    endpoint = os.environ["CLOUDFLARE_R2_ENDPOINT"]
    access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY"]
    secret_key = os.environ["CLOUDFLARE_R2_SECRET_KEY"]

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    lifecycle_config = {
        "Rules": [
            {
                # IA after 30d only - no Expiration. See the module docstring:
                # a blanket delete on this prefix would also catch reference/
                # and module_outputs/, which must never auto-expire.
                "ID": "pipeline-run-files-lifecycle",
                "Status": "Enabled",
                "Filter": {"Prefix": "org/"},
                "Transitions": [
                    {
                        "Days": 30,
                        "StorageClass": "STANDARD_IA",
                    }
                ],
            },
        ]
    }

    try:
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration=lifecycle_config,
        )
        print(f"✅ Lifecycle rule applied to bucket: {bucket}")
        print(f"   - Transition to Infrequent Access: after 30 days")
        print(f"   - No auto-delete (see module docstring - GDPR erasure is a separate, explicit endpoint)")
        print(f"   - Prefix: org/ (all pipeline run files)")

    except Exception as exc:
        print(f"❌ Failed to apply lifecycle rule: {exc}")
        print(f"\nNote: Cloudflare R2 lifecycle rules require the R2 plan to support them.")
        print(f"If this fails, configure manually in the Cloudflare dashboard:")
        print(f"  R2 → {bucket} → Settings → Object Lifecycle Rules")
        sys.exit(1)


def verify_lifecycle():
    """Read back and print the current lifecycle config."""
    bucket = os.environ["CLOUDFLARE_R2_BUCKET"]
    endpoint = os.environ["CLOUDFLARE_R2_ENDPOINT"]
    access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY"]
    secret_key = os.environ["CLOUDFLARE_R2_SECRET_KEY"]

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    try:
        response = client.get_bucket_lifecycle_configuration(Bucket=bucket)
        print(f"\nCurrent lifecycle config for {bucket}:")
        print(json.dumps(response["Rules"], indent=2, default=str))
    except client.exceptions.NoSuchLifecycleConfiguration:
        print(f"No lifecycle rules configured for {bucket}")
    except Exception as exc:
        print(f"Could not read lifecycle config: {exc}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Configure R2 lifecycle rules")
    parser.add_argument("--verify", action="store_true", help="Print current rules only")
    args = parser.parse_args()

    if args.verify:
        verify_lifecycle()
    else:
        configure_lifecycle()
        verify_lifecycle()
