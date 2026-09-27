"""
pipeline/test/test_text_report_combiner.py
9 tests for text_report_combiner.py
"""
import os
import pytest


class TestCombineReports:

    def test_section_headers_present(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        f1 = tmp_path / "alpha.txt"
        f2 = tmp_path / "beta.txt"
        f1.write_text("Alpha content")
        f2.write_text("Beta content")
        out = str(tmp_path / "MASTER.txt")
        combine_reports([str(f1), str(f2)], out, label="Test")
        with open(out) as f:
            content = f.read()
        assert "=== alpha.txt ===" in content
        assert "=== beta.txt ===" in content

    def test_correct_file_count_in_header(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        files = []
        for i in range(5):
            f = tmp_path / f"r{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))
        out = str(tmp_path / "MASTER.txt")
        combine_reports(files, out, label="Count")
        with open(out) as f:
            content = f.read()
        assert "Total sections: 5" in content

    def test_missing_input_raises_file_not_found(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        out = str(tmp_path / "MASTER.txt")
        with pytest.raises(FileNotFoundError):
            combine_reports(["/does/not/exist.txt"], out, label="X")

    def test_empty_input_list_raises_value_error(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        out = str(tmp_path / "MASTER.txt")
        with pytest.raises(ValueError, match="empty"):
            combine_reports([], out, label="X")

    def test_output_file_is_created(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        f = tmp_path / "in.txt"
        f.write_text("hello")
        out = str(tmp_path / "sub" / "MASTER.txt")
        combine_reports([str(f)], out, label="X")
        assert os.path.exists(out)

    def test_label_appears_in_header(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        f = tmp_path / "r.txt"
        f.write_text("data")
        out = str(tmp_path / "MASTER.txt")
        combine_reports([str(f)], out, label="My Special Label")
        with open(out) as fh:
            assert "My Special Label" in fh.read()

    def test_order_preserved(self, tmp_path):
        from pipeline.scripts.text_report_combiner import combine_reports
        f1 = tmp_path / "first.txt"
        f2 = tmp_path / "second.txt"
        f1.write_text("FIRST")
        f2.write_text("SECOND")
        out = str(tmp_path / "MASTER.txt")
        combine_reports([str(f1), str(f2)], out, label="X")
        with open(out) as f:
            content = f.read()
        assert content.index("FIRST") < content.index("SECOND")

    def test_spc_input_detected_and_named_correctly(self, tmp_path):
        """When spc/rpn files are in inputs, output named MASTER_CONSOLIDATED_STATISTICAL_REPORT."""
        from pipeline.scripts.text_report_combiner import combine_reports
        f = tmp_path / "spc_summary_L0.txt"
        f.write_text("spc content")
        out = str(tmp_path / "MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt")
        combine_reports([str(f)], out, label="Statistical")
        assert os.path.exists(out)

    def test_content_not_truncated(self, tmp_path):
        """Full content of each file must appear in output - not truncated."""
        from pipeline.scripts.text_report_combiner import combine_reports
        long_content = "X" * 50_000
        f = tmp_path / "big.txt"
        f.write_text(long_content)
        out = str(tmp_path / "MASTER.txt")
        combine_reports([str(f)], out, label="Big")
        with open(out) as fh:
            result = fh.read()
        assert long_content in result


class TestFloorGuard:
    """Log-only skeleton/empty-input detection (mirror of the preflight ceiling)."""

    def test_empty_section_warns_and_names_file(self, tmp_path, caplog):
        import logging
        from pipeline.scripts.text_report_combiner import combine_reports
        good = tmp_path / "populated.txt"
        good.write_text("Real analytics output with plenty of substantive data rows here.")
        empty = tmp_path / "spc_summary.txt"
        empty.write_text("   \n")  # ran but wrote nothing
        out = str(tmp_path / "MASTER.txt")
        with caplog.at_level(logging.WARNING, logger="pipeline.scripts.text_report_combiner"):
            combine_reports([str(good), str(empty)], out, label="X")
        assert os.path.exists(out)  # still produced - non-breaking
        assert any("empty/near-empty" in r.message and "spc_summary.txt" in r.message
                   for r in caplog.records)

    def test_all_empty_warns_skeleton(self, tmp_path, caplog):
        import logging
        from pipeline.scripts.text_report_combiner import combine_reports
        files = []
        for i in range(3):
            f = tmp_path / f"s{i}.txt"
            f.write_text("")  # every section empty - the RISK-INTELL failure mode
            files.append(str(f))
        out = str(tmp_path / "MASTER.txt")
        with caplog.at_level(logging.WARNING, logger="pipeline.scripts.text_report_combiner"):
            combine_reports(files, out, label="X")
        assert any("DATA-POPULATION FAILURE" in r.message for r in caplog.records)

    def test_populated_report_no_warning(self, tmp_path, caplog):
        import logging
        from pipeline.scripts.text_report_combiner import combine_reports
        f = tmp_path / "r.txt"
        f.write_text("A" * 5_000)
        out = str(tmp_path / "MASTER.txt")
        with caplog.at_level(logging.WARNING, logger="pipeline.scripts.text_report_combiner"):
            combine_reports([str(f)], out, label="X")
        assert not caplog.records
