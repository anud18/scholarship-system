# Service Layer Refactoring Checklist

## Overview
After removing all scoring fields from models, the following service files need manual review and updates.

## Files Requiring Review (12 total)

### 🔴 High Priority - Core Services

#### 1. `application_service.py`
**What to check**:
- [ ] Remove all assignments to `application.review_score`
- [ ] Remove all assignments to `application.review_comments`
- [ ] Remove all assignments to `application.rejection_reason`
- [ ] Remove all assignments to `application.priority_score`
- [ ] Remove all `calculate_priority_score()` calls
- [ ] Remove any score-based sorting/filtering logic
- [ ] Update response building to not include removed fields

**Pattern to search**:
```python
grep -n "review_score\|rejection_reason\|priority_score\|calculate_priority" application_service.py
```

#### 2. `college_review_service.py`
**What to check**:
- [ ] Remove all `ranking_score` calculation logic
- [ ] Remove all `academic_score` calculation logic
- [ ] Remove all `professor_review_score` calculation logic
- [ ] Remove all `college_criteria_score` calculation logic
- [ ] Remove all `special_circumstances_score` calculation logic
- [ ] Remove `scoring_weights` logic
- [ ] Update ranking logic to use `final_rank` instead of `ranking_score`
- [ ] Remove score-based sorting (use rank positions instead)

**Pattern to search**:
```python
grep -n "ranking_score\|academic_score\|professor_review_score\|college_criteria_score\|special_circumstances_score\|scoring_weights" college_review_service.py
```

#### 3. `bulk_approval_service.py`
**What to check**:
- [ ] Remove assignments to `application.rejection_reason`
- [ ] Change rejection logic to create/update `ApplicationReview` record with `decision_reason`
- [ ] Update batch operations to not use scoring fields

**Pattern to search**:
```python
grep -n "rejection_reason" bulk_approval_service.py
```

---

### 🟡 Medium Priority - Supporting Services

#### 4. `application_audit_service.py`
**What to check**:
- [ ] Remove audit logs for deleted scoring fields
- [ ] Update field change tracking

#### 5. `email_automation_service.py`
**What to check**:
- [ ] Update email templates to not reference `rejection_reason` from Application
- [ ] Get rejection reason from `ApplicationReview.decision_reason` instead
- [ ] Remove any score-related email notifications

#### 6. `github_integration_service.py`
**What to check**:
- [ ] Update GitHub issue creation to not include scores
- [ ] Update ranking displays to use rank positions instead of scores

#### 7. `scholarship_notification_service.py`
**What to check**:
- [ ] Update notification messages to not reference `rejection_reason`
- [ ] Get rejection info from `ApplicationReview` instead

---

### 🟢 Low Priority - Analytics & Utilities

#### 8. `matrix_distribution.py`
**What to check**:
- [ ] Update distribution algorithm to not use scores
- [ ] Use rank positions for distribution logic

#### 9. `analytics_service.py`
**What to check**:
- [ ] Remove score-based analytics
- [ ] Update statistics to use rank-based metrics

#### 10. `scholarship_service.py`
**What to check**:
- [ ] Remove any score-related validation
- [ ] Update configuration validation

#### 11. `alternate_promotion_service.py`
**What to check**:
- [ ] Update promotion logic to not use `rejection_reason`
- [ ] Check for any score-based eligibility

#### 12. `plugins/phd_eligibility_plugin.py`
**What to check**:
- [ ] Update eligibility checks to not use scores
- [ ] Update rejection reason handling

---

## Common Refactoring Patterns

### Pattern 1: Remove Score Assignment
```python
# ❌ OLD
application.review_score = 85.5
application.review_comments = "Good application"
application.rejection_reason = "GPA too low"

# ✅ NEW
# Create/update ApplicationReview record instead
review = ApplicationReview(
    application_id=application.id,
    reviewer_id=current_user.id,
    comments="Good application",
    decision_reason="GPA too low",  # for rejections
    review_status="completed"
)
db.add(review)
```

### Pattern 2: Update Ranking Logic
```python
# ❌ OLD
applications = applications.order_by(Application.college_ranking_score.desc())

# ✅ NEW
applications = applications.join(CollegeReview).order_by(CollegeReview.final_rank.asc())
```

### Pattern 3: Get Rejection Reason
```python
# ❌ OLD
rejection_reason = application.rejection_reason

# ✅ NEW
# Get from latest ApplicationReview
latest_review = application.reviews[-1] if application.reviews else None
rejection_reason = latest_review.decision_reason if latest_review else None
```

### Pattern 4: Remove Priority Score
```python
# ❌ OLD
application.priority_score = application.calculate_priority_score()
sorted_apps = sorted(applications, key=lambda x: x.priority_score, reverse=True)

# ✅ NEW
# Use submitted_at or other criteria for sorting
sorted_apps = sorted(applications, key=lambda x: x.submitted_at)
```

---

## Validation Commands

### 1. Check for removed field references
```bash
cd /home/jotp/scholarship-system/backend

# Search for removed Application fields
grep -r "\.review_score" app/services/
grep -r "\.review_comments" app/services/
grep -r "\.rejection_reason" app/services/
grep -r "\.priority_score" app/services/
grep -r "\.college_ranking_score" app/services/

# Search for removed CollegeReview fields
grep -r "\.ranking_score" app/services/
grep -r "\.academic_score" app/services/
grep -r "\.professor_review_score" app/services/
grep -r "\.scoring_weights" app/services/

# Search for removed ApplicationReview fields
grep -r "\.score" app/services/ | grep -v "gpa\|ascore"
grep -r "criteria_scores" app/services/
```

### 2. Check for removed methods
```bash
grep -r "calculate_priority_score" app/services/
```

### 3. Run tests after refactoring
```bash
pytest backend/tests/ -v
```

---

## Migration Impact Summary

| Table | Removed Fields | Replacement |
|-------|----------------|-------------|
| `applications` | `review_score`, `review_comments`, `rejection_reason`, `priority_score`, `college_ranking_score` | Use `ApplicationReview` and `CollegeReview` tables |
| `application_reviews` | `score`, `criteria_scores` | Use `comments`, `recommendation`, `decision_reason` |
| `college_reviews` | `ranking_score`, `academic_score`, `professor_review_score`, `college_criteria_score`, `special_circumstances_score`, `scoring_weights` | Use `preliminary_rank`, `final_rank` |

---

## Next Steps

1. **Run migration**: `alembic upgrade head`
2. **Review each service file** using the patterns above
3. **Test each modified service** individually
4. **Run full integration tests**
5. **Update frontend** if needed (remove score displays)
6. **Document changes** in commit message
