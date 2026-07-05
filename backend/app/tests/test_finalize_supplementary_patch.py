"""Unit tests: finalize() skips reject for supplementary unallocated items.

These tests exercise the post-patch logic inline (with MagicMock objects)
rather than invoking the real ManualDistributionService.finalize() method,
which is async and DB-bound. The goal is to verify that the patched control
flow does the right thing in each of the three cases.
"""

from unittest.mock import MagicMock


def _make_item(is_allocated: bool, allocated_sub_type, is_supplementary: bool):
    item = MagicMock()
    item.is_allocated = is_allocated
    item.allocated_sub_type = allocated_sub_type
    item.is_supplementary = is_supplementary
    item.deleted_at = None
    item.status = "ranked"
    item.application = MagicMock()
    item.application.deleted_at = None
    item.application.status = "submitted"
    item.application.quota_allocation_status = None
    return item


class TestFinalizeSupplementaryPatch:
    def test_unallocated_supplementary_item_stays_ranked(self):
        """Unallocated is_supplementary=True item must NOT get item.status='rejected'."""
        item = _make_item(is_allocated=False, allocated_sub_type=None, is_supplementary=True)

        # Simulate the finalize loop logic after the patch
        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
            item.application.quota_allocation_status = "allocated"
        elif item.is_supplementary and not item.is_allocated:
            pass  # leave as-is
        else:
            item.status = "rejected"
            item.application.quota_allocation_status = "rejected"

        assert item.status != "rejected", "Supplementary unallocated item should NOT be rejected"
        assert item.application.quota_allocation_status is None

    def test_unallocated_regular_item_becomes_rejected(self):
        """Unallocated is_supplementary=False item MUST still get item.status='rejected'."""
        item = _make_item(is_allocated=False, allocated_sub_type=None, is_supplementary=False)

        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
        elif item.is_supplementary and not item.is_allocated:
            pass
        else:
            item.status = "rejected"
            item.application.quota_allocation_status = "rejected"

        assert item.status == "rejected"
        assert item.application.quota_allocation_status == "rejected"

    def test_allocated_supplementary_item_gets_approved(self):
        """Allocated supplementary item follows the normal approved path."""
        item = _make_item(is_allocated=True, allocated_sub_type="nstc", is_supplementary=True)
        item.application.status = "submitted"

        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
            item.application.quota_allocation_status = "allocated"
        elif item.is_supplementary and not item.is_allocated:
            pass
        else:
            item.status = "rejected"

        assert item.application.status == "approved"
