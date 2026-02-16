import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from server.database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class Run(Base):
    __tablename__ = "runs"

    id = Column(String(36), primary_key=True, default=uuid_str)
    entity_type = Column(String(32), nullable=False)  # contact | company
    source_type = Column(String(32), nullable=False, default="csv")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    params_json = Column(Text, nullable=True)  # JSON string
    status = Column(String(32), nullable=False, default="running")  # running | completed | failed

    entities = relationship("Entity", back_populates="run")
    matches = relationship("Match", back_populates="run")
    clusters = relationship("Cluster", back_populates="run")
    actions = relationship("Action", back_populates="run")


class Entity(Base):
    __tablename__ = "entities"

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    external_id = Column(String(256), nullable=False)
    raw_json = Column(Text, nullable=True)  # JSON string

    run = relationship("Run", back_populates="entities")
    matches_as_a = relationship("Match", foreign_keys="Match.a_entity_id", back_populates="entity_a")
    matches_as_b = relationship("Match", foreign_keys="Match.b_entity_id", back_populates="entity_b")
    recommended_in_matches = relationship("Match", foreign_keys="Match.recommended_survivor_entity_id")

    __table_args__ = (Index("ix_entities_run_id", "run_id"),)


class Match(Base):
    __tablename__ = "matches"

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    a_entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    b_entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    score = Column(Float, nullable=False)
    reasons_json = Column(Text, nullable=True)  # JSON array of { feature, weight, detail }
    recommended_survivor_entity_id = Column(String(36), ForeignKey("entities.id"), nullable=True)
    status = Column(String(32), nullable=False, default="unreviewed")  # unreviewed | approved | rejected
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    run = relationship("Run", back_populates="matches")
    entity_a = relationship("Entity", foreign_keys=[a_entity_id], back_populates="matches_as_a")
    entity_b = relationship("Entity", foreign_keys=[b_entity_id], back_populates="matches_as_b")
    recommended_survivor = relationship("Entity", foreign_keys=[recommended_survivor_entity_id])

    __table_args__ = (
        Index("ix_matches_run_id_status", "run_id", "status"),
        Index("ix_matches_run_id_score", "run_id", "score"),
    )


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    member_entity_ids_json = Column(Text, nullable=False)  # JSON array of entity UUIDs
    recommended_survivor_entity_id = Column(String(36), ForeignKey("entities.id"), nullable=True)

    run = relationship("Run", back_populates="clusters")
    recommended_survivor = relationship("Entity", foreign_keys=[recommended_survivor_entity_id])

    __table_args__ = (Index("ix_clusters_run_id", "run_id"),)


class Action(Base):
    __tablename__ = "actions"

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    actor = Column(String(64), nullable=False, default="local")
    action_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    run = relationship("Run", back_populates="actions")
