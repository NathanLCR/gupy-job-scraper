"""Bounded PostgreSQL lexical/vector retrieval with deterministic RRF fusion."""

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from services.embedding_service import EmbeddingResult, embed_query_checked
from services.readiness_service import get_current_revision, get_expected_head


@dataclass(frozen=True)
class RetrievalFilters:
    region: Optional[str] = None
    country_code: Optional[str] = None
    workplace_type: Optional[str] = None
    seniority: Optional[str] = None
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    skill: Optional[str] = None
    location: Optional[str] = None


@dataclass(frozen=True)
class BranchHit:
    job_id: int
    rank: int
    score: float


@dataclass(frozen=True)
class RankedCandidate:
    job_id: int
    rrf_score: float
    dense_rank: Optional[int]
    dense_score: Optional[float]
    sparse_rank: Optional[int]
    sparse_score: Optional[float]


@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[RankedCandidate, ...]
    mode: Literal["hybrid", "dense", "lexical"]


@dataclass(frozen=True)
class RetrievalActivationStatus:
    schema_current: bool
    gin_index_valid: bool
    hnsw_index_valid: bool
    search_document_coverage: float
    embedding_coverage: float

    @property
    def can_activate(self) -> bool:
        return (
            self.schema_current
            and self.gin_index_valid
            and self.hnsw_index_valid
            and self.search_document_coverage == 1.0
            and self.embedding_coverage >= 0.95
        )


def evaluate_retrieval_activation(db: Session) -> RetrievalActivationStatus:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return RetrievalActivationStatus(False, False, False, 0.0, 0.0)

    connection = db.connection()
    schema_current = get_current_revision(connection) == get_expected_head()
    index_rows = db.execute(
        text(
            "SELECT c.relname, i.indisvalid, pg_get_expr(i.indpred, i.indrelid) AS predicate "
            "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
            "WHERE c.relname IN ('ix_jobs_search_document_gin','ix_jobs_embedding_hnsw')"
        )
    ).all()
    indexes = {row.relname: row for row in index_rows}
    gin = indexes.get("ix_jobs_search_document_gin")
    hnsw = indexes.get("ix_jobs_embedding_hnsw")
    total = int(db.scalar(text("SELECT count(*) FROM jobs")) or 0)
    if total == 0:
        search_coverage = embedding_coverage = 1.0
    else:
        search_coverage = float(
            db.scalar(text("SELECT count(*) FROM jobs WHERE search_document IS NOT NULL"))
            or 0
        ) / total
        embedding_coverage = float(
            db.scalar(
                text(
                    "SELECT count(*) FROM jobs WHERE embedding IS NOT NULL "
                    "AND embedding_model=:model"
                ),
                {"model": settings.ACTIVE_EMBEDDING_MODEL},
            )
            or 0
        ) / total
    return RetrievalActivationStatus(
        schema_current=schema_current,
        gin_index_valid=bool(gin and gin.indisvalid),
        hnsw_index_valid=bool(hnsw and hnsw.indisvalid and hnsw.predicate),
        search_document_coverage=search_coverage,
        embedding_coverage=embedding_coverage,
    )


def candidate_pool_size(top_k: int) -> int:
    return min(500, max(100, int(top_k) * 5))


def normalize_weights(dense_weight: float, sparse_weight: float) -> tuple[float, float]:
    if dense_weight < 0 or sparse_weight < 0:
        raise ValueError("Retrieval weights must be non-negative")
    total = dense_weight + sparse_weight
    if total <= 0:
        raise ValueError("Retrieval weight total must be greater than zero")
    return dense_weight / total, sparse_weight / total


def fuse_ranked_ids(
    dense: Sequence[BranchHit],
    lexical: Sequence[BranchHit],
    dense_weight: float,
    sparse_weight: float,
    *,
    max_candidates: Optional[int] = None,
    rrf_k: int = 60,
) -> list[RankedCandidate]:
    dense_weight, sparse_weight = normalize_weights(dense_weight, sparse_weight)
    dense_by_id = {hit.job_id: hit for hit in dense}
    sparse_by_id = {hit.job_id: hit for hit in lexical}
    candidates: list[RankedCandidate] = []

    for job_id in dense_by_id.keys() | sparse_by_id.keys():
        dense_hit = dense_by_id.get(job_id)
        sparse_hit = sparse_by_id.get(job_id)
        score = 0.0
        if dense_hit is not None:
            score += dense_weight / (rrf_k + dense_hit.rank)
        if sparse_hit is not None:
            score += sparse_weight / (rrf_k + sparse_hit.rank)
        candidates.append(
            RankedCandidate(
                job_id=job_id,
                rrf_score=score,
                dense_rank=dense_hit.rank if dense_hit else None,
                dense_score=dense_hit.score if dense_hit else None,
                sparse_rank=sparse_hit.rank if sparse_hit else None,
                sparse_score=sparse_hit.score if sparse_hit else None,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.rrf_score,
            -(candidate.dense_score if candidate.dense_score is not None else -1.0),
            -(candidate.sparse_score if candidate.sparse_score is not None else -1.0),
            candidate.job_id,
        )
    )
    return candidates[:max_candidates] if max_candidates is not None else candidates


