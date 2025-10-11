# Email Automation Integration Status

## 📊 Complete Integration Summary

All 6 trigger events for the email automation system have been successfully integrated.

| Trigger Event | Method Status | Integration Location | Status |
|---------------|--------------|---------------------|--------|
| application_submitted | ✅ Defined | application_service.py:967 | ✅ Integrated |
| professor_review_submitted | ✅ Defined | application_service.py:1342 | ✅ Integrated |
| college_review_submitted | ✅ Defined | college_review_service.py:158 | ✅ Integrated |
| final_result_decided | ✅ Defined | college_review_service.py:632 | ✅ Integrated |
| supplement_requested | ✅ Defined | document_requests.py:98 | ✅ Integrated |
| deadline_approaching | ✅ Defined | tasks/deadline_checker.py:127 | ✅ Integrated |

## 🔧 Changes Made

### 1. Added Missing Trigger Methods
**File**: `backend/app/services/email_automation_service.py`

Added three new trigger methods:
- `trigger_college_review_submitted()` (line 305)
- `trigger_supplement_requested()` (line 327)
- `trigger_deadline_approaching()` (line 349)

### 2. Integrated Professor Review Submitted Trigger
**File**: `backend/app/services/application_service.py`

**Location**: `create_professor_review()` method (line 1329-1360)

**What it does**:
- Fetches student and scholarship information
- Triggers email automation when professor submits a review
- Provides context including professor recommendation, ranking score, and review date

**Context data provided**:
```python
{
    "app_id": application.app_id,
    "student_name": student.name,
    "professor_name": user.name,
    "professor_email": user.email,
    "scholarship_type": scholarship.name,
    "scholarship_type_id": application.scholarship_type_id,
    "review_result": review.review_status,
    "review_date": review.reviewed_at,
    "professor_recommendation": review.recommendation,
    "college_name": application.college_name,
}
```

### 3. Integrated College Review Submitted Trigger
**File**: `backend/app/services/college_review_service.py`

**Location**: `create_or_update_review()` method (line 145-180)

**What it does**:
- Fetches reviewer and student information
- Triggers email automation when college submits a review
- Provides context including ranking score, recommendation, and comments

**Context data provided**:
```python
{
    "app_id": application.app_id,
    "student_name": student.name,
    "student_email": student.email,
    "college_name": reviewer.college,
    "ranking_score": college_review.ranking_score,
    "recommendation": review_data.get("recommendation"),
    "comments": review_data.get("comments"),
    "reviewer_name": reviewer.name,
    "scholarship_type": application.scholarship_type_ref.name,
    "scholarship_type_id": application.scholarship_type_id,
    "review_date": college_review.reviewed_at,
}
```

### 4. Integrated Supplement Requested Trigger
**File**: `backend/app/api/v1/endpoints/document_requests.py`

**Location**: `create_document_request()` endpoint (line 84-118)

**What it does**:
- Replaced direct `EmailService.send_document_request_notification()` call
- Now uses email automation trigger for consistency
- Triggers when staff requests additional documents from students

**Context data provided**:
```python
{
    "app_id": application.app_id,
    "student_name": student_name,
    "student_email": student_email,
    "requested_documents": request_data.requested_documents,
    "reason": request_data.reason,
    "notes": request_data.notes,
    "requester_name": current_user.name,
    "deadline": "",  # Can be extended if deadline field added
    "scholarship_type": application.scholarship_name,
    "scholarship_type_id": application.scholarship_type_id,
    "request_date": datetime.now(),
}
```

### 5. Implemented Deadline Approaching Trigger System
**New Files Created**:
- `backend/app/tasks/__init__.py` - Tasks package
- `backend/app/tasks/deadline_checker.py` - Deadline checking service
- `backend/scripts/check_deadlines.sh` - Manual execution script

**Integration**:
- ✅ **Integrated with APScheduler**: Automatically runs daily at 9:00 AM
- ✅ **No Cron Needed**: Uses existing roster scheduler infrastructure
- ✅ **Redis-backed**: Job state persisted across restarts
- ✅ **Centralized Management**: All scheduled tasks in one place

