"""
College Review Service

This service handles college-level review operations including:
- Application ranking and scoring
- Quota-based distribution
- Review workflow management
- Integration with GitHub issue creation
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.orm import selectinload, joinedload

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeReview, CollegeRanking, CollegeRankingItem, QuotaDistribution
from app.models.scholarship import ScholarshipType, ScholarshipConfiguration
from app.models.user import User, UserRole
from app.models.enums import Semester
from app.core.exceptions import BusinessLogicError, NotFoundError


class CollegeReviewService:
    """Service for managing college-level reviews and rankings"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_or_update_review(
        self,
        application_id: int,
        reviewer_id: int,
        review_data: Dict[str, Any]
    ) -> CollegeReview:
        """Create or update a college review for an application"""
        
        # Check if review already exists
        stmt = select(CollegeReview).where(CollegeReview.application_id == application_id)
        result = await self.db.execute(stmt)
        existing_review = result.scalar_one_or_none()
        
        # Verify application exists and is in reviewable state
        app_stmt = select(Application).where(Application.id == application_id)
        app_result = await self.db.execute(app_stmt)
        application = app_result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError("Application", str(application_id))
        
        if application.status not in ['recommended', 'under_review']:
            raise BusinessLogicError(f"Application {application_id} is not in reviewable state")
        
        # Calculate scores if not provided
        if not review_data.get('ranking_score'):
            ranking_score = self._calculate_ranking_score(review_data)
            review_data['ranking_score'] = ranking_score
        
        if existing_review:
            # Update existing review
            for key, value in review_data.items():
                if hasattr(existing_review, key):
                    setattr(existing_review, key, value)
            
            existing_review.updated_at = datetime.now(timezone.utc)
            existing_review.reviewed_at = datetime.now(timezone.utc)
            existing_review.review_status = 'completed'
            
            college_review = existing_review
        else:
            # Create new review
            college_review = CollegeReview(
                application_id=application_id,
                reviewer_id=reviewer_id,
                review_started_at=datetime.now(timezone.utc),
                reviewed_at=datetime.now(timezone.utc),
                review_status='completed',
                **review_data
            )
            self.db.add(college_review)
        
        # Update application's college review fields
        application.college_ranking_score = college_review.ranking_score
        application.status = 'college_reviewed'
        
        await self.db.commit()
        await self.db.refresh(college_review)
        
        return college_review
    
    def _calculate_ranking_score(self, review_data: Dict[str, Any]) -> float:
        """Calculate overall ranking score based on component scores"""
        
        # Default scoring weights
        weights = {
            'academic': 0.30,
            'professor_review': 0.40,
            'college_criteria': 0.20,
            'special_circumstances': 0.10
        }
        
        # Use custom weights if provided
        if 'scoring_weights' in review_data:
            weights.update(review_data['scoring_weights'])
        
        # Extract component scores
        scores = {
            'academic': review_data.get('academic_score', 0),
            'professor_review': review_data.get('professor_review_score', 0),
            'college_criteria': review_data.get('college_criteria_score', 0),
            'special_circumstances': review_data.get('special_circumstances_score', 0)
        }
        
        # Calculate weighted total
        total_score = sum(scores[key] * weights[key] for key in scores)
        return round(total_score, 2)
    
    async def get_applications_for_review(
        self,
        scholarship_type_id: Optional[int] = None,
        sub_type: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        academic_year: Optional[int] = None,
        semester: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get applications that are ready for college review"""
        
        # Base query for applications in reviewable state
        stmt = select(Application).options(
            selectinload(Application.scholarship_type_ref),
            # selectinload(Application.college_review),  # Temporarily disabled due to circular dependency
            selectinload(Application.professor_reviews)
        ).where(
            or_(
                Application.status == 'recommended',
                Application.status == 'under_review'
            )
        )
        
        # Apply filters
        if scholarship_type_id:
            stmt = stmt.where(Application.scholarship_type_id == scholarship_type_id)
        
        if sub_type:
            stmt = stmt.where(Application.sub_scholarship_type == sub_type)
        
        if academic_year:
            stmt = stmt.where(Application.academic_year == academic_year)
        
        if semester:
            stmt = stmt.where(Application.semester == semester)
        
        # Order by submission date (FIFO)
        stmt = stmt.order_by(asc(Application.submitted_at))
        
        result = await self.db.execute(stmt)
        applications = result.scalars().all()
        
        # Get college review data for all applications
        application_ids = [app.id for app in applications]
        college_reviews_stmt = select(CollegeReview).where(
            CollegeReview.application_id.in_(application_ids)
        )
        college_reviews_result = await self.db.execute(college_reviews_stmt)
        college_reviews = college_reviews_result.scalars().all()
        
        # Create lookup dictionary for college reviews
        college_review_lookup = {review.application_id: review for review in college_reviews}
        
        # Format response with additional review information
        formatted_applications = []
        for app in applications:
            # Get college review if exists
            college_review = college_review_lookup.get(app.id)
            
            app_data = {
                'id': app.id,
                'app_id': app.app_id,
                'student_name': app.student_data.get('cname') if app.student_data else 'N/A',
                'student_no': app.student_data.get('stdNo') if app.student_data else 'N/A',
                'scholarship_type': app.main_scholarship_type,
                'sub_type': app.sub_scholarship_type,
                'academic_year': app.academic_year,
                'semester': app.semester.value if app.semester else None,
                'submitted_at': app.submitted_at,
                'current_status': app.status,
                'professor_review_completed': len(app.professor_reviews) > 0,
                'college_review_completed': college_review is not None,
                'college_review_score': college_review.ranking_score if college_review else None
            }
            formatted_applications.append(app_data)
        
        return formatted_applications
    
    async def create_ranking(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        creator_id: int,
        ranking_name: Optional[str] = None
    ) -> CollegeRanking:
        """Create a new ranking for a scholarship sub-type"""
        
        # Check if ranking already exists
        existing_stmt = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.sub_type_code == sub_type_code,
                CollegeRanking.academic_year == academic_year,
                CollegeRanking.semester == semester
            )
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_ranking = existing_result.scalar_one_or_none()
        
        if existing_ranking and not existing_ranking.is_finalized:
            return existing_ranking
        
        # Get applications for this sub-type that have college reviews
        # First get all applications for the sub-type
        apps_stmt = select(Application).where(
            and_(
                Application.scholarship_type_id == scholarship_type_id,
                Application.sub_scholarship_type == sub_type_code,
                Application.academic_year == academic_year,
                Application.semester == semester
            )
        )
        
        # Get college reviews for this sub-type
        college_reviews_stmt = select(CollegeReview).join(Application).where(
            and_(
                Application.scholarship_type_id == scholarship_type_id,
                Application.sub_scholarship_type == sub_type_code,
                Application.academic_year == academic_year,
                Application.semester == semester
            )
        )
        apps_result = await self.db.execute(apps_stmt)
        applications = apps_result.scalars().all()
        
        # Get college reviews for these applications
        college_reviews_result = await self.db.execute(college_reviews_stmt)
        college_reviews = college_reviews_result.scalars().all()
        
        # Filter applications to only those that have college reviews
        applications_with_reviews = []
        college_review_lookup = {review.application_id: review for review in college_reviews}
        
        for app in applications:
            if app.id in college_review_lookup:
                applications_with_reviews.append((app, college_review_lookup[app.id]))
        
        # Get quota information from configuration
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester,
                ScholarshipConfiguration.is_active == True
            )
        )
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        total_quota = None
        if config and config.has_quota_limit:
            total_quota = config.get_sub_type_total_quota(sub_type_code)
        
        # Create ranking
        ranking = CollegeRanking(
            scholarship_type_id=scholarship_type_id,
            sub_type_code=sub_type_code,
            academic_year=academic_year,
            semester=semester,
            ranking_name=ranking_name or f"{sub_type_code} Ranking AY{academic_year}",
            total_applications=len(applications_with_reviews),
            total_quota=total_quota,
            created_by=creator_id
        )
        
        self.db.add(ranking)
        await self.db.commit()
        await self.db.refresh(ranking)
        
        # Create ranking items sorted by college review score
        applications_with_reviews.sort(key=lambda x: x[1].ranking_score, reverse=True)
        
        for rank_position, (app, college_review) in enumerate(applications_with_reviews, 1):
            ranking_item = CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                college_review_id=college_review.id,
                rank_position=rank_position,
                total_score=college_review.ranking_score
            )
            self.db.add(ranking_item)
        
        await self.db.commit()
        
        return ranking
    
    async def get_ranking(self, ranking_id: int) -> Optional[CollegeRanking]:
        """Get a ranking with all its items"""
        
        stmt = select(CollegeRanking).options(
            selectinload(CollegeRanking.items)
            # selectinload(CollegeRankingItem.application),  # Disabled due to circular dependency
            # selectinload(CollegeRankingItem.college_review),  # Disabled due to circular dependency
            # selectinload(CollegeRanking.scholarship_type)  # Disabled due to circular dependency
        ).where(CollegeRanking.id == ranking_id)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_ranking_order(
        self,
        ranking_id: int,
        new_order: List[Dict[str, Any]]
    ) -> CollegeRanking:
        """Update the ranking order of applications"""
        
        ranking = await self.get_ranking(ranking_id)
        if not ranking:
            raise NotFoundError("Ranking", str(ranking_id))
        
        if ranking.is_finalized:
            raise BusinessLogicError("Cannot modify finalized ranking")
        
        # Update rank positions
        for order_item in new_order:
            item_id = order_item['item_id']
            new_position = order_item['position']
            
            # Find the ranking item
            ranking_item = next(
                (item for item in ranking.items if item.id == item_id),
                None
            )
            
            if ranking_item:
                ranking_item.rank_position = new_position
                
                # Update application's ranking position
                application = ranking_item.application
                application.final_ranking_position = new_position
        
        ranking.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        return ranking
    
    async def execute_quota_distribution(
        self,
        ranking_id: int,
        executor_id: int,
        distribution_rules: Optional[Dict[str, Any]] = None
    ) -> QuotaDistribution:
        """Execute quota-based distribution for a ranking"""
        
        ranking = await self.get_ranking(ranking_id)
        if not ranking:
            raise NotFoundError("Ranking", str(ranking_id))
        
        if ranking.distribution_executed:
            raise BusinessLogicError("Distribution already executed for this ranking")
        
        # Sort ranking items by position
        sorted_items = sorted(ranking.items, key=lambda x: x.rank_position)
        
        # Apply quota allocation
        allocated_count = 0
        allocation_results = []
        
        for item in sorted_items:
            if ranking.total_quota and allocated_count >= ranking.total_quota:
                # No more quota available
                item.is_allocated = False
                item.status = 'rejected'
                item.allocation_reason = 'Quota exceeded'
                
                # Update application status
                item.application.quota_allocation_status = 'rejected'
                item.application.status = 'rejected'
            else:
                # Allocate quota
                item.is_allocated = True
                item.status = 'allocated'
                item.allocation_reason = 'Within quota limit'
                allocated_count += 1
                
                # Update application status
                item.application.quota_allocation_status = 'allocated'
                item.application.status = 'approved'
            
            allocation_results.append({
                'application_id': item.application_id,
                'rank_position': item.rank_position,
                'is_allocated': item.is_allocated,
                'status': item.status
            })
        
        # Update ranking
        ranking.allocated_count = allocated_count
        ranking.distribution_executed = True
        ranking.distribution_date = datetime.now(timezone.utc)
        
        # Create distribution record
        distribution = QuotaDistribution(
            distribution_name=f"Distribution for {ranking.ranking_name}",
            academic_year=ranking.academic_year,
            semester=ranking.semester,
            total_applications=ranking.total_applications,
            total_quota=ranking.total_quota or ranking.total_applications,
            total_allocated=allocated_count,
            algorithm_version="v1.0",
            distribution_rules=distribution_rules or {},
            distribution_summary={
                ranking.sub_type_code: {
                    'total_applications': ranking.total_applications,
                    'total_quota': ranking.total_quota,
                    'allocated': allocated_count,
                    'rejected': ranking.total_applications - allocated_count
                }
            },
            executed_by=executor_id
        )
        
        self.db.add(distribution)
        await self.db.commit()
        await self.db.refresh(distribution)
        
        return distribution
    
    async def finalize_ranking(
        self,
        ranking_id: int,
        finalizer_id: int
    ) -> CollegeRanking:
        """Finalize a ranking (makes it read-only)"""
        
        ranking = await self.get_ranking(ranking_id)
        if not ranking:
            raise NotFoundError("Ranking", str(ranking_id))
        
        if ranking.is_finalized:
            raise BusinessLogicError("Ranking is already finalized")
        
        ranking.is_finalized = True
        ranking.finalized_at = datetime.now(timezone.utc)
        ranking.finalized_by = finalizer_id
        ranking.ranking_status = 'finalized'
        
        await self.db.commit()
        
        return ranking
    
    async def get_quota_status(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get quota status for a scholarship type"""
        
        # Get configuration
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester,
                ScholarshipConfiguration.is_active == True
            )
        )
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            return {"error": "No active configuration found"}
        
        # Get application counts by sub-type
        apps_stmt = select(
            Application.sub_scholarship_type,
            func.count(Application.id).label('total'),
            func.sum(
                case([(Application.quota_allocation_status == 'allocated', 1)], else_=0)
            ).label('allocated')
        ).where(
            and_(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.semester == semester
            )
        ).group_by(Application.sub_scholarship_type)
        
        apps_result = await self.db.execute(apps_stmt)
        app_counts = apps_result.all()
        
        # Build quota status
        quota_status = {
            'total_quota': config.total_quota,
            'has_quota_limit': config.has_quota_limit,
            'has_college_quota': config.has_college_quota,
            'sub_types': {}
        }
        
        for sub_type, total, allocated in app_counts:
            sub_quota = config.get_sub_type_total_quota(sub_type) if config.has_quota_limit else None
            
            quota_status['sub_types'][sub_type] = {
                'total_applications': total,
                'allocated': allocated or 0,
                'quota': sub_quota,
                'remaining': (sub_quota - (allocated or 0)) if sub_quota else None,
                'utilization_rate': ((allocated or 0) / sub_quota * 100) if sub_quota else None
            }
        
        return quota_status


