"""SQLAlchemy ORM models for the interview platform."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    Text,
    Enum as SAEnum,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


def gen_uuid():
    return uuid.uuid4()


class CandidateStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    FOCUS_READY = "focus_ready"
    INTERVIEWING = "interviewing"
    INTERVIEWED = "interviewed"
    EVALUATED = "evaluated"
    REPORTED = "reported"


class InterviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class CheatingLevel(str, enum.Enum):
    NONE = "none"
    WARNING_1 = "warning_1"
    WARNING_2 = "warning_2"
    PENALTY = "penalty"


class Recommendation(str, enum.Enum):
    HIRE = "hire"
    NO_HIRE = "no_hire"
    BORDERLINE = "borderline"


# ── Job Descriptions ──────────────────────────────────────────────

class JobDescription(Base):
    __tablename__ = "job_descriptions"

    jd_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    title = Column(String(500), nullable=False)
    raw_text = Column(Text, nullable=False)
    parsed_data = Column(JSONB, nullable=True)  # JD_Object
    must_have_skills = Column(JSONB, default=list)
    good_to_have_skills = Column(JSONB, default=list)
    experience_range = Column(String(100), nullable=True)
    tools = Column(JSONB, default=list)
    competencies = Column(JSONB, default=list)
    chroma_collection_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    candidates = relationship("Candidate", back_populates="job_description", cascade="all, delete-orphan")


# ── Candidates ────────────────────────────────────────────────────

class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    jd_id = Column(UUID(as_uuid=True), ForeignKey("job_descriptions.jd_id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    resume_s3_url = Column(String(1000), nullable=True)
    resume_text = Column(Text, nullable=True)
    resume_vector_id = Column(String(255), nullable=True)
    shortlist_score = Column(Float, default=0.0)
    status = Column(SAEnum(CandidateStatus), default=CandidateStatus.UPLOADED)
    focus_areas = Column(JSONB, default=list)
    graph_state = Column(JSONB, default=dict)
    # Session fields for candidate login
    session_id = Column(String(64), unique=True, nullable=True, index=True)
    session_expires_at = Column(DateTime(timezone=True), nullable=True)
    session_created_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    job_description = relationship("JobDescription", back_populates="candidates")
    interviews = relationship("Interview", back_populates="candidate", cascade="all, delete-orphan")


# ── Interviews ────────────────────────────────────────────────────

class Interview(Base):
    __tablename__ = "interviews"

    interview_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    candidate_id = Column(
        UUID(as_uuid=True), ForeignKey("candidates.candidate_id"), nullable=False
    )
    status = Column(SAEnum(InterviewStatus), default=InterviewStatus.PENDING)
    state_json = Column(JSONB, default=dict)
    current_pillar = Column(String(255), nullable=True)
    question_number = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    cheating_level = Column(SAEnum(CheatingLevel), default=CheatingLevel.NONE)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    candidate = relationship("Candidate", back_populates="interviews")
    transcripts = relationship("Transcript", back_populates="interview", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="interview", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="interview", uselist=False, cascade="all, delete-orphan")


# ── Transcripts ───────────────────────────────────────────────────

class Transcript(Base):
    __tablename__ = "transcripts"

    transcript_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    interview_id = Column(
        UUID(as_uuid=True), ForeignKey("interviews.interview_id"), nullable=False
    )
    pillar = Column(String(255), nullable=True)
    question_number = Column(Integer, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    audio_url = Column(String(1000), nullable=True)
    is_follow_up = Column(Boolean, default=False)
    cheating_flag = Column(SAEnum(CheatingLevel), default=CheatingLevel.NONE)
    cheating_details = Column(JSONB, nullable=True)
    reading_time_used = Column(Float, default=0.0)
    answer_time_used = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    interview = relationship("Interview", back_populates="transcripts")
    evaluation = relationship("Evaluation", back_populates="transcript", uselist=False)


# ── Evaluations ───────────────────────────────────────────────────

class Evaluation(Base):
    __tablename__ = "evaluations"

    evaluation_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    interview_id = Column(
        UUID(as_uuid=True), ForeignKey("interviews.interview_id"), nullable=False
    )
    transcript_id = Column(
        UUID(as_uuid=True), ForeignKey("transcripts.transcript_id"), nullable=True
    )
    pillar = Column(String(255), nullable=True)
    question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    reference_answer = Column(Text, nullable=True)
    correctness = Column(Integer, default=0)
    depth = Column(Integer, default=0)
    reasoning = Column(Integer, default=0)
    clarity = Column(Integer, default=0)
    overall_score = Column(Float, default=0.0)
    justification = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    interview = relationship("Interview", back_populates="evaluations")
    transcript = relationship("Transcript", back_populates="evaluation")


# ── Reports ───────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    interview_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interviews.interview_id"),
        nullable=False,
        unique=True,
    )
    candidate_name = Column(String(255), nullable=True)
    jd_title = Column(String(500), nullable=True)
    strengths = Column(JSONB, default=list)
    weaknesses = Column(JSONB, default=list)
    cheating_flags = Column(JSONB, default=list)
    topic_scores = Column(JSONB, default=dict)
    final_score = Column(Float, default=0.0)
    confidence_score = Column(Float, default=0.0)
    recommendation = Column(SAEnum(Recommendation), default=Recommendation.BORDERLINE)
    summary = Column(Text, nullable=True)
    detailed_feedback = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    interview = relationship("Interview", back_populates="report")


# ── Recruiters ───────────────────────────────────────────────────

class Recruiter(Base):
    """Recruiter users authenticated via AWS Cognito."""
    __tablename__ = "recruiters"

    recruiter_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    cognito_sub = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