**How it works**:
1. **Automatic Execution**: Starts with backend via `init_scheduler()` in `roster_scheduler_service.py`
2. **Warning Thresholds**: Sends notifications at 7, 3, and 1 day before deadline
3. **Deadline Types**:
   - Submission deadlines (implemented)
   - Document request deadlines (placeholder for future)
   - Review deadlines (placeholder for future)

**Running the deadline checker**:

```bash
# Automatic execution (default)
# Backend starts → APScheduler starts → Deadline checker runs daily at 9 AM
# No configuration needed!

# Manual run (for testing)
cd backend
python -m app.tasks.deadline_checker

# Or use the script
./scripts/check_deadlines.sh
```

**Check scheduled jobs**:
```python
# Via Python
from app.services.roster_scheduler_service import roster_scheduler
jobs = roster_scheduler.list_all_jobs()
# Look for job_id: "deadline_checker"
```

**Context data provided**:
```python
{
    "app_id": application.app_id,
    "student_name": student.name,
    "student_email": student.email,
    "deadline": config.submission_deadline,
    "days_remaining": "7",  # or "3", "1"
    "deadline_type": "submission",  # or "supplement", "review"
    "scholarship_name": config.scholarship_type.name,
    "scholarship_type": application.main_scholarship_type,
    "scholarship_type_id": config.scholarship_type_id,
}
```

## 🏗️ Architecture

### APScheduler Integration
The deadline checker is integrated into the existing APScheduler infrastructure:

**Scheduler Startup Flow**:
```
backend/main.py:lifespan()
    ↓
roster_scheduler_service.py:init_scheduler()
    ↓
roster_scheduler.start_scheduler()
    ↓
Load active schedules from DB
    ↓
Add fixed jobs:
    - batch_import_cleanup (2 AM)
    - deadline_checker (9 AM)
```

**Benefits**:
- ✅ **Centralized**: All scheduled tasks in one APScheduler instance
- ✅ **Persistent**: Redis-backed job store survives restarts
- ✅ **Observable**: `list_all_jobs()` for monitoring
- ✅ **Controllable**: Pause/resume/remove jobs programmatically
- ✅ **Development-friendly**: Works in local dev environment

### Unified Trigger Pattern
All trigger events follow the same pattern:

```python
# 1. Fetch necessary context data
student = await db.get(User, application.user_id)
scholarship = await db.get(ScholarshipType, application.scholarship_type_id)

# 2. Call email automation service
from app.services.email_automation_service import email_automation_service

await email_automation_service.trigger_<event_name>(
    db=db,
    application_id=application.id,
    <context>_data={
        "app_id": application.app_id,
        "student_name": student.name,
        "student_email": student.email,
        # ... event-specific fields
    },
)
```

### Email Automation Service Architecture
**File**: `backend/app/services/email_automation_service.py`

**Core Components**:
1. **Trigger Methods**: High-level entry points for each event
2. **process_trigger()**: Fetches active automation rules for the event
3. **_process_single_rule()**: Processes each rule (gets recipients, template, sends/schedules)
4. **_get_recipients()**: Executes condition query to find email recipients
5. **_send_automated_email()**: Sends email immediately
6. **_schedule_automated_email()**: Schedules email for later (based on delay_hours)

### Database Tables Used
- `email_automation_rules` - Define trigger → template mappings
- `email_templates` - Email content templates
- `scheduled_emails` - Store emails to be sent later
- `email_logs` - Track all sent emails

## 📝 Usage Examples

### Example 1: Creating an Email Automation Rule

When a professor submits a review, notify the student:

```sql
INSERT INTO email_automation_rules (
    template_key,
    trigger_event,
    condition_query,
    is_active,
    delay_hours
) VALUES (
    'professor_review_notification',
    'professor_review_submitted',
    'SELECT u.email FROM users u JOIN applications a ON a.user_id = u.id WHERE a.id = {application_id}',
    true,
    0  -- Send immediately
);
```

### Example 2: Creating an Email Template

