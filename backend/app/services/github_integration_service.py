"""
GitHub Integration Service

This service handles integration with GitHub for creating issues and reports
related to scholarship distribution and college review processes.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.college_review import (
    CollegeRanking,
    CollegeRankingItem,
    QuotaDistribution,
)


class GitHubIntegrationService:
    """Service for GitHub integration operations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.github_token = getattr(settings, "GITHUB_TOKEN", None)
        self.github_repo = getattr(settings, "GITHUB_REPO", "jotpalch/scholarship-system")

    async def create_distribution_report_issue(
        self, distribution: QuotaDistribution, ranking: Optional[CollegeRanking] = None
    ) -> Dict[str, Any]:
        """Create a GitHub issue with distribution report"""

        # Generate issue content
        issue_title = self._generate_issue_title(distribution)
        issue_body = await self._generate_issue_body(distribution, ranking)
        labels = self._generate_issue_labels(distribution)

        # Prepare GitHub issue data
        github_issue_data = {
            "title": issue_title,
            "body": issue_body,
            "labels": labels,
            "assignees": [],
        }

        # Create issue URL (for tracking purposes)
        issue_url = f"https://github.com/{self.github_repo}/issues"

        # In production, you would make an actual API call to GitHub
        # For now, we'll simulate and return the data structure
        simulated_issue = {
            "number": self._generate_issue_number(),
            "url": f"{issue_url}/{self._generate_issue_number()}",
            "title": issue_title,
            "body": issue_body,
            "state": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "html_url": f"{issue_url}/{self._generate_issue_number()}",
        }

        # Update distribution record with GitHub issue info
        distribution.github_issue_number = simulated_issue["number"]
        distribution.github_issue_url = simulated_issue["html_url"]

        await self.db.commit()

        return simulated_issue

    def _generate_issue_title(self, distribution: QuotaDistribution) -> str:
        """Generate GitHub issue title"""
        semester_text = f" - {distribution.semester}" if distribution.semester else ""
        return f"Scholarship Distribution Report - AY{distribution.academic_year}{semester_text}"

    async def _generate_issue_body(
        self, distribution: QuotaDistribution, ranking: Optional[CollegeRanking] = None
    ) -> str:
        """Generate GitHub issue body with detailed distribution report"""

        # Get ranking if not provided
        if not ranking and distribution.distribution_summary:
            # Find related ranking (simplified approach)
            stmt = (
                select(CollegeRanking)
                .where(
                    CollegeRanking.distribution_executed == True,
                    CollegeRanking.distribution_date.isnot(None),
                )
                .order_by(CollegeRanking.distribution_date.desc())
                .limit(1)
            )

            result = await self.db.execute(stmt)
            ranking = result.scalar_one_or_none()

        # Build issue body
        body_parts = []

        # Header
        body_parts.append("# Scholarship Distribution Report")
        body_parts.append(f"**Academic Year:** {distribution.academic_year}")
        if distribution.semester:
            body_parts.append(f"**Semester:** {distribution.semester}")
        body_parts.append(f"**Execution Date:** {distribution.executed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        body_parts.append("**Executed By:** System Admin")
        body_parts.append("")

        # Summary
        body_parts.append("## Distribution Summary")
        body_parts.append(f"- **Total Applications:** {distribution.total_applications}")
        body_parts.append(f"- **Total Quota:** {distribution.total_quota}")
        body_parts.append(f"- **Total Allocated:** {distribution.total_allocated}")
        body_parts.append(f"- **Success Rate:** {distribution.success_rate:.1f}%")
        body_parts.append(f"- **Algorithm Version:** {distribution.algorithm_version}")
        body_parts.append("")

        # Distribution by Sub-Type
        if distribution.distribution_summary:
            body_parts.append("## Distribution by Sub-Type")
            body_parts.append("| Sub-Type | Total Applications | Quota | Allocated | Rejected | Utilization |")
            body_parts.append("|----------|-------------------|-------|-----------|----------|-------------|")

            for sub_type, summary in distribution.distribution_summary.items():
                total_apps = summary.get("total_applications", 0)
                quota = summary.get("quota", 0)
                allocated = summary.get("allocated", 0)
                rejected = summary.get("rejected", 0)
                utilization = (allocated / quota * 100) if quota > 0 else 0

                body_parts.append(
                    f"| {sub_type} | {total_apps} | {quota} | {allocated} | {rejected} | {utilization:.1f}% |"
                )
            body_parts.append("")

        # Detailed Ranking Results
        if ranking:
            body_parts.append("## Detailed Ranking Results")
            body_parts.append(f"**Ranking:** {ranking.ranking_name}")
            body_parts.append(f"**Sub-Type:** {ranking.sub_type_code}")
            body_parts.append("")

            # Get ranking items
            stmt = (
                select(CollegeRankingItem)
                .options(
                    selectinload(CollegeRankingItem.application),
                    selectinload(CollegeRankingItem.college_review),
                )
                .where(CollegeRankingItem.ranking_id == ranking.id)
                .order_by(CollegeRankingItem.rank_position)
            )

            result = await self.db.execute(stmt)
            ranking_items = result.scalars().all()

            if ranking_items:
                body_parts.append("| Rank | Student | Student ID | Score | Status | Allocation |")
                body_parts.append("|------|---------|------------|-------|--------|------------|")

                for item in ranking_items:
                    student_name = (
                        item.application.student_data.get("cname", "N/A") if item.application.student_data else "N/A"
                    )
                    student_id = (
                        item.application.student_data.get("stdNo", "N/A") if item.application.student_data else "N/A"
                    )
                    score = f"{item.total_score:.2f}" if item.total_score else "N/A"
                    status_emoji = "✅" if item.is_allocated else "❌"
                    allocation_status = "Allocated" if item.is_allocated else "Rejected"

                    body_parts.append(
                        f"| {item.rank_position} | {student_name} | {student_id} | {score} | {status_emoji} | {allocation_status} |"
                    )
                body_parts.append("")

        # Exception Handling
        if distribution.exceptions and len(distribution.exceptions) > 0:
            body_parts.append("## Exceptions and Special Cases")
            for exception in distribution.exceptions:
                body_parts.append(f"- {exception}")
            body_parts.append("")

        # Algorithm Details
        body_parts.append("## Algorithm Details")
        if distribution.scoring_weights:
            body_parts.append("### Scoring Weights Used")
            for weight_name, weight_value in distribution.scoring_weights.items():
                body_parts.append(f"- {weight_name}: {weight_value}")
            body_parts.append("")

        if distribution.distribution_rules:
            body_parts.append("### Distribution Rules Applied")
            for rule_name, rule_value in distribution.distribution_rules.items():
                body_parts.append(f"- {rule_name}: {rule_value}")
            body_parts.append("")

        # Footer
        body_parts.append("---")
        body_parts.append("*This issue was automatically generated by the Scholarship Management System.*")
        body_parts.append(f"*Distribution ID: {distribution.id}*")

        return "\n".join(body_parts)

    def _generate_issue_labels(self, distribution: QuotaDistribution) -> List[str]:
        """Generate appropriate labels for the GitHub issue"""
        labels = [
            "scholarship-distribution",
            f"AY{distribution.academic_year}",
            "automated-report",
        ]

        if distribution.semester:
            labels.append(f"semester-{distribution.semester.lower()}")

        # Add status labels based on success rate
        if distribution.success_rate >= 90:
            labels.append("high-success-rate")
        elif distribution.success_rate >= 70:
            labels.append("moderate-success-rate")
        else:
            labels.append("low-success-rate")

        return labels

    def _generate_issue_number(self) -> int:
        """Generate a simulated issue number"""
        import random

        return random.randint(1000, 9999)

    async def create_ranking_summary_issue(self, ranking: CollegeRanking) -> Dict[str, Any]:
        """Create a GitHub issue with ranking summary (before distribution)"""

        issue_title = f"College Ranking Summary - {ranking.ranking_name}"
        issue_body = await self._generate_ranking_summary_body(ranking)
        labels = [
            "college-ranking",
            "pre-distribution",
            f"AY{ranking.academic_year}",
            f"sub-type-{ranking.sub_type_code}",
        ]

        # Simulate GitHub issue creation
        simulated_issue = {
            "number": self._generate_issue_number(),
            "url": f"https://github.com/{self.github_repo}/issues/{self._generate_issue_number()}",
            "title": issue_title,
            "body": issue_body,
            "state": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Update ranking record
        ranking.github_issue_url = simulated_issue["url"]
        await self.db.commit()

        return simulated_issue

    async def _generate_ranking_summary_body(self, ranking: CollegeRanking) -> str:
        """Generate ranking summary body"""

        body_parts = []

        # Header
        body_parts.append("# College Ranking Summary")
        body_parts.append(f"**Ranking:** {ranking.ranking_name}")
        body_parts.append(f"**Sub-Type:** {ranking.sub_type_code}")
        body_parts.append(f"**Academic Year:** {ranking.academic_year}")
        if ranking.semester:
            body_parts.append(f"**Semester:** {ranking.semester}")
        body_parts.append(f"**Created:** {ranking.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        body_parts.append("")

        # Summary
        body_parts.append("## Ranking Summary")
        body_parts.append(f"- **Total Applications:** {ranking.total_applications}")
        body_parts.append(f"- **Available Quota:** {ranking.total_quota}")
        body_parts.append(f"- **Status:** {ranking.ranking_status}")
        body_parts.append(f"- **Finalized:** {'Yes' if ranking.is_finalized else 'No'}")
        body_parts.append("")

        # Get ranking items
        stmt = (
            select(CollegeRankingItem)
            .options(
                selectinload(CollegeRankingItem.application),
                selectinload(CollegeRankingItem.college_review),
            )
            .where(CollegeRankingItem.ranking_id == ranking.id)
            .order_by(CollegeRankingItem.rank_position)
        )

        result = await self.db.execute(stmt)
        ranking_items = result.scalars().all()

        if ranking_items:
            body_parts.append("## Current Ranking Order")
            body_parts.append("| Rank | Student | Student ID | Score | Review Status |")
            body_parts.append("|------|---------|------------|-------|---------------|")

            for item in ranking_items:
                student_name = (
                    item.application.student_data.get("cname", "N/A") if item.application.student_data else "N/A"
                )
                student_id = (
                    item.application.student_data.get("stdNo", "N/A") if item.application.student_data else "N/A"
                )
                score = f"{item.total_score:.2f}" if item.total_score else "N/A"
                review_status = item.college_review.review_status if item.college_review else "N/A"

                body_parts.append(
                    f"| {item.rank_position} | {student_name} | {student_id} | {score} | {review_status} |"
                )

        body_parts.append("")
        body_parts.append("---")
        body_parts.append("*This ranking summary was automatically generated.*")
        body_parts.append(f"*Ranking ID: {ranking.id}*")

        return "\n".join(body_parts)

    async def update_issue_with_distribution_results(
        self, issue_number: int, distribution: QuotaDistribution
    ) -> Dict[str, Any]:
        """Update an existing GitHub issue with distribution results"""

        # In a real implementation, this would update the GitHub issue
        # For now, we'll simulate the update

        update_comment = f"""
## Distribution Results Update

Distribution has been executed successfully!

**Final Results:**
- Total Allocated: {distribution.total_allocated}
- Success Rate: {distribution.success_rate:.1f}%
- Execution Time: {distribution.executed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}

Distribution ID: {distribution.id}
"""

        return {
            "comment_added": True,
            "comment_body": update_comment,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


# Utility functions for GitHub integration
def format_distribution_for_export(distribution: QuotaDistribution) -> Dict[str, Any]:
    """Format distribution data for export/reporting"""

    return {
        "distribution_id": distribution.id,
        "distribution_name": distribution.distribution_name,
        "academic_year": distribution.academic_year,
        "semester": distribution.semester,
        "executed_at": distribution.executed_at.isoformat(),
        "total_applications": distribution.total_applications,
        "total_quota": distribution.total_quota,
        "total_allocated": distribution.total_allocated,
        "success_rate": distribution.success_rate,
        "algorithm_version": distribution.algorithm_version,
        "distribution_summary": distribution.distribution_summary,
        "exceptions": distribution.exceptions,
        "github_issue_number": distribution.github_issue_number,
        "github_issue_url": distribution.github_issue_url,
    }


def generate_distribution_csv_content(ranking_items: List[CollegeRankingItem]) -> str:
    """Generate CSV content for distribution results"""

    csv_lines = []
    csv_lines.append("Rank,Student Name,Student ID,Score,Allocated,Status,Allocation Reason")

    for item in sorted(ranking_items, key=lambda x: x.rank_position):
        student_name = item.application.student_data.get("cname", "N/A") if item.application.student_data else "N/A"
        student_id = item.application.student_data.get("stdNo", "N/A") if item.application.student_data else "N/A"
        score = f"{item.total_score:.2f}" if item.total_score else "N/A"
        allocated = "Yes" if item.is_allocated else "No"
        status = item.status
        reason = item.allocation_reason or "N/A"

        csv_lines.append(f"{item.rank_position},{student_name},{student_id},{score},{allocated},{status},{reason}")

    return "\n".join(csv_lines)
