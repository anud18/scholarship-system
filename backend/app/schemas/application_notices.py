"""Schemas and default content for the student wizard 獎學金申請注意事項.

The content is stored in ``system_settings`` under key ``application_notices``
(``data_type=json``) so administrators can edit every notice item (and the
important-notice banner) without a code deploy. When the setting has not been
configured yet, the API serves ``DEFAULT_APPLICATION_NOTICES`` — the original
copy that used to be hardcoded in the frontend wizard.
"""

from typing import List

from pydantic import BaseModel, Field

# system_settings.key that stores the admin-edited content.
APPLICATION_NOTICES_KEY = "application_notices"


class ApplicationNoticeItem(BaseModel):
    """One numbered notice item (e.g. 申請資格, 申請期限)."""

    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=2000)


class LocalizedApplicationNotices(BaseModel):
    """Notice content for a single locale."""

    items: List[ApplicationNoticeItem] = Field(..., min_length=1, max_length=30)
    important_notice: str = Field(..., min_length=1, max_length=2000)


class ApplicationNotices(BaseModel):
    """Full bilingual notice content shown in the application wizard."""

    zh: LocalizedApplicationNotices
    en: LocalizedApplicationNotices


DEFAULT_APPLICATION_NOTICES = ApplicationNotices(
    zh=LocalizedApplicationNotices(
        items=[
            ApplicationNoticeItem(
                title="申請資格",
                content=(
                    "申請人必須為本校在學【全職學生】，【不得於公私立機構從事專職全時之有給職工作】，"
                    "且符合各獎學金規定的申請條件。請確認您的學籍狀態與申請資格。"
                ),
            ),
            ApplicationNoticeItem(
                title="申請限制",
                content=(
                    "每位獲獎學生至多可領獎3年共計6學期，國科會與教育部獎學金兩獎項合併計算，申請次數不限。\n"
                    "每次申請為一學年期程，並可申請續領至滿三學年為止。如遇休學、退學、畢業，"
                    "或有違反本校獎學金要點相關規定之情事，將喪失領獎資格，將由備取學生遞補。"
                ),
            ),
            ApplicationNoticeItem(
                title="申請期限",
                content="各獎學金有不同的申請期限，逾期申請恕不受理。請注意各獎學金的開放申請日期與截止日期。",
            ),
            ApplicationNoticeItem(
                title="文件準備",
                content=(
                    "請備妥所需文件，包括但不限於成績單、郵局存摺封面、勞保投保紀錄、指導教授推薦函等。"
                    "所有文件必須為清晰可辨識的電子檔案（PDF、JPG、JPEG 或 PNG 格式）。"
                ),
            ),
            ApplicationNoticeItem(
                title="資料正確性",
                content="申請人應確保所填寫資料及上傳文件之正確性與真實性。如有虛偽不實，將取消申請資格並依校規處理。",
            ),
            ApplicationNoticeItem(
                title="個人資料使用",
                content="您的個人資料將僅用於獎學金申請審核及後續相關作業，本校將依個人資料保護法規定妥善保管。",
            ),
            ApplicationNoticeItem(
                title="審核流程",
                content=(
                    "申請送出後，須經指導教授審核，並依序辦理系所初審、學院複審及教務處校級複核會議審查等程序。"
                    "審核期間，請隨時留意系統通知，以掌握最新審查進度。"
                ),
            ),
            ApplicationNoticeItem(
                title="獎金撥款",
                content="獲獎學生請確認郵局帳戶資料正確無誤，獎學金將於核定後撥款至指定帳戶",
            ),
            ApplicationNoticeItem(
                title="申請撤回",
                content="申請送出後如需撤回，請於審核開始前聯繫承辦單位。審核程序啟動後將無法撤回申請。",
            ),
        ],
        important_notice=(
            "請務必詳細閱讀各項獎學金要點與相關規定。\n"
            "每位學生每次申請國科會或教育部博士生獎學金為一學年期程，僅可擇一獲獎，請謹慎選擇。"
        ),
    ),
    en=LocalizedApplicationNotices(
        items=[
            ApplicationNoticeItem(
                title="Eligibility",
                content=(
                    "Applicants must be currently enrolled students and meet the specific requirements of "
                    "each scholarship. Please verify your enrollment status and eligibility."
                ),
            ),
            ApplicationNoticeItem(
                title="Application Restrictions",
                content=(
                    "Each awarded student may receive the scholarship for up to 3 years (6 semesters total); "
                    "the NSTC and MOE scholarships are counted together, with no limit on the number of "
                    "applications.\nEach application covers one academic year, and may be renewed up to a "
                    "total of three academic years. Recipients who take a leave of absence, withdraw, "
                    "graduate, or violate the university's scholarship regulations will forfeit their "
                    "eligibility, and a waitlisted student will be selected instead."
                ),
            ),
            ApplicationNoticeItem(
                title="Application Deadline",
                content=(
                    "Each scholarship has different application deadlines. Late applications will not be "
                    "accepted. Please note the opening and closing dates for each scholarship."
                ),
            ),
            ApplicationNoticeItem(
                title="Document Preparation",
                content=(
                    "Please prepare all required documents, including but not limited to transcripts, "
                    "enrollment certificates, and advisor recommendation letters. All documents must be "
                    "clear electronic files (PDF, JPG, JPEG, or PNG format)."
                ),
            ),
            ApplicationNoticeItem(
                title="Data Accuracy",
                content=(
                    "Applicants must ensure the accuracy and authenticity of all information and uploaded "
                    "documents. False information will result in disqualification and disciplinary action "
                    "according to university regulations."
                ),
            ),
            ApplicationNoticeItem(
                title="Personal Data Usage",
                content=(
                    "Your personal data will be used solely for scholarship application review and related "
                    "procedures. The university will safeguard your data according to Personal Data "
                    "Protection Act."
                ),
            ),
            ApplicationNoticeItem(
                title="Review Process",
                content=(
                    "After submission, applications will go through department preliminary review, college "
                    "review, and administrative approval. Please monitor system notifications during the "
                    "review period."
                ),
            ),
            ApplicationNoticeItem(
                title="Award Distribution",
                content=(
                    "Award recipients should ensure their bank account information is correct. Scholarships "
                    "will be disbursed to the designated account after approval."
                ),
            ),
            ApplicationNoticeItem(
                title="Application Withdrawal",
                content=(
                    "If you need to withdraw your application after submission, please contact the "
                    "administrative office before the review begins. Withdrawal is not possible once the "
                    "review process has started."
                ),
            ),
        ],
        important_notice=(
            "Please read the regulations and related rules for each scholarship carefully.\n"
            "Each student may apply for either the NSTC or MOE PhD Scholarship for one academic year per "
            "application, and may only receive one of the two. Please choose carefully."
        ),
    ),
)
