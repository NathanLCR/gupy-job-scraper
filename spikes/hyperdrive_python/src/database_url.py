from sqlalchemy.engine import make_url


def build_sqlalchemy_url(hyperdrive_connection_string: str) -> str:
    """Adapt Hyperdrive's PostgreSQL URL for SQLAlchemy's pure-Python driver."""
    url = make_url(hyperdrive_connection_string)
    url = url.set(drivername="postgresql+pg8000")
    url = url.difference_update_query(["sslmode"])
    return url.render_as_string(hide_password=False)
