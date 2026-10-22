"""Backup and retention management for stored exports and system data.

Ensures stored export files (encrypted at rest) are systematically included in backups
and preserved according to the enterprise retention period (7 years / 2555 days).
"""
import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings


class BackupService:
    @staticmethod
    def get_retention_policy() -> Dict[str, Any]:
        """Return the official retention policy for stored files and exports."""
        return {
            "retention_period_days": settings.EXPORT_RETENTION_DAYS,
            "retention_period_years": round(settings.EXPORT_RETENTION_DAYS / 365, 1),
            "policy_description": (
                f"Exported files, frozen comparison runs, and vendor dispute records "
                f"are retained for {settings.EXPORT_RETENTION_DAYS} days "
                f"({round(settings.EXPORT_RETENTION_DAYS / 365)} years) to support procurement "
                f"audit, contract claims, and vendor dispute defense."
            ),
            "storage_location": str(Path(settings.REPORT_DIR) / "exports"),
            "encryption_at_rest": True,
            "encryption_algorithm": "ENC1-HMAC-SHA256-CTR",
            "access_control": "Reviewer and Admin only",
            "included_in_backups": True,
            "backup_directory": settings.BACKUP_DIR,
        }

    @staticmethod
    def get_backup_included_paths() -> List[str]:
        """Return paths guaranteed to be included in data backups."""
        exports_path = Path(settings.REPORT_DIR) / "exports"
        exports_path.mkdir(parents=True, exist_ok=True)
        return [str(exports_path)]

    @staticmethod
    def create_backup(destination_dir: Optional[str] = None) -> Dict[str, Any]:
        """Create a backup archive containing all stored export files and metadata."""
        dest_path = Path(destination_dir or settings.BACKUP_DIR)
        dest_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_name = f"datacenter_exports_backup_{timestamp}.tar.gz"
        archive_path = dest_path / archive_name

        exports_dir = Path(settings.REPORT_DIR) / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        file_count = 0
        total_size = 0

        with tarfile.open(archive_path, "w:gz") as tar:
            for root, _, files in os.walk(exports_dir):
                for f in files:
                    full_p = Path(root) / f
                    arcname = os.path.relpath(full_p, exports_dir.parent)
                    tar.add(full_p, arcname=arcname)
                    file_count += 1
                    total_size += full_p.stat().st_size

        return {
            "status": "success",
            "archive_name": archive_name,
            "archive_path": str(archive_path),
            "files_backed_up": file_count,
            "total_bytes": total_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "retention_policy_days": settings.EXPORT_RETENTION_DAYS,
        }
