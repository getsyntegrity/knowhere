from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.document_ingestion.job_state_gate import mark_job_running
from app.services.document_ingestion.page_estimator import PageEstimator
from app.services.document_ingestion.parse_result_package import (
    build_parse_result_package,
)
from app.services.document_ingestion.parse_execution import execute_document_parse
from app.services.document_ingestion.processing_billing import (
    charge_parse_job_pages,
    record_skipped_parse_job_billing,
    record_processing_start,
)
from app.services.document_ingestion.processing_context import (
    ParseJobContext,
    load_parse_job_context,
)
from app.services.document_ingestion.source_preparation import prepare_source_file
from app.services.document_ingestion.success_finalization import finalize_parse_success
from app.services.document_ingestion.workspace import (
    TemporaryParseWorkspace,
)
from loguru import logger

from shared.core.exceptions.domain_exceptions import ValidationException
from shared.services.jobs.lifecycle.service import get_sync_job_lifecycle_service
from shared.services.redis.distributed_lock import RedisJobLock
from shared.services.redis.redis_sync_service import (
    SyncRedisServiceFactory,
)
from shared.services.storage.result_storage import get_result_storage


class DocumentProcessingRun:
    """Run worker-side Document Ingestion for an uploaded file Job."""

    def execute(self, job_id: str, user_id: str | None) -> dict[str, object]:
        logger.info(f"Parse started: job_id={job_id}, user_id={user_id}")
        lifecycle_service = get_sync_job_lifecycle_service()

        redis_service = SyncRedisServiceFactory.get_service()
        job_context = load_parse_job_context(job_id, user_id, redis_service)

        should_process = mark_job_running(job_id, job_context.redis_service)
        if not should_process:
            logger.warning(f"Skipping parse_task for inactive job: job_id={job_id}")
            return {
                "status": "skipped",
                "job_id": job_id,
                "reason": "job_already_terminal",
            }

        with RedisJobLock(job_context.redis_service, job_id):
            task_workspace = TemporaryParseWorkspace.create(job_id)
            try:
                result = _run_parse_job(
                    job_id=job_id,
                    job_context=job_context,
                    lifecycle_service=lifecycle_service,
                    task_workspace=task_workspace,
                )
            finally:
                task_workspace.cleanup()

        return result


def _run_parse_job(
    *,
    job_id: str,
    job_context: ParseJobContext,
    lifecycle_service: Any,
    task_workspace: TemporaryParseWorkspace,
) -> dict[str, object]:
    lifecycle_service.update_progress(job_id, progress=10, message="Parsing document...")

    prepared_source = prepare_source_file(
        job_id=job_id,
        job_context=job_context,
        input_dir=task_workspace.input_dir,
    )

    workload_estimate = PageEstimator.estimate_workload(prepared_source.local_file_path)
    page_count = workload_estimate.page_count
    logger.info(
        "Workload estimation: "
        f"job_id={job_id}, page_count={page_count}, "
        f"method={workload_estimate.method}, "
        f"fallback_reason={workload_estimate.fallback_reason}"
    )

    processing_started_at = datetime.now(timezone.utc)
    if _is_pdf_page_limit_exceeded(
        file_extension=prepared_source.file_extension,
        page_count=page_count,
    ):
        billing_snapshot = record_skipped_parse_job_billing(
            job_id=job_id,
            workload_estimate=workload_estimate,
        )
        record_processing_start(
            job_id=job_id,
            job_context=job_context,
            billing_snapshot=billing_snapshot,
            processing_started_at=processing_started_at,
            workload_estimate=workload_estimate,
        )
        _raise_pdf_page_limit_exceeded(page_count)

    billing_snapshot = charge_parse_job_pages(
        job_id=job_id,
        filename=prepared_source.source_file_name,
        job_user_id=job_context.job_user_id,
        workload_estimate=workload_estimate,
    )
    record_processing_start(
        job_id=job_id,
        job_context=job_context,
        billing_snapshot=billing_snapshot,
        processing_started_at=processing_started_at,
        workload_estimate=workload_estimate,
    )

    parse_output = execute_document_parse(
        job_id=job_id,
        job_context=job_context,
        prepared_source=prepared_source,
        output_dir=task_workspace.output_dir,
    )

    lifecycle_service.update_progress(
        job_id,
        progress=30,
        message="Parse completed, preparing chunks...",
    )
    result_package = build_parse_result_package(
        job_id=job_id,
        filename=prepared_source.source_file_name,
        parse_output=parse_output,
    )

    lifecycle_service.update_progress(
        job_id,
        progress=70,
        message="Chunks ready, generating zip...",
    )
    logger.info(
        f"Chunks prepared: job_id={job_id}, count={len(result_package.chunks)}"
    )

    return finalize_parse_success(
        result_package=result_package,
        job_context=job_context,
        job_id=job_id,
        lifecycle_service=lifecycle_service,
        processing_started_at=processing_started_at,
        task_workspace_dir=task_workspace.root_dir,
        result_storage_factory=get_result_storage,
    )


def _is_pdf_page_limit_exceeded(*, file_extension: str, page_count: int) -> bool:
    from shared.core.config import settings

    return file_extension == ".pdf" and page_count > settings.MAX_PDF_PAGE_LIMIT


def _raise_pdf_page_limit_exceeded(page_count: int) -> None:
    from shared.core.config import settings

    pdf_page_limit = settings.MAX_PDF_PAGE_LIMIT
    raise ValidationException(
        user_message=(
            f"Document too large: {page_count} pages exceeds the {pdf_page_limit}-page limit. "
            "Please split the document and upload in smaller batches."
        ),
        violations=[
            {
                "field": "page_count",
                "description": f"PDF has {page_count} pages, limit is {pdf_page_limit}",
            }
        ],
    )
