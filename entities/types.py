from typing import Any
from sqlalchemy.types import TypeDecorator, JSON

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - fallback when pgvector is not installed
    class Vector(JSON):  # type: ignore[no-redef]
        """Fallback Vector type that stores embeddings as JSON arrays."""
        def __init__(self, dim: int = 384, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.dim = dim
