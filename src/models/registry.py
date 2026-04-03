from datetime import datetime

from sqlalchemy import DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ParserRegistry(Base):
    __tablename__ = "parser_registry"

    parser_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    route_type: Mapped[str] = mapped_column(String(32))
    form_family: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    model_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_family: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
