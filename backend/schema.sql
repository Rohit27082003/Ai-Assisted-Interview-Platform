-- AI Interview Orchestrator - PostgreSQL Schema
-- Run this to initialize the database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum types
CREATE TYPE candidate_status AS ENUM (
    'uploaded', 'parsed', 'shortlisted', 'rejected',
    'focus_ready', 'interviewing', 'interviewed',
    'evaluated', 'reported'
);

CREATE TYPE interview_status AS ENUM (
    'pending', 'in_progress', 'completed', 'terminated'
);

CREATE TYPE cheating_level AS ENUM (
    'none', 'warning_1', 'warning_2', 'penalty'
);

CREATE TYPE recommendation_type AS ENUM (
    'hire', 'no_hire', 'borderline'
);

-- Recruiters
CREATE TABLE recruiters (
    recruiter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cognito_sub VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Job Descriptions
CREATE TABLE job_descriptions (
    jd_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    raw_text TEXT NOT NULL,
    parsed_data JSONB,
    must_have_skills JSONB DEFAULT '[]'::jsonb,
    good_to_have_skills JSONB DEFAULT '[]'::jsonb,
    experience_range VARCHAR(100),
    tools JSONB DEFAULT '[]'::jsonb,
    competencies JSONB DEFAULT '[]'::jsonb,
    chroma_collection_id VARCHAR(255),
    recruiter_id UUID REFERENCES recruiters(recruiter_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Candidates
CREATE TABLE candidates (
    candidate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jd_id UUID NOT NULL REFERENCES job_descriptions(jd_id),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    resume_s3_url VARCHAR(1000),
    resume_text TEXT,
    resume_vector_id VARCHAR(255),
    shortlist_score FLOAT DEFAULT 0.0,
    status candidate_status DEFAULT 'uploaded',
    focus_areas JSONB DEFAULT '[]'::jsonb,
    graph_state JSONB DEFAULT '{}'::jsonb,
    session_id VARCHAR(64) UNIQUE,
    session_expires_at TIMESTAMPTZ,
    session_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Interviews
CREATE TABLE interviews (
    interview_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(candidate_id),
    status interview_status DEFAULT 'pending',
    state_json JSONB DEFAULT '{}'::jsonb,
    current_pillar VARCHAR(255),
    question_number INTEGER DEFAULT 0,
    total_questions INTEGER DEFAULT 0,
    cheating_level cheating_level DEFAULT 'none',
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Transcripts
CREATE TABLE transcripts (
    transcript_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID NOT NULL REFERENCES interviews(interview_id),
    pillar VARCHAR(255),
    question_number INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    audio_url VARCHAR(1000),
    is_follow_up BOOLEAN DEFAULT FALSE,
    cheating_flag cheating_level DEFAULT 'none',
    cheating_details JSONB,
    reading_time_used FLOAT DEFAULT 0.0,
    answer_time_used FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evaluations
CREATE TABLE evaluations (
    evaluation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID NOT NULL REFERENCES interviews(interview_id),
    transcript_id UUID REFERENCES transcripts(transcript_id),
    pillar VARCHAR(255),
    question TEXT,
    answer TEXT,
    reference_answer TEXT,
    correctness INTEGER DEFAULT 0,
    depth INTEGER DEFAULT 0,
    reasoning INTEGER DEFAULT 0,
    clarity INTEGER DEFAULT 0,
    overall_score FLOAT DEFAULT 0.0,
    justification TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reports
CREATE TABLE reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interview_id UUID NOT NULL UNIQUE REFERENCES interviews(interview_id),
    candidate_name VARCHAR(255),
    jd_title VARCHAR(500),
    strengths JSONB DEFAULT '[]'::jsonb,
    weaknesses JSONB DEFAULT '[]'::jsonb,
    cheating_flags JSONB DEFAULT '[]'::jsonb,
    topic_scores JSONB DEFAULT '{}'::jsonb,
    final_score FLOAT DEFAULT 0.0,
    confidence_score FLOAT DEFAULT 0.0,
    recommendation recommendation_type DEFAULT 'borderline',
    summary TEXT,
    detailed_feedback JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_candidates_jd_id ON candidates(jd_id);
CREATE INDEX idx_candidates_status ON candidates(status);
CREATE INDEX idx_interviews_candidate_id ON interviews(candidate_id);
CREATE INDEX idx_interviews_status ON interviews(status);
CREATE INDEX idx_transcripts_interview_id ON transcripts(interview_id);
CREATE INDEX idx_evaluations_interview_id ON evaluations(interview_id);
CREATE INDEX idx_reports_interview_id ON reports(interview_id);
CREATE INDEX idx_recruiters_cognito_sub ON recruiters(cognito_sub);
CREATE INDEX idx_recruiters_email ON recruiters(email);
CREATE INDEX idx_job_descriptions_recruiter_id ON job_descriptions(recruiter_id);
