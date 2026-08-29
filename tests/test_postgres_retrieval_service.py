import pytest

from services.postgres_retrieval_service import (
    BranchHit,
    candidate_pool_size,
    fuse_ranked_ids,
    normalize_weights,
)


def test_candidate_pool_size_uses_approved_bounds():
    assert candidate_pool_size(1) == 100
    assert candidate_pool_size(20) == 100
    assert candidate_pool_size(21) == 105
    assert candidate_pool_size(100) == 500


def test_rrf_contributes_only_for_branches_where_job_appeared():
    fused = fuse_ranked_ids(
        dense=[BranchHit(job_id=1, rank=1, score=0.9)],
        lexical=[BranchHit(job_id=2, rank=1, score=4.0)],
        dense_weight=0.5,
        sparse_weight=0.5,
    )

    by_id = {candidate.job_id: candidate for candidate in fused}
    assert by_id[1].dense_rank == 1
    assert by_id[1].sparse_rank is None
    assert by_id[1].rrf_score == pytest.approx(0.5 / 61)
    assert by_id[2].dense_rank is None
    assert by_id[2].sparse_rank == 1
    assert by_id[2].rrf_score == pytest.approx(0.5 / 61)


def test_weight_normalization_rejects_zero_and_normalizes_valid_values():
    with pytest.raises(ValueError, match="greater than zero"):
        normalize_weights(0, 0)
    assert normalize_weights(2, 1) == pytest.approx((2 / 3, 1 / 3))


def test_rrf_final_tie_breaker_is_job_id():
    dense = [
        BranchHit(job_id=9, rank=1, score=0.8),
        BranchHit(job_id=3, rank=1, score=0.8),
    ]
    first = fuse_ranked_ids(dense, [], 1, 0)
    second = fuse_ranked_ids(list(reversed(dense)), [], 1, 0)
    assert [candidate.job_id for candidate in first] == [3, 9]
    assert first == second


def test_fused_union_can_be_capped_deterministically():
    dense = [BranchHit(job_id=job_id, rank=job_id, score=1 / job_id) for job_id in range(1, 401)]
    fused = fuse_ranked_ids(dense, [], 1, 0, max_candidates=300)
    assert len(fused) == 300
    assert fused[0].job_id == 1
    assert fused[-1].job_id == 300
