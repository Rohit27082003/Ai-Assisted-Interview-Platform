export interface JDObject {
  role: string;
  must_have_skills: string[];
  good_to_have: string[];
  experience_range: string;
  tools: string[];
  competencies: string[];
}

export interface JobDescription {
  jd_id: string;
  title: string;
  parsed_data: JDObject | null;
  must_have_skills: string[];
  good_to_have_skills: string[];
  experience_range: string | null;
  tools: string[];
  competencies: string[];
  created_at: string;
}

export interface Candidate {
  candidate_id: string;
  jd_id: string;
  name: string;
  email: string;
  resume_s3_url: string | null;
  shortlist_score: number;
  status: string;
  focus_areas: FocusArea[];
  created_at: string;
  interview_id?: string;
  interview_window_start?: string | null;
  interview_window_end?: string | null;
  scoring_analysis?: {
    skills_score: number;
    projects_score: number;
    experience_score: number;
    tooling_score: number;
    vector_score: number;
    final_score: number;
    reasoning?: string;
    pros?: string[];
    cons?: string[];
    red_flags?: string[];
    missing_critical_skills?: string[];
  };
}

export interface FocusArea {
  skill: string;
  reason: string;
}

export interface ShortlistResult {
  candidate_id: string;
  name: string;
  email: string;
  shortlist_score: number;
  skills_match: number;
  projects_match: number;
  experience_match: number;
  tooling_match: number;
  recommended: boolean;
  reasoning?: string;
}

export interface ShortlistResponse {
  jd_id: string;
  total_candidates: number;
  shortlisted: ShortlistResult[];
  rejected: ShortlistResult[];
}

export interface Interview {
  interview_id: string;
  candidate_id: string;
  status: string;
  started_at: string | null;
  current_pillar: string | null;
  question_number: number;
  transcript?: any[];
}

export interface InterviewQuestion {
  question_text: string;
  pillar: string;
  question_number: number;
  is_follow_up: boolean;
  reading_time_seconds: number;
  answer_time_seconds: number;
}

export interface WSMessage {
  type: 'question' | 'timer' | 'cheating_warning' | 'warning' | 'complete' | 'error' | 'terminated' | 'restore_state' | 'transcript_partial';
  data: Record<string, any>;
}

export interface EvaluationItem {
  pillar: string;
  question: string;
  answer: string;
  reference_answer: string;
  correctness: number;
  depth: number;
  reasoning: number;
  clarity: number;
  relevance: number;
  practical_application: number;
  overall_score: number;
  justification: string;
  expected_vs_actual_comparison: string;
  similarity_score: number;
}

export interface EvaluationResponse {
  interview_id: string;
  evaluations: EvaluationItem[];
  average_score: number;
}

export interface Report {
  report_id: string;
  interview_id: string;
  candidate_name: string;
  jd_title: string;
  strengths: string[];
  weaknesses: string[];
  cheating_flags: string[];
  topic_scores: Record<string, number>;
  final_score: number;
  confidence_score: number;
  recommendation: string;
  summary: string;
  detailed_feedback: Record<string, any>;
  created_at: string;
}
