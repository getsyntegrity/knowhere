"""Tests for CodeLocation value object."""

import pytest

from canonical.value_objects.code_location import CodeLocation


class TestCodeLocation:
    """Test CodeLocation invariants and behavior."""
    
    def test_valid_location(self):
        """T001: CodeLocation with valid fields."""
        loc = CodeLocation(start_line=10, start_column=3, end_line=25, end_column=8)
        assert loc.start_line == 10
        assert loc.start_column == 3
        assert loc.end_line == 25
        assert loc.end_column == 8
    
    def test_single_line_location(self):
        """T001: CodeLocation on single line."""
        loc = CodeLocation(start_line=10, start_column=3, end_line=10, end_column=8)
        assert loc.start_line == loc.end_line
        assert loc.start_column <= loc.end_column
    
    def test_immutability(self):
        """T001: CodeLocation is frozen."""
        loc = CodeLocation(start_line=10, start_column=3, end_line=25, end_column=8)
        with pytest.raises(Exception):  # frozen model
            loc.start_line = 20
    
    def test_equality(self):
        """T001: CodeLocation equality."""
        loc1 = CodeLocation(start_line=10, start_column=3, end_line=25, end_column=8)
        loc2 = CodeLocation(start_line=10, start_column=3, end_line=25, end_column=8)
        assert loc1 == loc2
    
    def test_string_serialization(self):
        """T001: CodeLocation string format."""
        loc = CodeLocation(start_line=10, start_column=3, end_line=25, end_column=8)
        assert str(loc) == "10:3-25:8"
    
    def test_string_deserialization(self):
        """T001: CodeLocation from string."""
        loc = CodeLocation.from_string("10:3-25:8")
        assert loc.start_line == 10
        assert loc.start_column == 3
        assert loc.end_line == 25
        assert loc.end_column == 8
    
    def test_end_line_before_start_raises(self):
        """T001: end_line < start_line raises error."""
        with pytest.raises(ValueError):
            CodeLocation(start_line=10, start_column=1, end_line=5, end_column=1)
    
    def test_end_column_before_start_on_same_line_raises(self):
        """T001: end_column < start_column on same line raises error."""
        with pytest.raises(ValueError):
            CodeLocation(start_line=10, start_column=8, end_line=10, end_column=3)
    
    def test_positive_constraint(self):
        """T001: All values must be positive."""
        with pytest.raises(ValueError):
            CodeLocation(start_line=0, start_column=1, end_line=1, end_column=1)
