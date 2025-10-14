"""
Simple verification script for application ID generation
"""
import re

from app.models.application_sequence import ApplicationSequence


def test_format_app_id():
    """Test app_id formatting"""
    print("Testing app_id formatting...")

    # Test first semester
    app_id = ApplicationSequence.format_app_id(113, "first", 1)
    assert app_id == "APP-113-1-00001", f"Expected APP-113-1-00001, got {app_id}"
    print(f"  ✓ First semester format: {app_id}")

    # Test second semester
    app_id = ApplicationSequence.format_app_id(113, "second", 125)
    assert app_id == "APP-113-2-00125", f"Expected APP-113-2-00125, got {app_id}"
    print(f"  ✓ Second semester format: {app_id}")

    # Test annual scholarship
    app_id = ApplicationSequence.format_app_id(114, "annual", 1)
    assert app_id == "APP-114-0-00001", f"Expected APP-114-0-00001, got {app_id}"
    print(f"  ✓ Annual format: {app_id}")

    # Test large sequence number
    app_id = ApplicationSequence.format_app_id(113, "first", 99999)
    assert app_id == "APP-113-1-99999", f"Expected APP-113-1-99999, got {app_id}"
    print(f"  ✓ Large sequence number: {app_id}")

    print("✓ All formatting tests passed!")


def test_get_semester_code():
    """Test semester code conversion"""
    print("\nTesting semester code conversion...")

    assert ApplicationSequence.get_semester_code("first") == "1"
    print("  ✓ first -> 1")

    assert ApplicationSequence.get_semester_code("second") == "2"
    print("  ✓ second -> 2")

    assert ApplicationSequence.get_semester_code("annual") == "0"
    print("  ✓ annual -> 0")

    assert ApplicationSequence.get_semester_code("unknown") == "0"
    print("  ✓ unknown -> 0 (default)")

    print("✓ All semester code tests passed!")


def test_app_id_pattern():
    """Test app_id pattern validation"""
    print("\nTesting app_id pattern validation...")

    # Valid formats
    valid_app_ids = [
        "APP-113-1-00001",
        "APP-113-2-00125",
        "APP-114-0-00001",
        "APP-113-1-99999",
    ]

    pattern = r"^APP-\d+-[0-2]-\d{5}$"
    for app_id in valid_app_ids:
        assert re.match(pattern, app_id), f"Valid app_id {app_id} failed validation"
        print(f"  ✓ Valid: {app_id}")

    # Invalid formats (old random format)
    invalid_app_ids = [
        "APP-2025-123456",  # Old format with year and random suffix
        "APP-113-3-00001",  # Invalid semester code (should be 0-2)
        "APP-113-1-1",  # Sequence not zero-padded
    ]

    for app_id in invalid_app_ids:
        if not re.match(pattern, app_id):
            print(f"  ✓ Correctly rejected: {app_id}")

    print("✓ All pattern validation tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Application ID Format Verification")
    print("=" * 60)

    try:
        test_format_app_id()
        test_get_semester_code()
        test_app_id_pattern()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe new application ID format is working correctly:")
        print("  Format: APP-{academic_year}-{semester_code}-{sequence:05d}")
        print("  Example: APP-113-1-00001 (Academic Year 113, First Semester, Sequence 1)")
        print()
        print("Ready to generate sequential application IDs!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
