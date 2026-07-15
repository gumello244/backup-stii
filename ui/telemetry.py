from __future__ import annotations

"""Fire-and-forget telemetry reporting shared across UI code.

Thin wrapper over GlobalAsyncWorker.api_service so call sites don't each
repeat the "get worker, check api_service is up, submit_task" boilerplate.

Example:
    report_success("MERGE_COMPLETE", {"file_count": 12})
"""
from typing import Optional

from ui.workers import get_global_worker


def report_success(event: str, details: Optional[dict[str, object]] = None) -> None:
    """Report a successful event, if telemetry is available."""
    worker = get_global_worker()
    if worker.api_service:
        worker.submit_task(worker.api_service.report_success(event, details))


def report_failure(
    event: str, error_msg: str, details: Optional[dict[str, object]] = None,
) -> None:
    """Report a failed event, if telemetry is available."""
    worker = get_global_worker()
    if worker.api_service:
        worker.submit_task(worker.api_service.report_failure(event, error_msg, details))