```sql
INSERT INTO email_templates (
    key,
    name,
    subject_template,
    body_template,
    category
) VALUES (
    'professor_review_notification',
    'Professor Review Notification',
    '【{scholarship_type}】教授審查結果通知',
    '親愛的 {student_name} 同學：

您的申請（{app_id}）已由教授 {professor_name} 完成審查。

審查結果：{review_result}
審查意見：{professor_recommendation}

請登入系統查看詳細資訊。

系統連結：{system_url}',
    'review_professor'
);
```

### Example 3: Testing a Trigger

```python
# In your test code
from app.services.email_automation_service import email_automation_service

# Trigger professor review submitted
await email_automation_service.trigger_professor_review_submitted(
    db=db,
    application_id=123,
    review_data={
        "app_id": "APP-2024-001",
        "student_name": "張三",
        "professor_name": "李教授",
        "scholarship_type": "優秀學生獎學金",
        "review_result": "推薦",
        "professor_recommendation": "學生表現優異，強烈推薦",
    }
)
```

## 🔍 Verification

### Check Integration Status

Run this query to verify all triggers are integrated:

```sql
SELECT
    trigger_event::text as event,
    COUNT(*) as rule_count,
    COUNT(CASE WHEN is_active THEN 1 END) as active_rules
FROM email_automation_rules
GROUP BY trigger_event
ORDER BY trigger_event;
```

Expected results:
```
event                       | rule_count | active_rules
----------------------------|------------|-------------
application_submitted       | 1+         | 1+
college_review_submitted    | 1+         | 1+
deadline_approaching        | 1+         | 1+
final_result_decided        | 1+         | 1+
professor_review_submitted  | 1+         | 1+
supplement_requested        | 1+         | 1+
```

### Test Email Sending

1. **Check email logs**:
```sql
SELECT * FROM email_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

2. **Check scheduled emails**:
```sql
SELECT * FROM scheduled_emails
WHERE status = 'PENDING'
ORDER BY scheduled_for ASC;
```

## 🚀 Next Steps

### Optional Enhancements

1. **Add Deadline Fields to DocumentRequest**:
```sql
ALTER TABLE document_requests ADD COLUMN deadline TIMESTAMP WITH TIME ZONE;
```

2. **Add Review Deadline Fields to ScholarshipConfiguration**:
```sql
ALTER TABLE scholarship_configurations
ADD COLUMN professor_review_deadline TIMESTAMP WITH TIME ZONE,
ADD COLUMN college_review_deadline TIMESTAMP WITH TIME ZONE;
```

3. **APScheduler Integration** (✅ Already Implemented):
```python
# Already integrated in roster_scheduler_service.py:init_scheduler()
# Deadline checker runs automatically when backend starts!

# View all scheduled jobs:
from app.services.roster_scheduler_service import roster_scheduler
print(roster_scheduler.list_all_jobs())

# Current scheduled jobs:
# - roster_schedule_* (dynamic, based on DB config)
# - batch_import_cleanup (daily at 2 AM)
# - deadline_checker (daily at 9 AM) ← NEW!
```

4. **Add More Granular Deadline Types**:
- Document upload deadlines
- Interview scheduling deadlines
- Acceptance confirmation deadlines

## 📦 Summary

**Total Changes**:
- ✅ 3 new trigger methods added to EmailAutomationService
- ✅ 3 existing service methods modified to call triggers
- ✅ 1 new background task system created (deadline_checker.py)
- ✅ Integrated with existing APScheduler infrastructure
- ✅ All code formatted with Black
- ✅ All syntax validated

**Result**: Complete email automation integration with unified trigger architecture!

### Scheduled Tasks Overview

| Task | Schedule | Location | Description |
|------|----------|----------|-------------|
| Roster Generation | Dynamic (Cron) | DB-configured | Auto-generate payment rosters |
| Batch Cleanup | Daily 2 AM | `roster_scheduler_service.py` | Clean expired batch data |
| **Deadline Checker** | **Daily 9 AM** | **`roster_scheduler_service.py`** | **Check approaching deadlines** |

**Monitoring**:
```python
# Check all scheduled jobs
from app.services.roster_scheduler_service import roster_scheduler
jobs = roster_scheduler.list_all_jobs()

# Check specific job
status = roster_scheduler.get_schedule_status(schedule_id)
```

---

Generated: 2025-10-11
Updated: 2025-10-11 (APScheduler Integration)
