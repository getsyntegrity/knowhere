"""Billing boundary for job/work processing."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from shared.core.billing import BillingCalculator
from shared.core.config import settings
from shared.services.billing.credits_sync_service import SyncCreditsService

_SKIPPED_BILLING_STATUS: str = "skipped"
_CHARGED_BILLING_STATUS: str = "charged"


@dataclass(frozen=True)
class WorkBillingResult:
    """Result of authorizing and recording billing for work."""

    billing_status: str
    amount_micro_dollars: int
    credits: float

    @classmethod
    def skipped(cls) -> "WorkBillingResult":
        """Return the no-op billing result used by OSS/self-hosted mode."""
        return cls(
            billing_status=_SKIPPED_BILLING_STATUS,
            amount_micro_dollars=0,
            credits=0.0,
        )


class WorkBillingService:
    """Charge work when billing is enabled, otherwise return a no-op result."""

    def __init__(
        self,
        *,
        calculator: BillingCalculator | None = None,
        credits_service: SyncCreditsService | None = None,
    ) -> None:
        self._calculator = calculator or BillingCalculator()
        self._credits_service = credits_service

    def charge_for_pages(
        self,
        *,
        session: Session,
        user_id: str,
        page_count: int,
        filename: str,
    ) -> WorkBillingResult:
        """Authorize and charge per-page work if billing is enabled."""
        if not settings.BILLING_ENABLED:
            return WorkBillingResult.skipped()

        billing_result = self.estimate_page_charge(page_count=page_count)
        billing_reason = self._calculator.format_description(page_count, filename)
        credits_service = self._credits_service or SyncCreditsService()
        credits_service.deduct_credits(
            session=session,
            user_id=user_id,
            amount=billing_result.amount_micro_dollars,
            reason=billing_reason,
        )
        return billing_result

    def estimate_page_charge(self, *, page_count: int) -> WorkBillingResult:
        """Return the enabled-billing charge estimate for a page workload."""
        billing_amount = self._calculator.calculate_page_cost(page_count)
        return WorkBillingResult(
            billing_status=_CHARGED_BILLING_STATUS,
            amount_micro_dollars=billing_amount.amount,
            credits=billing_amount.to_credit(),
        )
