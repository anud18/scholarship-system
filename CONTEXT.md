# Scholarship System

Handles scholarship applications from student submission through professor and
college review, quota distribution, and payment roster generation.

## Language

### Distribution

**分發 (Distribution)**:
Deciding which ranked students receive a quota slot, and from which sub-type and
year's quota. Happens after a college finalizes its ranking.
_Avoid_: allocation (reserved for a single student's slot), assignment

**名額 (Quota Slot)**:
One fundable place, owned by a (sub-type × configuration × college) cell of the
quota matrix. A student holds at most one.
_Avoid_: quota (that is the count of slots), place

**核配 (Allocation)**:
The pairing of one student with one 名額. A student's allocation names both the
sub-type and the configuration whose quota the slot is drawn from.
_Avoid_: award (that is post-確認分發), grant

**已儲存分配 (Saved Allocation)**:
An allocation persisted to the database. The state the system would act on if
everyone went home now.
_Avoid_: committed, confirmed (確認分發 means something else)

**暫存分配 (Staged Allocation)**:
An allocation the admin has made on screen but not yet saved. The distribution
screen's authoritative state — 預設分發 and every quota count on the page are
computed against 暫存分配, never against 已儲存分配.
_Avoid_: local allocation, draft, unsaved change

**未決 (Undecided)**:
A student with no 暫存分配. Being 未決 is the only thing that makes a student
eligible for 預設分發 — unticking a box returns the student to 未決, and their
slot is immediately available to someone else.
_Avoid_: blank, empty, cleared, unallocated (that describes an outcome, not a
state)

**預設分發 (Default Distribution)**:
Filling every 未決 student the algorithm can place, by rank and preference
order, without disturbing anyone already decided. Idempotent: pressing it twice
changes nothing the second time.
_Avoid_: auto-allocate, preview, suggestion

**未分配原因 (Unallocated Reason)**:
Why 預設分發 could not place a particular student — 名額已滿, 審核不同意,
未申請該類別, 已撤銷停發, or 學院不推薦. Determined where the allocation
decision is made, never inferred afterwards.
_Avoid_: skip reason, error

**確認分發 (Finalize)**:
Locking a distribution: allocated students become approved, the rest rejected.
The point after which a student 持有獎助 (holds an award) rather than merely a
名額.
_Avoid_: confirm, commit, approve

**撤銷／停發 (Cancelled Allocation)**:
An admin decision to pull a student out of the distribution entirely. Frees
their 名額 but, unlike 未決, never makes them a candidate again.
_Avoid_: cancelled, removed, excluded

### Received months

**已領月份數 (Received Months)**:
How many months a student has been paid a given scholarship. Always the sum of
匯入月份數 and 系統月份數 — never one substituted for the other.
_Avoid_: received months (unqualified), 領取月數

**匯入月份數 (Imported Months)**:
The lifetime baseline taken from 國科會's report, derived from the inclusive span
領獎起始月份 → 目前領獎月份. Keyed by (學號 × scholarship type), so it exists
whether or not the student has ever applied through this system.
_Avoid_: override, imported override, manual months

**系統月份數 (System Months)**:
The half derived live from this system's own payment rosters, by roster cycle
(monthly 1, semi-yearly 6, yearly 12). Never persisted — recomputed on every read.
_Avoid_: calculated months, auto months

**匯入批次 (Import Run)**:
One upload of 國科會's report. Staged on preview, committed on confirm; nothing
reaches the ledger until an admin confirms.
_Avoid_: import job, 批次匯入 (that is the offline *application* importer)

### Student identity

**學號 (Student Number)**:
The student's NYCU number (`std_stdcode`). The canonical key for matching a
person across applications, rosters and imported records.
_Avoid_: student id, student_id_number (that column holds the national ID)

**身分證字號 (National ID)**:
`std_pid`. Carried only for the payment-roster Excel column; never used to match
identity, since foreign students may not have one.
_Avoid_: student id
