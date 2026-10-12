#!/usr/bin/env python3
"""FreeLLMAPI Auto-Updater with Safety Checks"""

import logging
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from packaging.version import Version
from pathlib import Path
import requests

# CONFIGURATION (no hardcoded username paths)
INSTALL_DIR = Path.home() / "Apps" / "FreeLLMAPI"
OLD_DIR = INSTALL_DIR.parent / "FreeLLMAPI.old"
DOWNLOAD_DIR = Path.home() / "downloads"
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "freellmapi_update.log"
REPO = "tashfeenahmed/freellmapi"


def setup_logging():
    """Setup logging to file and console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def log_action(logger, action, detail=""):
    """Write to log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] {action}: {detail}")


def get_local_version(install_dir):
    """Get version from executable file properties (right-click Details)."""
    if not install_dir.exists():
        return "unknown"
    exe_path = install_dir / "freeLLMAPI.exe"
    if not exe_path.exists():
        return "unknown"
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"(Get-Item '{exe_path}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logging.warning(f"Could not read version via PowerShell: {e}")
    return "unknown"


def get_latest_version(repo):
    """Get latest version from GitHub releases."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        tag = data.get("tag_name", "")
        version = tag.lstrip("v")
        download_url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith("-win.zip"):
                download_url = asset["browser_download_url"]
                break
        if not download_url:
            logging.error("No Windows ZIP found in latest release")
            return None, None
        return version, download_url
    except Exception as e:
        logging.error(f"Failed to get latest version: {e}")
        return None, None


def compare_versions(local, latest):
    """Compare versions. Returns: -1 (local newer), 0 (equal), 1 (latest newer)."""
    try:
        local_ver = Version(local)
        latest_ver = Version(latest)
        if latest_ver > local_ver:
            return 1
        elif latest_ver < local_ver:
            return -1
        else:
            return 0
    except Exception as e:
        logging.error(f"Version comparison failed: {e}")
        return 0


def is_process_running(process_name):
    """Check if a process is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return process_name.lower() in result.stdout.lower()
    except Exception:
        return False


def kill_process(process_name, force=True):
    """Kill a process by name."""
    try:
        cmd = ["taskkill", "/IM", f"{process_name}.exe"]
        if force:
            cmd.append("/F")
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Failed to kill process: {e}")
        return False


def download_and_verify(download_url, dest_path):
    """Download file and verify ZIP integrity."""
    try:
        logging.info(f"Downloading from {download_url}")
        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()
        temp_file = dest_path.with_suffix(".zip.tmp")
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if zipfile.is_zipfile(temp_file):
            temp_file.rename(dest_path)
            logging.info(f"Download verified: {dest_path}")
            return True
        else:
            logging.error("Downloaded file is not a valid ZIP")
            temp_file.unlink(missing_ok=True)
            return False
    except Exception as e:
        logging.error(f"Download failed: {e}")
        return False


def backup_existing(install_dir, old_dir):
    """Backup existing installation (removes stale .old first)."""
    if not install_dir.exists():
        return True
    if old_dir.exists():
        shutil.rmtree(old_dir)
    try:
        shutil.copytree(install_dir, old_dir)
        logging.info(f"Backed up to {old_dir}")
        return True
    except Exception as e:
        logging.error(f"Backup failed: {e}")
        return False


def check_and_update(dry_run=True, auto_start=False):
    """Main update logic with all safety conditions."""
    logger = setup_logging()
    logging.info("=== FreeLLMAPI Update Check ===")
    logging.info(f"Dry run: {dry_run}")

    local_version = get_local_version(INSTALL_DIR)
    logging.info(f"Local version: {local_version}")

    latest_version, download_url = get_latest_version(REPO)
    if not latest_version or not download_url:
        logging.error("Failed to get latest version from GitHub")
        return False
    logging.info(f"Latest version: {latest_version}")

    cmp = compare_versions(local_version, latest_version)
    if cmp <= 0:
        logging.info(f"No update needed. Local: {local_version}, Latest: {latest_version}")
        if not dry_run:
            log_action(logger, "no_new_version", f"local={local_version}")
        return True

    logging.info(f"Update available: {local_version} -> {latest_version}")

    if dry_run:
        logging.info("[DRY RUN] Would perform update")
        log_action(logger, "dry_run_check", f"local={local_version}, latest={latest_version}")
        return True

    # Kill running process
    if is_process_running("freeLLMAPI"):
        logging.info("Process is running, killing...")
        kill_process("freeLLMAPI", force=True)
        time.sleep(2)
        if is_process_running("freeLLMAPI"):
            logging.error("Failed to kill process!")
            return False
        log_action(logger, "process_killed")

    # Backup existing installation
    if INSTALL_DIR.exists():
        if not backup_existing(INSTALL_DIR, OLD_DIR):
            logging.error("Backup failed, aborting")
            return False
        log_action(logger, "backup_created")

    # Download new version
    download_path = DOWNLOAD_DIR / f"FreeLLMAPI-{latest_version}-win.zip"
    if not download_and_verify(download_url, download_path):
        logging.error("Download failed")
        return False
    log_action(logger, "downloaded", str(download_path))

    # Remove old folder
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR)
        log_action(logger, "old_folder_removed")

    # Extract new version
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(download_path, "r") as zip_ref:
        zip_ref.extractall(INSTALL_DIR)
    logging.info(f"Extracted to {INSTALL_DIR}")
    log_action(logger, "extracted")

    # Clean up download zip after unpack
    download_path.unlink(missing_ok=True)
    log_action(logger, "download_cleaned")

    # Start new version if requested
    exe_path = INSTALL_DIR / "freeLLMAPI.exe"
    if exe_path.exists():
        log_action(logger, "ready_to_run", str(exe_path))
        if auto_start and not dry_run:
            try:
                logging.info("Starting new version...")
                subprocess.Popen([str(exe_path)])
                log_action(logger, "started", str(exe_path))
            except Exception as e:
                logging.error(f"Failed to start: {e}")
                log_action(logger, "start_failed", str(e))

    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FreeLLMAPI Auto-Updater")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually perform the update")
    parser.add_argument("--start", action="store_true", help="Start the new version after update")
    args = parser.parse_args()
    success = check_and_update(dry_run=not args.no_dry_run, auto_start=args.start)
    sys.exit(0 if success else 1)
