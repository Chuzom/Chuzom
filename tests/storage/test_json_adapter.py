"""Unit tests for JSON adapter (budget storage)."""

from __future__ import annotations

import json
import os
import pytest

from chuzom.storage.adapters.json_adapter import JsonAdapter


@pytest.mark.unit
class TestJsonAdapter:
    """JSON adapter unit tests."""

    def test_write_creates_file(self, chuzom_paths):
        """Verify write() creates file at correct path."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        data = {"openai": 50.0}

        adapter.write(data)

        assert chuzom_paths["budgets"].exists()
        assert json.loads(chuzom_paths["budgets"].read_text()) == data

    def test_write_atomic_uses_tmp_rename(self, chuzom_paths):
        """Verify atomic write uses temp file + rename."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        data = {"openai": 50.0}

        # Monitor tmp file creation
        tmp_path = chuzom_paths["budgets"].with_suffix(".json.tmp")
        adapter.write(data, atomic=True)

        # Tmp file should not exist after atomic write
        assert not tmp_path.exists()
        # Final file should exist
        assert chuzom_paths["budgets"].exists()

    def test_read_missing_file_returns_none(self, chuzom_paths):
        """Verify read() returns None when file doesn't exist."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        result = adapter.read()
        assert result is None

    def test_read_parses_json_correctly(self, chuzom_paths, sample_budgets):
        """Verify read() deserializes JSON correctly."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        chuzom_paths["budgets"].write_text(json.dumps(sample_budgets))

        result = adapter.read()

        assert result == sample_budgets

    def test_read_invalid_json_returns_none(self, chuzom_paths):
        """Graceful degradation: corrupted JSON returns None."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        chuzom_paths["budgets"].write_text("{ invalid json }")

        result = adapter.read()

        assert result is None

    def test_write_preserves_sort_order(self, chuzom_paths):
        """Verify JSON written with sorted keys (deterministic)."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        data = {"zebra": 1.0, "apple": 2.0, "mango": 3.0}

        adapter.write(data)

        # Read raw text to check key order
        content = chuzom_paths["budgets"].read_text()
        assert content.index("apple") < content.index("mango") < content.index("zebra")

    def test_append_not_supported(self, chuzom_paths):
        """Verify append() raises NotImplementedError."""
        adapter = JsonAdapter(chuzom_paths["budgets"])

        with pytest.raises(NotImplementedError):
            adapter.append({})

    def test_verify_integrity_returns_no_checks(self, chuzom_paths):
        """JSON files don't have integrity checks."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        is_valid, reason = adapter.verify_integrity()

        assert is_valid is True
        assert reason == "n/a"

    def test_write_non_atomic(self, chuzom_paths):
        """Verify non-atomic write (direct overwrite)."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        data = {"openai": 50.0}

        adapter.write(data, atomic=False)

        assert json.loads(chuzom_paths["budgets"].read_text()) == data

    def test_write_overwrites_existing(self, chuzom_paths):
        """Verify write() overwrites existing data."""
        adapter = JsonAdapter(chuzom_paths["budgets"])
        old_data = {"openai": 100.0}
        new_data = {"openai": 50.0, "gemini": 200.0}

        adapter.write(old_data)
        adapter.write(new_data)

        result = adapter.read()
        assert result == new_data
        assert "100.0" not in chuzom_paths["budgets"].read_text()