class QuotaDistributionService:
    """Service specifically for handling quota distribution algorithms"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def distribute_by_ranking(
        self,
        applications: List[Application],
        total_quota: int,
        distribution_rules: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Distribute quota based on ranking order"""
        
        # Sort applications by ranking score (descending)
        sorted_apps = sorted(
            applications,
            key=lambda x: (
                x.college_ranking_score or 0,
                -(x.submitted_at.timestamp() if x.submitted_at else 0)  # Tie-breaker: earlier submission
            ),
            reverse=True
        )
        
        # Allocate quota
        results = []
        for i, app in enumerate(sorted_apps):
            is_allocated = i < total_quota
            
            result = {
                'application_id': app.id,
                'rank_position': i + 1,
                'is_allocated': is_allocated,
                'ranking_score': app.college_ranking_score,
                'allocation_reason': 'Within quota' if is_allocated else 'Quota exceeded'
            }
            results.append(result)
        
        return results
    
    async def distribute_by_sub_type_matrix(
        self,
        applications: List[Application],
        quota_matrix: Dict[str, Dict[str, int]],  # {sub_type: {college: quota}}
        distribution_rules: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Distribute quota using sub-type and college matrix"""
        
        # Group applications by sub-type and college
        grouped_apps = {}
        for app in applications:
            sub_type = app.sub_scholarship_type
            college = app.student_data.get('college_code') if app.student_data else 'unknown'
            
            if sub_type not in grouped_apps:
                grouped_apps[sub_type] = {}
            if college not in grouped_apps[sub_type]:
                grouped_apps[sub_type][college] = []
            
            grouped_apps[sub_type][college].append(app)
        
        # Distribute within each group
        results = []
        for sub_type, colleges in grouped_apps.items():
            sub_type_quota = quota_matrix.get(sub_type, {})
            
            for college, college_apps in colleges.items():
                college_quota = sub_type_quota.get(college, 0)
                
                # Sort applications within this group
                sorted_apps = sorted(
                    college_apps,
                    key=lambda x: (
                        x.college_ranking_score or 0,
                        -(x.submitted_at.timestamp() if x.submitted_at else 0)
                    ),
                    reverse=True
                )
                
                # Allocate quota for this group
                for i, app in enumerate(sorted_apps):
                    is_allocated = i < college_quota
                    
                    result = {
                        'application_id': app.id,
                        'sub_type': sub_type,
                        'college': college,
                        'rank_position': i + 1,
                        'is_allocated': is_allocated,
                        'ranking_score': app.college_ranking_score,
                        'quota_available': college_quota,
                        'allocation_reason': f'Within {sub_type}-{college} quota' if is_allocated else f'{sub_type}-{college} quota exceeded'
                    }
                    results.append(result)
        
        return results