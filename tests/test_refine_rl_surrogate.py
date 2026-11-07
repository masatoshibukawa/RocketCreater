from scripts.refine_rl_surrogate import partition_records


def test_original_test_identity_cannot_reenter_from_search_history():
    rows = [dict(spec_hash="test-design", split=split) for split in ("train", "validation")]
    rows += [dict(spec_hash="shared", split=split) for split in ("train", "validation")]
    rows += [dict(spec_hash="train-only", split="train")]
    train, validation = partition_records(rows, {"test-design"})
    assert set(train) == {"train-only"}
    assert set(validation) == {"shared"}
