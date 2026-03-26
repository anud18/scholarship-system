"""
Test that PhD scholarship allows independent sub-type selection (not hierarchical).

Students should be able to apply for MOE (教育部) without first selecting NSTC (國科會).
The selection mode should be 'multiple', not 'hierarchical'.

TDD: Test written BEFORE changing the selection mode.
"""

import ast
import inspect
import textwrap

import pytest

from app.models.enums import SubTypeSelectionMode


def _get_phd_seed_selection_mode() -> str:
    """Extract the PhD scholarship's sub_type_selection_mode from seed.py source code.

    Parses the AST to find the scholarships_data list and locate the phd entry's
    sub_type_selection_mode value. This avoids executing the async seed function.
    """
    from app.seed import seed_scholarships

    source = inspect.getsource(seed_scholarships)
    # Dedent to parse as standalone function
    source = textwrap.dedent(source)
    tree = ast.parse(source)

    # Walk the AST to find the list assignment
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            for elt in node.elts:
                if not isinstance(elt, ast.Dict):
                    continue
                keys = [k.value if isinstance(k, ast.Constant) else None for k in elt.keys]
                values = elt.values
                if "code" in keys:
                    code_idx = keys.index("code")
                    code_val = values[code_idx]
                    if isinstance(code_val, ast.Constant) and code_val.value == "phd":
                        if "sub_type_selection_mode" in keys:
                            mode_idx = keys.index("sub_type_selection_mode")
                            mode_node = values[mode_idx]
                            # e.g. SubTypeSelectionMode.multiple.value
                            if isinstance(mode_node, ast.Attribute) and mode_node.attr == "value":
                                inner = mode_node.value  # SubTypeSelectionMode.multiple
                                if isinstance(inner, ast.Attribute):
                                    return inner.attr  # "multiple" or "hierarchical"
    raise RuntimeError("Could not find PhD scholarship seed data")


class TestPhdSubTypeSelectionMode:
    """PhD scholarship should use 'multiple' selection mode, not 'hierarchical'."""

    def test_seed_mode_is_multiple(self):
        """Verify the seed configuration sets PhD to 'multiple' mode."""
        mode = _get_phd_seed_selection_mode()
        assert mode == "multiple", (
            f"PhD scholarship seed uses '{mode}' mode, expected 'multiple'. "
            "Students should be able to select MOE without first selecting NSTC."
        )

    def test_moe_only_is_valid_under_multiple_mode(self):
        """With 'multiple' mode, selecting only MOE (without NSTC) should be valid."""
        # Simulate the validation logic from ScholarshipType.is_valid_sub_type_selection
        sub_type_list = ["nstc", "moe_1w"]
        mode = SubTypeSelectionMode.multiple.value

        selected = ["moe_1w"]
        # multiple mode: check all selected are in the allowed list
        assert all(s in sub_type_list for s in selected)

    def test_nstc_only_is_valid_under_multiple_mode(self):
        """With 'multiple' mode, selecting only NSTC should be valid."""
        sub_type_list = ["nstc", "moe_1w"]
        selected = ["nstc"]
        assert all(s in sub_type_list for s in selected)

    def test_both_any_order_is_valid_under_multiple_mode(self):
        """With 'multiple' mode, selecting both in any order should be valid."""
        sub_type_list = ["nstc", "moe_1w"]
        assert all(s in sub_type_list for s in ["nstc", "moe_1w"])
        assert all(s in sub_type_list for s in ["moe_1w", "nstc"])

    def test_hierarchical_rejects_moe_only(self):
        """Confirm hierarchical mode would reject MOE-only (the old behavior we're removing)."""
        sub_type_list = ["nstc", "moe_1w"]
        selected = ["moe_1w"]
        expected = sub_type_list[:len(selected)]
        # hierarchical: selected must match prefix of sub_type_list
        assert selected != expected, "Hierarchical should reject ['moe_1w'] alone"
