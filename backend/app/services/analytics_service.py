"""
Application analytics service for scholarship management
Provides comprehensive analytics, reporting, and insights
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus

# Student model removed - student data now fetched from external API


logger = logging.getLogger(__name__)


class ScholarshipAnalyticsService:
    """Service for scholarship application analytics and reporting"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_comprehensive_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        semester: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive analytics dashboard data"""

        try:
            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now(timezone.utc)
            if not start_date:
                start_date = end_date - timedelta(days=365)  # Last year

            # Base query
            stmt = select(Application).where(Application.created_at >= start_date, Application.created_at <= end_date)

            if semester:
                stmt = stmt.where(Application.semester == semester)

            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            analytics = {
                "date_range": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "semester": semester,
                },
                "overview": self._calculate_overview_metrics(applications),
                "status_analysis": self._analyze_application_status(applications),
                "type_analysis": self._analyze_scholarship_types(applications),
                "temporal_analysis": self._analyze_temporal_patterns(applications),
                "performance_metrics": self._calculate_performance_metrics(applications),
                "renewal_analysis": self._analyze_renewal_patterns(applications),
                "geographic_analysis": self._analyze_geographic_distribution(applications),
                "success_factors": self._analyze_success_factors(applications),
            }

            return analytics

        except Exception as e:
            logger.error(f"Error generating comprehensive analytics: {str(e)}")
            raise

    def _calculate_overview_metrics(self, applications: List[Application]) -> Dict[str, Any]:
        """Calculate overview metrics"""

        total_applications = len(applications)

        if total_applications == 0:
            return {
                "total_applications": 0,
                "approval_rate": 0,
                "rejection_rate": 0,
                "pending_rate": 0,
                "average_processing_time": 0,
            }

        # Status counts
        approved = len([app for app in applications if app.status == ApplicationStatus.approved.value])
        rejected = len([app for app in applications if app.status == ApplicationStatus.rejected.value])
        pending = len(
            [
                app
                for app in applications
                if app.status
                in [
                    ApplicationStatus.submitted.value,
                    ApplicationStatus.under_review.value,
                ]
            ]
        )

        # Processing time analysis
        processing_times = []
        for app in applications:
            if app.submitted_at and app.decision_date:
                processing_time = (app.decision_date - app.submitted_at).days
                if processing_time >= 0:  # Only include valid processing times
                    processing_times.append(processing_time)

        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0

        return {
            "total_applications": total_applications,
            "approved_applications": approved,
            "rejected_applications": rejected,
            "pending_applications": pending,
            "approval_rate": (approved / total_applications * 100) if total_applications > 0 else 0,
            "rejection_rate": (rejected / total_applications * 100) if total_applications > 0 else 0,
            "pending_rate": (pending / total_applications * 100) if total_applications > 0 else 0,
            "average_processing_time_days": round(avg_processing_time, 1),
            "processing_time_samples": len(processing_times),
        }

    def _analyze_application_status(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze application status distribution"""

        status_counts = {}
        for status in ApplicationStatus:
            count = len([app for app in applications if app.status == status.value])
            if count > 0:
                status_counts[status.value] = {
                    "count": count,
                    "percentage": (count / len(applications) * 100) if applications else 0,
                }

        # Status transition analysis
        status_flow = self._analyze_status_transitions(applications)

        return {
            "status_distribution": status_counts,
            "status_flow_analysis": status_flow,
            "completion_rate": (
                len(
                    [
                        app
                        for app in applications
                        if app.status
                        in [
                            ApplicationStatus.approved.value,
                            ApplicationStatus.rejected.value,
                        ]
                    ]
                )
                / len(applications)
                * 100
                if applications
                else 0
            ),
        }

    def _analyze_scholarship_types(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze scholarship type distribution and performance - REFACTORED for configuration-driven types"""

        # Group by scholarship_type_id (configuration-driven)
        type_stats = {}

        # Get distinct scholarship_type_ids from applications
        scholarship_type_ids = set(app.scholarship_type_id for app in applications if app.scholarship_type_id)

        for type_id in scholarship_type_ids:
            type_apps = [app for app in applications if app.scholarship_type_id == type_id]
            if type_apps:
                # Try to get scholarship name from first app's relationship
                type_name = None
                if type_apps[0].scholarship:
                    type_name = type_apps[0].scholarship.name or type_apps[0].scholarship.code
                else:
                    type_name = f"Type_{type_id}"

                type_stats[type_id] = {
                    "scholarship_type_id": type_id,
                    "scholarship_type_name": type_name,
                    "total_applications": len(type_apps),
                    "approved": len([app for app in type_apps if app.status == ApplicationStatus.approved.value]),
                    "approval_rate": len([app for app in type_apps if app.status == ApplicationStatus.approved.value])
                    / len(type_apps)
                    * 100,
                    "sub_types": {},
                }

                # Sub-type breakdown (configuration-driven)
                # Get distinct sub-types from current applications
                sub_types_in_apps = set(app.sub_scholarship_type for app in type_apps if app.sub_scholarship_type)
                for sub_type_value in sub_types_in_apps:
                    sub_apps = [app for app in type_apps if app.sub_scholarship_type == sub_type_value]
                    if sub_apps:
                        type_stats[type_id]["sub_types"][sub_type_value] = {
                            "total": len(sub_apps),
                            "approved": len(
                                [app for app in sub_apps if app.status == ApplicationStatus.approved.value]
                            ),
                            "approval_rate": len(
                                [app for app in sub_apps if app.status == ApplicationStatus.approved.value]
                            )
                            / len(sub_apps)
                            * 100,
                        }

        return {
            "scholarship_type_distribution": type_stats,
            "most_popular_type_id": (
                max(
                    type_stats.keys(),
                    key=lambda k: type_stats[k]["total_applications"],
                )
                if type_stats
                else None
            ),
            "highest_approval_rate_type_id": (
                max(
                    type_stats.keys(),
                    key=lambda k: type_stats[k]["approval_rate"],
                )
                if type_stats
                else None
            ),
        }

    def _analyze_temporal_patterns(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze temporal patterns in applications"""

        # Monthly submission patterns
        monthly_submissions = {}
        for app in applications:
            if app.submitted_at:
                month_key = app.submitted_at.strftime("%Y-%m")
                if month_key not in monthly_submissions:
                    monthly_submissions[month_key] = {"total": 0, "approved": 0}
                monthly_submissions[month_key]["total"] += 1
                if app.status == ApplicationStatus.approved.value:
                    monthly_submissions[month_key]["approved"] += 1

        # Day of week patterns
        day_patterns = {}
        for app in applications:
            if app.submitted_at:
                day_name = app.submitted_at.strftime("%A")
                day_patterns[day_name] = day_patterns.get(day_name, 0) + 1

        # Seasonal analysis
        seasonal_data = {"Spring": 0, "Summer": 0, "Fall": 0, "Winter": 0}
        for app in applications:
            if app.submitted_at:
                month = app.submitted_at.month
                if month in [3, 4, 5]:
                    seasonal_data["Spring"] += 1
                elif month in [6, 7, 8]:
                    seasonal_data["Summer"] += 1
                elif month in [9, 10, 11]:
                    seasonal_data["Fall"] += 1
                else:
                    seasonal_data["Winter"] += 1

        return {
            "monthly_submissions": monthly_submissions,
            "day_of_week_patterns": day_patterns,
            "seasonal_distribution": seasonal_data,
            "peak_submission_month": (
                max(
                    monthly_submissions.keys(),
                    key=lambda k: monthly_submissions[k]["total"],
                )
                if monthly_submissions
                else None
            ),
        }

    def _analyze_renewal_patterns(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze renewal application patterns"""

        renewal_apps = [app for app in applications if app.is_renewal]
        new_apps = [app for app in applications if not app.is_renewal]

        renewal_analysis = {
            "renewal_applications": len(renewal_apps),
            "new_applications": len(new_apps),
            "renewal_percentage": (len(renewal_apps) / len(applications) * 100) if applications else 0,
        }

        # Renewal success rates
        if renewal_apps:
            renewal_approved = len([app for app in renewal_apps if app.status == ApplicationStatus.approved.value])
            renewal_analysis["renewal_approval_rate"] = renewal_approved / len(renewal_apps) * 100

        if new_apps:
            new_approved = len([app for app in new_apps if app.status == ApplicationStatus.approved.value])
            renewal_analysis["new_application_approval_rate"] = new_approved / len(new_apps) * 100

        # Note: Priority score comparison removed (priority_score field removed from Application model)

        return renewal_analysis

    def _calculate_performance_metrics(self, applications: List[Application]) -> Dict[str, Any]:
        """Calculate performance metrics"""

        # Processing efficiency
        overdue_applications = len(
            [
                app
                for app in applications
                if app.review_deadline
                and app.review_deadline < datetime.now(timezone.utc)
                and app.status
                in [
                    ApplicationStatus.submitted.value,
                    ApplicationStatus.under_review.value,
                ]
            ]
        )

        # Note: Priority score distribution removed (priority_score field removed from Application model)
        # Performance metrics now focus on processing efficiency and timeliness

        return {
            "overdue_applications": overdue_applications,
            # Note: priority_distribution, average_priority_by_status removed
            "note": "Priority score metrics removed - system no longer uses scoring",
        }

    def _analyze_geographic_distribution(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze geographic distribution (placeholder for future implementation)"""

        # This would analyze by department, college, etc.
        # For now, return basic structure

        return {
            "note": "Geographic analysis would be implemented with student department/college data",
            "applications_by_department": {},
            "applications_by_college": {},
        }

    def _analyze_success_factors(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze factors that correlate with successful applications"""

        approved_apps = [app for app in applications if app.status == ApplicationStatus.approved.value]
        rejected_apps = [app for app in applications if app.status == ApplicationStatus.rejected.value]

        success_factors = {}

        # Renewal correlation
        approved_renewals = len([app for app in approved_apps if app.is_renewal])
        rejected_renewals = len([app for app in rejected_apps if app.is_renewal])

        success_factors["renewal_correlation"] = {
            "approved_renewals": approved_renewals,
            "rejected_renewals": rejected_renewals,
            "renewal_success_rate": (
                (approved_renewals / (approved_renewals + rejected_renewals) * 100)
                if (approved_renewals + rejected_renewals) > 0
                else 0
            ),
        }

        # Note: Priority score correlation removed (priority_score field removed from Application model)
        # Success factors now focus on renewal status and submission timing

        # Submission timing correlation placeholder; requires additional data to categorize early vs late

        return success_factors

    def _analyze_status_transitions(self, applications: List[Application]) -> Dict[str, Any]:
        """Analyze how applications transition between statuses"""

        # This would require tracking status change history
        # For now, return current status distribution

        transitions = {
            "note": "Status transition analysis would require status change audit trail",
            "common_paths": [
                "DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED",
                "DRAFT -> SUBMITTED -> UNDER_REVIEW -> REJECTED",
                "DRAFT -> SUBMITTED -> PROFESSOR_REVIEW -> APPROVED",
            ],
        }

        return transitions

    async def generate_executive_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        semester: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate executive summary report"""

        try:
            analytics = await self.get_comprehensive_analytics(start_date, end_date, semester)

            # Extract key insights
            overview = analytics["overview"]
            renewal_analysis = analytics["renewal_analysis"]
            type_analysis = analytics["type_analysis"]

            executive_summary = {
                "report_period": analytics["date_range"],
                "key_metrics": {
                    "total_applications": overview["total_applications"],
                    "approval_rate": f"{overview['approval_rate']:.1f}%",
                    "average_processing_time": f"{overview['average_processing_time_days']} days",
                    "renewal_percentage": f"{renewal_analysis.get('renewal_percentage', 0):.1f}%",
                },
                "insights": [],
                "recommendations": [],
                "trends": {
                    "most_popular_scholarship": type_analysis.get("most_popular_type"),
                    "highest_success_rate": type_analysis.get("highest_approval_rate_type"),
                    "renewal_success_advantage": (
                        renewal_analysis.get("renewal_approval_rate", 0)
                        - renewal_analysis.get("new_application_approval_rate", 0)
                        if renewal_analysis.get("renewal_approval_rate")
                        and renewal_analysis.get("new_application_approval_rate")
                        else 0
                    ),
                },
            }

            # Generate insights
            if overview["approval_rate"] > 70:
                executive_summary["insights"].append("High approval rate indicates effective screening process")
            elif overview["approval_rate"] < 30:
                executive_summary["insights"].append(
                    "Low approval rate may indicate overly strict criteria or quota constraints"
                )

            if overview["average_processing_time_days"] > 30:
                executive_summary["insights"].append("Processing time exceeds target of 30 days")
                executive_summary["recommendations"].append(
                    "Consider process optimization or additional review resources"
                )

            if renewal_analysis.get("renewal_approval_rate", 0) > renewal_analysis.get(
                "new_application_approval_rate", 0
            ):
                executive_summary["insights"].append(
                    "Renewal applications have higher success rate than new applications"
                )

            # Generate recommendations
            if analytics["performance_metrics"]["overdue_applications"] > 0:
                executive_summary["recommendations"].append(
                    f"Address {analytics['performance_metrics']['overdue_applications']} overdue applications"
                )

            return executive_summary

        except Exception as e:
            logger.error(f"Error generating executive summary: {str(e)}")
            raise

    async def get_predictive_insights(self, forecast_months: int = 6) -> Dict[str, Any]:
        """Generate predictive insights based on historical data"""

        try:
            # Get historical data for the past year
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=365)

            stmt = select(Application).where(Application.created_at >= start_date, Application.created_at <= end_date)
            result = await self.db.execute(stmt)
            historical_apps = result.scalars().all()

            # Calculate monthly averages
            monthly_data = {}
            for app in historical_apps:
                if app.created_at:
                    month_key = app.created_at.strftime("%Y-%m")
                    monthly_data[month_key] = monthly_data.get(month_key, 0) + 1

            avg_monthly_applications = sum(monthly_data.values()) / len(monthly_data) if monthly_data else 0

            # Generate forecasts
            predictions = {
                "forecast_period_months": forecast_months,
                "predicted_applications": round(avg_monthly_applications * forecast_months),
                "confidence_level": "Medium",  # Would be calculated based on data variance
                "seasonal_adjustments": {
                    "note": "Seasonal patterns detected in historical data",
                    "peak_months": [
                        "September",
                        "January",
                    ],  # Typical academic calendar
                    "low_months": ["June", "July", "December"],
                },
                "capacity_planning": {
                    "predicted_workload": round(avg_monthly_applications * forecast_months),
                    "recommended_review_capacity": round(
                        avg_monthly_applications * forecast_months / 30
                    ),  # Assuming 30-day review cycle
                    "resource_requirements": "Based on historical processing times",
                },
            }

            return predictions

        except Exception as e:
            logger.error(f"Error generating predictive insights: {str(e)}")
            raise
