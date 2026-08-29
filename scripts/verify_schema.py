"""Read-only schema gate for worker startup."""

from services.readiness_service import check_database_readiness


def main() -> int:
    result = check_database_readiness(timeout_seconds=5.0)
    if result.ready:
        print("Database schema is current.")
        return 0
    print(f"Database schema verification failed: {result.failure_category or 'unknown'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
