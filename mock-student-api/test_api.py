#!/usr/bin/env python3
import requests
import json
import sys

def test_api():
    """Test the mock student API endpoints"""
    base_url = "http://localhost:8080"
    
    print("Testing Mock Student Database API...")
    
    # Test root endpoint
    try:
        response = requests.get(f"{base_url}/")
        assert response.status_code == 200
        print("✓ Root endpoint working")
    except Exception as e:
        print(f"✗ Root endpoint failed: {e}")
        return False
    
    # Test health check
    try:
        response = requests.get(f"{base_url}/health")
        assert response.status_code == 200
        health_data = response.json()
        print(f"✓ Health check working - {health_data['student_count']} students in database")
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False
    
    # Get list of students
    try:
        response = requests.get(f"{base_url}/api/students?limit=5")
        assert response.status_code == 200
        students = response.json()
        assert len(students) > 0
        print(f"✓ Student list working - found {len(students)} students")
        
        # Use first student for further tests
        test_student_id = students[0]['std_stdno']
        print(f"Using student ID {test_student_id} for testing")
        
    except Exception as e:
        print(f"✗ Student list failed: {e}")
        return False
    
    # Test student info endpoint
    try:
        response = requests.get(f"{base_url}/api/students/{test_student_id}")
        assert response.status_code == 200
        student_data = response.json()
        assert student_data['std_stdno'] == test_student_id
        print(f"✓ Student info working - {student_data['std_cname']} ({student_data['std_ename']})")
    except Exception as e:
        print(f"✗ Student info failed: {e}")
        return False
    
    # Test semester records
    try:
        response = requests.get(f"{base_url}/api/students/{test_student_id}/semesters")
        assert response.status_code == 200
        semester_data = response.json()
        assert semester_data['student_id'] == test_student_id
        assert len(semester_data['semesters']) > 0
        print(f"✓ Semester records working - {len(semester_data['semesters'])} semesters found")
    except Exception as e:
        print(f"✗ Semester records failed: {e}")
        return False
    
    # Test alternative semester endpoint
    try:
        response = requests.get(f"{base_url}/api/semesters?student_id={test_student_id}")
        assert response.status_code == 200
        semester_data2 = response.json()
        assert semester_data2['student_id'] == test_student_id
        print("✓ Alternative semester endpoint working")
    except Exception as e:
        print(f"✗ Alternative semester endpoint failed: {e}")
        return False
    
    # Test semester filtering
    if semester_data['semesters']:
        first_semester = semester_data['semesters'][0]
        year = first_semester['trm_year']
        term = first_semester['trm_term']
        
        try:
            response = requests.get(f"{base_url}/api/students/{test_student_id}/semesters?year={year}&term={term}")
            assert response.status_code == 200
            filtered_data = response.json()
            assert len(filtered_data['semesters']) >= 1
            print(f"✓ Semester filtering working - year {year}, term {term}")
        except Exception as e:
            print(f"✗ Semester filtering failed: {e}")
            return False
    
    # Test specific semester endpoint
    if semester_data['semesters']:
        first_semester = semester_data['semesters'][0]
        year = first_semester['trm_year']
        term = first_semester['trm_term']
        
        try:
            response = requests.get(f"{base_url}/api/students/{test_student_id}/semesters/{year}/{term}")
            assert response.status_code == 200
            specific_data = response.json()
            assert len(specific_data) == 1
            print(f"✓ Specific semester endpoint working")
        except Exception as e:
            print(f"✗ Specific semester endpoint failed: {e}")
            return False
    
    # Test 404 handling
    try:
        response = requests.get(f"{base_url}/api/students/nonexistent")
        assert response.status_code == 404
        print("✓ 404 handling working")
    except Exception as e:
        print(f"✗ 404 handling failed: {e}")
        return False
    
    print("\n🎉 All tests passed! Mock Student API is working correctly.")
    return True

if __name__ == "__main__":
    if not test_api():
        sys.exit(1)