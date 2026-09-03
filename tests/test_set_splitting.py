from segmetric.set.core.splitting import split_filename_to_segments


def test_splits_on_underscore_and_strips_extension(tmp_path):
    path = tmp_path / "H6_120HR_34C_NR_1004_RH.pdf"
    path.write_bytes(b"x")

    segments = split_filename_to_segments(str(path))

    assert [s.raw_value for s in segments] == ["H6", "120HR", "34C", "NR", "1004", "RH"]
    assert [s.index for s in segments] == [0, 1, 2, 3, 4, 5]
    assert [s.column_name for s in segments] == [
        "col_1", "col_2", "col_3", "col_4", "col_5", "col_6",
    ]
    assert all(s.include for s in segments)


def test_single_token_filename(tmp_path):
    path = tmp_path / "sample.png"
    path.write_bytes(b"x")

    segments = split_filename_to_segments(str(path))

    assert len(segments) == 1
    assert segments[0].raw_value == "sample"
    assert segments[0].column_name == "col_1"
