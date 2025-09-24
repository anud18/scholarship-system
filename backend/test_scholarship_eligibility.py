#!/usr/bin/env python3
"""
測試獎學金資格邏輯的獨立腳本
"""

from datetime import datetime, timedelta, timezone


# 模擬設定
class MockSettings:
    debug = True
    environment = "development"


# 模擬資料
class MockStudent:
    def __init__(self, std_no, gpa, completed_terms):
        self.id = 1
        self.stdNo = std_no
        self.gpa = gpa
        self.completed_terms = completed_terms


class MockTermRecord:
    def __init__(self, gpa, completed_terms):
        self.gpa = float(gpa)
        self.completedTerms = completed_terms


class MockScholarship:
    def __init__(self):
        self.id = 1
        self.name = "學士班新生獎學金"
        self.code = "undergraduate_freshman"
        self.min_gpa = 3.38
        self.max_completed_terms = 6
        self.eligible_student_types = ["undergraduate"]
        self.whitelist_enabled = False
        self.whitelist_student_ids = []
        # 設定申請期間為當前時間前後30天
        now = datetime.now(timezone.utc)
        self.application_start_date = now - timedelta(days=30)
        self.application_end_date = now + timedelta(days=30)

    @property
    def is_application_period(self):
        now = datetime.now(timezone.utc)
        return self.application_start_date <= now <= self.application_end_date

    def is_student_in_whitelist(self, student_id):
        # 如果未啟用白名單，則不限制申請
        if not self.whitelist_enabled:
            return True
        # 如果啟用白名單但列表為空，則無人可申請
        if not self.whitelist_student_ids:
            return False
        # 檢查學生是否在白名單中
        return student_id in self.whitelist_student_ids


# 模擬開發設定
DEV_SCHOLARSHIP_SETTINGS = {
    "ALWAYS_OPEN_APPLICATION": True,
    "BYPASS_WHITELIST": True,
    "MOCK_APPLICATION_PERIOD": True,
}


class MockScholarshipService:
    def __init__(self):
        self.settings = MockSettings()

    def _is_dev_mode(self):
        return self.settings.debug or self.settings.environment == "development"

    def _should_bypass_application_period(self):
        return self._is_dev_mode() and DEV_SCHOLARSHIP_SETTINGS.get("ALWAYS_OPEN_APPLICATION", False)

    def _should_bypass_whitelist(self):
        return self._is_dev_mode() and DEV_SCHOLARSHIP_SETTINGS.get("BYPASS_WHITELIST", False)

    def check_scholarship_eligibility(self, student, term_record, scholarship):
        """檢查學生獎學金資格"""
        print(f"\n🔍 檢查獎學金資格: {scholarship.name}")
        print(f"學生: {student.stdNo}")
        print(f"GPA: {term_record.gpa}")
        print(f"修習學期數: {term_record.completedTerms}")
        print(f"開發模式: {self._is_dev_mode()}")

        # 檢查申請期間
        if not self._should_bypass_application_period() and not scholarship.is_application_period:
            print("❌ 不符合: 申請期間已過")
            return False
        elif self._should_bypass_application_period():
            print("🔧 DEV MODE: 跳過申請期間檢查")
        else:
            print(f"✅ 申請期間: {scholarship.application_start_date} 到 {scholarship.application_end_date}")

        # 檢查 GPA
        if scholarship.min_gpa and term_record.gpa < scholarship.min_gpa:
            print(f"❌ 不符合: GPA {term_record.gpa} 低於最低要求 {scholarship.min_gpa}")
            return False
        else:
            print(f"✅ GPA 符合: {term_record.gpa} >= {scholarship.min_gpa}")

        # 檢查修習學期數
        if scholarship.max_completed_terms and term_record.completedTerms > scholarship.max_completed_terms:
            print(f"❌ 不符合: 修習學期數 {term_record.completedTerms} 超過最大限制 {scholarship.max_completed_terms}")
            return False
        else:
            print(f"✅ 修習學期數符合: {term_record.completedTerms} <= {scholarship.max_completed_terms}")

        # 檢查白名單
        if not self._should_bypass_whitelist() and not scholarship.is_student_in_whitelist(student.id):
            print(f"❌ 不符合: 學生 {student.stdNo} 不在白名單中")
            return False
        elif self._should_bypass_whitelist() and scholarship.whitelist_enabled:
            print("🔧 DEV MODE: 跳過白名單檢查")
        else:
            print("✅ 白名單檢查通過")

        print(f"🎉 獎學金 {scholarship.name} 符合申請資格！")
        return True


def test_stu_under_eligibility():
    """測試 stu_under 學生的資格"""
    print("=" * 60)
    print("測試 stu_under 學士班新生獎學金資格")
    print("=" * 60)

    # 創建 stu_under 學生資料
    student = MockStudent("U1120001", 3.5, 2)
    term_record = MockTermRecord(3.5, 2)
    scholarship = MockScholarship()

    # 創建服務
    service = MockScholarshipService()

    # 檢查資格
    is_eligible = service.check_scholarship_eligibility(student, term_record, scholarship)

    print("\n📋 最終結果:")
    print(f"學生 {student.stdNo} {'符合' if is_eligible else '不符合'} {scholarship.name} 申請資格")

    return is_eligible


def test_different_scenarios():
    """測試不同情境"""
    print("\n" + "=" * 60)
    print("測試不同情境")
    print("=" * 60)

    scenarios = [
        {
            "name": "正常符合條件的學生",
            "std_no": "U1120002",
            "gpa": 3.5,
            "terms": 3,
            "expected": True,
        },
        {
            "name": "GPA 不符合的學生",
            "std_no": "U1120003",
            "gpa": 3.0,
            "terms": 2,
            "expected": False,
        },
        {
            "name": "修習學期數過多的學生",
            "std_no": "U1120004",
            "gpa": 3.8,
            "terms": 8,
            "expected": False,
        },
    ]

    service = MockScholarshipService()
    scholarship = MockScholarship()

    for scenario in scenarios:
        print(f"\n--- {scenario['name']} ---")
        student = MockStudent(scenario["std_no"], scenario["gpa"], scenario["terms"])
        term_record = MockTermRecord(scenario["gpa"], scenario["terms"])

        result = service.check_scholarship_eligibility(student, term_record, scholarship)
        status = "✅ 符合預期" if result == scenario["expected"] else "❌ 不符合預期"
        print(f"結果: {'符合' if result else '不符合'} 資格 {status}")


if __name__ == "__main__":
    print("🎓 獎學金資格檢查測試")

    # 測試 stu_under
    stu_under_result = test_stu_under_eligibility()

    # 測試其他情境
    test_different_scenarios()

    print("\n" + "=" * 60)
    print("總結")
    print("=" * 60)
    print(f"stu_under 學生: {'✅ 符合新生獎學金資格' if stu_under_result else '❌ 不符合新生獎學金資格'}")
    print("開發模式設定:")
    print("- 跳過申請期間檢查: ✅")
    print("- 跳過白名單檢查: ✅")
    print("- 自動設定申請期間: ✅")
