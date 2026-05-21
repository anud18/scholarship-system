"""RenewalAuditService — check invariants for renewal/challenge state.

Per spec Section 12, every approved challenge application MUST point to a
renewal whose status is `cancelled_by_challenge`. The general-distribution
algorithm enforces this transition atomically when a challenge is approved,
but operational issues (manual data fixes, partial migrations, bugs in
future refactors) can break the invariant.

This service surfaces violations so admins can spot data drift quickly.
"""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus


class RenewalAuditService:
    """Audit invariants tying approved challenges to their cancelled renewals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_invariant_violations(self) -> List[Dict]:
        """Find approved challenges whose linked renewal is not cancelled_by_challenge.

        Invariant (spec §12): for every Application_C with
        ``status == approved`` and ``challenges_application_id IS NOT NULL``,
        the referenced renewal application must have
        ``status == cancelled_by_challenge``.

        Returns:
            A list of violation dicts, each shaped as::

                {
                    "challenge_id": int,
                    "renewal_id": int,
                    "actual_renewal_status": str,  # the .value of the status
                }

            Returns an empty list when the invariant holds for all rows.
        """
        stmt = select(
            Application.id,
            Application.challenges_application_id,
            Application.status,
        ).where(
            Application.challenges_application_id.is_not(None),
            Application.status == ApplicationStatus.approved,
        )
        rows = (await self.db.execute(stmt)).all()

        violations: List[Dict] = []
        for challenge_id, renewal_id, _challenge_status in rows:
            renewal = await self.db.scalar(select(Application).where(Application.id == renewal_id))
            if renewal is None:
                # Dangling FK — treat as a violation so it surfaces in the audit.
                violations.append(
                    {
                        "challenge_id": challenge_id,
                        "renewal_id": renewal_id,
                        "actual_renewal_status": None,
                    }
                )
                continue

            if renewal.status != ApplicationStatus.cancelled_by_challenge:
                actual = renewal.status.value if hasattr(renewal.status, "value") else renewal.status
                violations.append(
                    {
                        "challenge_id": challenge_id,
                        "renewal_id": renewal_id,
                        "actual_renewal_status": actual,
                    }
                )

        return violations
