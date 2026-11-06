"""Upload one file: self-check, copy, index, then the automatic self-test (once per file).

A file that fails the self-check is not added. Any file; PDF only until PLAN.md Day 4.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from learnbot import config
from learnbot.index import file_hash
from learnbot.pdf_check import FAIL, check_pdf


def find_document(name):
    """Path of an uploaded file or a test document by file name, or None."""
    for folder in (config.UPLOAD_DIR, config.TEST_DOCS_DIR):
        if (Path(folder) / name).is_file():
            return Path(folder) / name
    return None


@dataclass
class Upload:
    check: object  # PdfCheckResult
    path: Path = None  # the stored file; None if the file was not added
    self_test: object = None  # learnbot.selftest.SelfTest
    problem: str = ""  # why the file was not added


def store_file(path, upload_dir=None):
    """(stored path, problem). A different file with the same name is never overwritten."""
    path = Path(path)
    target = Path(upload_dir or config.UPLOAD_DIR) / path.name
    if target.is_file():
        if file_hash(target) != file_hash(path):
            return None, f"A different file named {path.name} is already uploaded. Rename the new file and try again."
        return target, ""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    return target, ""


def upload_file(path, run_test, upload_dir=None):
    """Check the file; if it may be used, store it and run run_test(stored path) -> SelfTest."""
    check = check_pdf(path)
    if check.verdict == FAIL:
        return Upload(check, problem="This file cannot be used: " + "; ".join(check.reasons))
    stored, problem = store_file(path, upload_dir)
    if problem:
        return Upload(check, problem=problem)
    return Upload(check, stored, run_test(stored))
