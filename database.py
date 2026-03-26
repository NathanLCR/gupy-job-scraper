from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import urllib.parse
from entities import Base
from dotenv import load_dotenv

load_dotenv()

db_user = urllib.parse.quote_plus(os.getenv('DB_USER', ''))
db_password = urllib.parse.quote_plus(os.getenv('DB_PASSWORD', ''))
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')
DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
