"""
Review Service

統一審查服務，處理所有角色的審查邏輯
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.application import Application
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.user import User


class ReviewService:
    """統一審查服務"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_subtype_cumulative_status(self, application_id: int) -> Dict[str, Dict[str, Any]]:
        """
        計算每個子項目的累積狀態

        Args:
            application_id: 申請 ID

        Returns:
            {
                "nstc": {
                    "status": "rejected",  # approved | rejected | pending
                    "rejected_by": {
                        "role": "professor",
                        "name": "王小明",
                        "reviewed_at": "2025-01-15 14:30:00"
                    },
                    "comments": "研究計畫不符合要求"
                },
                "moe_1w": {
                    "status": "approved",
                    "rejected_by": None,
                    "comments": None
                }
            }
        """
        # 動態導入避免循環依賴
        from app.models.review import ApplicationReview

        # 查詢所有審查記錄（按時間排序）
        stmt = (
            select(ApplicationReview)
            .where(ApplicationReview.application_id == application_id)
            .options(joinedload(ApplicationReview.reviewer), joinedload(ApplicationReview.items))
            .order_by(ApplicationReview.created_at)
        )
        result = await self.db.execute(stmt)
        reviews = result.unique().scalars().all()

        # 計算每個子項目的累積狀態
        subtype_status = {}

        for review in reviews:
            for item in review.items:
                code = item.sub_type_code

                # 初始化
                if code not in subtype_status:
                    subtype_status[code] = {
                        "status": "pending",
                        "rejected_by": None,
                        "comments": None,
                    }

                # 如果本次是 reject，且之前未被 reject 過
                if item.recommendation == "reject" and subtype_status[code]["status"] != "rejected":
                    subtype_status[code] = {
                        "status": "rejected",
                        "rejected_by": {
                            "role": review.reviewer.role,
                            "name": review.reviewer.name,
                            "reviewed_at": review.reviewed_at.strftime("%Y-%m-%d %H:%M:%S"),
                        },
                        "comments": item.comments,
                    }
                # 如果本次是 approve，且之前未被 reject 過
                elif item.recommendation == "approve" and subtype_status[code]["status"] == "pending":
                    subtype_status[code]["status"] = "approved"

        return subtype_status

    async def get_reviewable_subtypes(self, application_id: int, current_user_role: str) -> List[str]:
        """
        取得當前審查者可以審查的子項目清單

        規則：
        - 教授：可審查所有子項目
        - 學院：只能審查「教授未拒絕」的子項目
        - 管理員：只能審查「教授和學院都未拒絕」的子項目

        Args:
            application_id: 申請 ID
            current_user_role: 當前使用者角色

        Returns:
            可審查的子項目代碼列表
        """
        # 取得申請的獎學金配置
        stmt = (
            select(Application)
            .where(Application.id == application_id)
            .options(joinedload(Application.scholarship_configuration))
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            return []

        # 取得所有子項目
        all_subtypes = application.scholarship_subtype_list or []
        if not all_subtypes:
            all_subtypes = ["default"]

        # 取得子項目累積狀態
        subtype_status = await self.get_subtype_cumulative_status(application_id)

        # 根據角色過濾
        if current_user_role == "professor":
            # 教授可以審查所有子項目
            return all_subtypes

        elif current_user_role == "college":
            # 學院只能審查「教授未拒絕」的子項目
            return [
                code
                for code in all_subtypes
                if subtype_status.get(code, {}).get("status") != "rejected"
                or subtype_status.get(code, {}).get("rejected_by", {}).get("role") != "professor"
            ]

        elif current_user_role in ["admin", "super_admin"]:
            # 管理員只能審查「教授和學院都未拒絕」的子項目
            return [
                code
                for code in all_subtypes
                if subtype_status.get(code, {}).get("status") != "rejected"
                or subtype_status.get(code, {}).get("rejected_by", {}).get("role") not in ["professor", "college"]
            ]

        return []

    async def calculate_overall_recommendation(self, items: List[Dict[str, Any]]) -> str:
        """
        根據子項目審查結果計算整體建議

        Args:
            items: 子項目審查列表 [{"recommendation": "approve"/"reject", ...}, ...]

        Returns:
            "approve" | "partial_approve" | "reject"
        """
        approve_count = sum(1 for item in items if item.get("recommendation") == "approve")
        reject_count = sum(1 for item in items if item.get("recommendation") == "reject")
        total_count = len(items)

        if approve_count == total_count:
            return "approve"
        elif reject_count == total_count:
            return "reject"
        else:
            return "partial_approve"

    async def combine_comments(self, items: List[Dict[str, Any]]) -> str:
        """
        組合子項目的 comments

        Args:
            items: 子項目審查列表 [{"sub_type_code": "nstc", "recommendation": "approve", "comments": "..."}, ...]

        Returns:
            組合後的評論字串
        """
        comment_lines = []

        for item in items:
            sub_type_code = item.get("sub_type_code", "")
            recommendation = item.get("recommendation", "")
            comments = item.get("comments", "")

            if comments and comments.strip():
                comment_lines.append(f"{sub_type_code}: {comments}")
            elif recommendation == "approve":
                comment_lines.append(f"{sub_type_code}: 同意")

        return "\n".join(comment_lines)

    async def update_decision_reason(
        self,
        application: Application,
        reviewer: User,
        items: List[Dict[str, Any]],
        reviewed_at: datetime,
    ) -> None:
        """
        更新 Application.decision_reason（累加被拒絕的子項目）

        只要該次審查有 reject 任何子項目 → 累加到 decision_reason

        Args:
            application: 申請對象
            reviewer: 審查者
            items: 子項目審查列表
            reviewed_at: 審查時間
        """
        # 篩選被拒絕的子項目
        rejected_items = [item for item in items if item.get("recommendation") == "reject"]

        if not rejected_items:
            return

        # 角色名稱對應
        role_name = {
            "professor": "教授",
            "college": "學院",
            "admin": "管理員",
            "super_admin": "系統管理員",
        }.get(reviewer.role, reviewer.role)

        # 組合被拒絕的子項目評論
        rejected_comments = "\n".join(
            [
                f"- {item.get('sub_type_code')}: {item.get('comments')}"
                for item in rejected_items
                if item.get("comments")
            ]
        )

        # 格式化新原因
        timestamp = reviewed_at.strftime("%Y-%m-%d %H:%M:%S")
        new_reason = f"[{timestamp}] {role_name} ({reviewer.name}):\n{rejected_comments}"

        # 累加到 decision_reason
        if application.decision_reason:
            application.decision_reason += f"\n\n{new_reason}"
        else:
            application.decision_reason = new_reason

    async def update_application_status(self, application_id: int) -> str:
        """
        根據子項目累積狀態更新 Application 狀態

        Args:
            application_id: 申請 ID

        Returns:
            更新後的狀態
        """
        application = await self.db.get(Application, application_id)
        if not application:
            return ""

        # 計算子項目累積狀態
        subtype_status = await self.get_subtype_cumulative_status(application_id)

        if not subtype_status:
            return application.status

        # 計算整體狀態
        all_approved = all(status["status"] == "approved" for status in subtype_status.values())
        all_rejected = all(status["status"] == "rejected" for status in subtype_status.values())

        if all_approved:
            application.status = "approved"
        elif all_rejected:
            application.status = "rejected"
        else:
            # 部分核准
            application.status = "partial_approve"

        return application.status

    async def create_review(
        self,
        application_id: int,
        reviewer_id: int,
        items: List[Dict[str, Any]],
    ) -> "ApplicationReview":
        """
        建立或更新審查記錄（防止重複記錄）

        Args:
            application_id: 申請 ID
            reviewer_id: 審查者 ID
            items: 子項目審查列表 [{"sub_type_code": "nstc", "recommendation": "approve", "comments": "..."}, ...]

        Returns:
            建立或更新的審查記錄
        """
        from sqlalchemy.orm import selectinload

        from app.models.review import ApplicationReview, ApplicationReviewItem

        # 計算整體建議
        overall_recommendation = await self.calculate_overall_recommendation(items)

        # 組合評論
        combined_comments = await self.combine_comments(items)

        # 檢查是否已存在記錄
        stmt = (
            select(ApplicationReview)
            .where(
                ApplicationReview.application_id == application_id,
                ApplicationReview.reviewer_id == reviewer_id,
            )
            .options(selectinload(ApplicationReview.items))
        )
        result = await self.db.execute(stmt)
        existing_review = result.scalar_one_or_none()

        if existing_review:
            # 更新現有記錄
            existing_review.recommendation = overall_recommendation
            existing_review.comments = combined_comments
            existing_review.reviewed_at = datetime.utcnow()

            # 刪除舊的子項目記錄
            for old_item in existing_review.items:
                await self.db.delete(old_item)
            await self.db.flush()

            review = existing_review
        else:
            # 建立新審查記錄
            review = ApplicationReview(
                application_id=application_id,
                reviewer_id=reviewer_id,
                recommendation=overall_recommendation,
                comments=combined_comments,
                reviewed_at=datetime.utcnow(),
            )
            self.db.add(review)

        await self.db.flush()  # 取得 review.id

        # 建立新的子項目審查記錄
        for item in items:
            review_item = ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=item["sub_type_code"],
                recommendation=item["recommendation"],
                comments=item.get("comments"),
            )
            self.db.add(review_item)

        await self.db.commit()
        await self.db.refresh(review)

        # 取得審查者資訊
        reviewer = await self.db.get(User, reviewer_id)

        # 更新 decision_reason
        application = await self.db.get(Application, application_id)
        if application and reviewer:
            await self.update_decision_reason(application, reviewer, items, review.reviewed_at)

        # 更新申請狀態
        await self.update_application_status(application_id)
        await self.db.commit()

        return review

    async def get_review_by_id(self, review_id: int) -> Optional["ApplicationReview"]:
        """
        根據 ID 取得審查記錄

        Args:
            review_id: 審查記錄 ID

        Returns:
            審查記錄或 None
        """
        from sqlalchemy.orm import selectinload

        from app.models.review import ApplicationReview

        stmt = (
            select(ApplicationReview)
            .where(ApplicationReview.id == review_id)
            .options(
                selectinload(ApplicationReview.reviewer),
                selectinload(ApplicationReview.items),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_review(
        self,
        review_id: int,
        items: List[Dict[str, Any]],
    ) -> "ApplicationReview":
        """
        更新審查記錄

        Args:
            review_id: 審查記錄 ID
            items: 更新後的子項目審查列表

        Returns:
            更新後的審查記錄
        """
        # 取得現有審查記錄
        review = await self.get_review_by_id(review_id)
        if not review:
            return None

        # 刪除舊的子項目
        for old_item in review.items:
            await self.db.delete(old_item)

        # 建立新的子項目
        for item in items:
            review_item = ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=item["sub_type_code"],
                recommendation=item["recommendation"],
                comments=item.get("comments"),
            )
            self.db.add(review_item)

        # 重新計算整體建議和評論
        overall_recommendation = await self.calculate_overall_recommendation(items)
        combined_comments = await self.combine_comments(items)

        # 更新審查記錄
        review.recommendation = overall_recommendation
        review.comments = combined_comments
        review.reviewed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(review)

        # 更新 decision_reason
        reviewer = await self.db.get(User, review.reviewer_id)
        application = await self.db.get(Application, review.application_id)
        if application and reviewer:
            # 清除舊的 decision_reason（因為是更新）
            # 在實務上可能需要更複雜的邏輯來處理
            await self.update_decision_reason(application, reviewer, items, review.reviewed_at)

        # 更新申請狀態
        await self.update_application_status(review.application_id)
        await self.db.commit()

        return review

    async def get_review_by_application_and_reviewer(
        self, application_id: int, reviewer_id: int
    ) -> Optional["ApplicationReview"]:
        """
        根據申請 ID 和審查者 ID 取得審查記錄

        Args:
            application_id: 申請 ID
            reviewer_id: 審查者 ID

        Returns:
            審查記錄或 None
        """
        from sqlalchemy.orm import selectinload

        from app.models.review import ApplicationReview

        stmt = (
            select(ApplicationReview)
            .where(
                ApplicationReview.application_id == application_id,
                ApplicationReview.reviewer_id == reviewer_id,
            )
            .options(
                selectinload(ApplicationReview.reviewer),
                selectinload(ApplicationReview.items),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
