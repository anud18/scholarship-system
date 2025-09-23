"""
Test application creation with dynamic fields
"""

from app.schemas.application import ApplicationCreate


def test_application_create_with_dynamic_fields():
    """Test that ApplicationCreate schema accepts dynamic fields from frontend"""
    
    # Simulate frontend form data with dynamic fields
    form_data = {
        "scholarship_type": "undergraduate_freshman",
        "academic_year": "2024",
        "semester": "2",
        "contact_email": "stu_under@nycu.edu.tw",
        "agree_terms": True,
        # Dynamic fields from application form configuration
        "university_academic_performance": "Excellent academic performance with GPA 3.8",
        "research_interests_and_directions": "Machine Learning and Artificial Intelligence",
        "expected_graduation_date": "2025-06-15",
        "personal_statement": "I am a dedicated student with strong research interests...",
        "research_proposal": "My research focuses on developing novel ML algorithms...",
        "budget_plan": "Total budget: $5000 for research materials and conference attendance",
        "milestone_plan": "Q1: Literature review, Q2: Algorithm development, Q3: Implementation, Q4: Evaluation"
    }
    
    # This should not raise any validation errors
    application = ApplicationCreate(**form_data)
    
    # Verify that all fields are preserved
    assert application.scholarship_type == "undergraduate_freshman"
    assert application.academic_year == "2024"
    assert application.semester == "2"
    assert application.contact_email == "stu_under@nycu.edu.tw"
    assert application.agree_terms is True
    
    # Verify dynamic fields are preserved
    assert application.university_academic_performance == "Excellent academic performance with GPA 3.8"
    assert application.research_interests_and_directions == "Machine Learning and Artificial Intelligence"
    assert application.expected_graduation_date == "2025-06-15"
    assert application.personal_statement == "I am a dedicated student with strong research interests..."
    assert application.research_proposal == "My research focuses on developing novel ML algorithms..."
    assert application.budget_plan == "Total budget: $5000 for research materials and conference attendance"
    assert application.milestone_plan == "Q1: Literature review, Q2: Algorithm development, Q3: Implementation, Q4: Evaluation"


def test_application_create_model_dump_includes_dynamic_fields():
    """Test that model_dump() includes all dynamic fields"""
    
    form_data = {
        "scholarship_type": "undergraduate_freshman",
        "academic_year": "2024",
        "semester": "2",
        "contact_email": "stu_under@nycu.edu.tw",
        "agree_terms": True,
        "university_academic_performance": "Excellent academic performance with GPA 3.8",
        "research_interests_and_directions": "Machine Learning and Artificial Intelligence"
    }
    
    application = ApplicationCreate(**form_data)
    dumped_data = application.model_dump()
    
    # Verify all fields are in the dumped data
    assert "scholarship_type" in dumped_data
    assert "academic_year" in dumped_data
    assert "semester" in dumped_data
    assert "contact_email" in dumped_data
    assert "agree_terms" in dumped_data
    assert "university_academic_performance" in dumped_data
    assert "research_interests_and_directions" in dumped_data
    
    # Verify values are correct
    assert dumped_data["scholarship_type"] == "undergraduate_freshman"
    assert dumped_data["university_academic_performance"] == "Excellent academic performance with GPA 3.8"
    assert dumped_data["research_interests_and_directions"] == "Machine Learning and Artificial Intelligence"


def test_application_update_with_dynamic_fields():
    """Test that ApplicationUpdate schema also accepts dynamic fields"""
    from app.schemas.application import ApplicationUpdate
    
    update_data = {
        "university_academic_performance": "Updated academic performance description",
        "research_interests_and_directions": "Updated research interests",
        "personal_statement": "Updated personal statement"
    }
    
    # This should not raise any validation errors
    application_update = ApplicationUpdate(**update_data)
    
    # Verify dynamic fields are preserved
    assert application_update.university_academic_performance == "Updated academic performance description"
    assert application_update.research_interests_and_directions == "Updated research interests"
    assert application_update.personal_statement == "Updated personal statement" 