def _filter_sql(filters: RetrievalFilters) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict = {}

    for field in ("region", "country_code", "workplace_type", "seniority"):
        value = getattr(filters, field)
        if value and not (field == "region" and value.lower() in {"global", "all"}):
            clauses.append(f"jobs.{field} ILIKE :{field}")
            params[field] = f"%{value.strip()}%"
    if filters.min_salary is not None:
        clauses.append("jobs.salary >= :min_salary")
        params["min_salary"] = filters.min_salary
    if filters.max_salary is not None:
        clauses.append("jobs.salary <= :max_salary")
        params["max_salary"] = filters.max_salary
    if filters.location:
        clauses.append(
            "EXISTS (SELECT 1 FROM cities ci LEFT JOIN states st ON st.id=ci.state_id "
            "WHERE ci.id=jobs.city_id AND (ci.name ILIKE :location OR st.name ILIKE :location))"
        )
        params["location"] = f"%{filters.location.strip()}%"
    if filters.skill:
        clauses.append(
            "(EXISTS (SELECT 1 FROM job_hard_skills jhs JOIN hard_skills hs "
            "ON hs.id=jhs.hard_skill_id WHERE jhs.job_id=jobs.id "
            "AND hs.name ILIKE :skill) OR CAST(jobs.tech_stack AS text) ILIKE :skill)"
        )
        params["skill"] = f"%{filters.skill.strip()}%"

    return (" AND ".join(clauses), params)


class PostgresRetrievalService:
    def __init__(self, db: Session):
        self.db = db

    def _dense_hits(
        self,
        embedding: EmbeddingResult,
        filters: RetrievalFilters,
        pool_size: int,
    ) -> list[BranchHit]:
        pool_size = min(1000, max(1, int(pool_size)))
        self.db.execute(text(f"SET LOCAL hnsw.ef_search = {pool_size}"))
        filter_sql, params = _filter_sql(filters)
        clauses = [
            "jobs.embedding IS NOT NULL",
            "jobs.embedding_model = :active_model",
        ]
        if filter_sql:
            clauses.append(filter_sql)
        vector_literal = "[" + ",".join(str(float(value)) for value in embedding.vector) + "]"
        params.update(
            {
                "active_model": embedding.model,
                "query_embedding": vector_literal,
                "pool_size": pool_size,
            }
        )
        rows = self.db.execute(
            text(
                "SELECT jobs.id AS job_id, "
                "greatest(0.0, least(1.0, 1 - (jobs.embedding <=> "
                "CAST(:query_embedding AS vector)))) AS score "
                "FROM jobs WHERE "
                + " AND ".join(clauses)
                + " ORDER BY jobs.embedding <=> CAST(:query_embedding AS vector), jobs.id ASC "
                "LIMIT :pool_size"
            ),
            params,
        ).all()
        return [
            BranchHit(job_id=int(row.job_id), rank=index, score=float(row.score))
            for index, row in enumerate(rows, start=1)
        ]

    def _lexical_hits(
        self, query: str, filters: RetrievalFilters, pool_size: int
    ) -> list[BranchHit]:
        filter_sql, params = _filter_sql(filters)
        clauses = ["jobs.search_document @@ parsed.query"]
        if filter_sql:
            clauses.append(filter_sql)
        params.update({"query": query, "pool_size": min(1000, max(1, int(pool_size)))})
        rows = self.db.execute(
            text(
                "WITH parsed AS (SELECT websearch_to_tsquery('english', :query) AS query) "
                "SELECT jobs.id AS job_id, "
                "ts_rank_cd(jobs.search_document, parsed.query) AS score "
                "FROM jobs CROSS JOIN parsed WHERE "
                + " AND ".join(clauses)
                + " ORDER BY score DESC, jobs.id ASC LIMIT :pool_size"
            ),
            params,
        ).all()
        return [
            BranchHit(job_id=int(row.job_id), rank=index, score=float(row.score))
            for index, row in enumerate(rows, start=1)
        ]

    def retrieve(
        self,
        query: str,
        filters: RetrievalFilters,
        *,
        top_k: int,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
        dense_pool_size: Optional[int] = None,
        lexical_pool_size: Optional[int] = None,
        max_candidates: Optional[int] = None,
        query_embedding: Optional[EmbeddingResult] = None,
    ) -> RetrievalResult:
        normalized_dense, normalized_sparse = normalize_weights(
            dense_weight, sparse_weight
        )
        default_pool = candidate_pool_size(top_k)
        embedding = query_embedding or embed_query_checked(query)
        dense = self._dense_hits(
            embedding, filters, dense_pool_size or default_pool
        )
        lexical = self._lexical_hits(query, filters, lexical_pool_size or default_pool)
        fused = fuse_ranked_ids(
            dense,
            lexical,
            normalized_dense,
            normalized_sparse,
            max_candidates=max_candidates or top_k,
        )
        mode: Literal["hybrid", "dense", "lexical"]
        if dense and lexical:
            mode = "hybrid"
        elif dense:
            mode = "dense"
        else:
            mode = "lexical"
        return RetrievalResult(tuple(fused), mode)
