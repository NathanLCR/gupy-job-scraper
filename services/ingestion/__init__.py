"""
SkillPulse AI - Multi-Source Public Job Ingestion Adapters & Engine.
"""

from services.ingestion.base_adapter import BaseIngestionAdapter
from services.ingestion.arbeitnow_adapter import ArbeitnowAdapter
from services.ingestion.remotive_adapter import RemotiveAdapter
from services.ingestion.jobicy_adapter import JobicyAdapter
from services.ingestion.himalayas_adapter import HimalayasAdapter
from services.ingestion.remoteok_adapter import RemoteOKAdapter
from services.ingestion.gupy_adapter import GupyAdapter
from services.ingestion.ingestion_manager import IngestionManager, ingestion_manager

__all__ = [
    "BaseIngestionAdapter",
    "ArbeitnowAdapter",
    "RemotiveAdapter",
    "JobicyAdapter",
    "HimalayasAdapter",
    "RemoteOKAdapter",
    "GupyAdapter",
    "IngestionManager",
    "ingestion_manager",
]
