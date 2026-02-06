"""Authentication routes for recruiter and candidate login."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Candidate
from app.services.aws.cognito_service import get_cognito_service
from app.api.middleware.auth_middleware import (
    require_recruiter,
    AuthenticatedUser,
    generate_session_id,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ── Request/Response Schemas ─────────────────────────────────────


class RecruiterLoginRequest(BaseModel):
    email: EmailStr
    password: str


class RecruiterSignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone_number: Optional[str] = None  # Optional, format: +1234567890


class TokenResponse(BaseModel):
    access_token: str
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: int
    token_type: str = "Bearer"


class SignupResponse(BaseModel):
    message: str
    user_sub: Optional[str] = None
    requires_confirmation: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfoResponse(BaseModel):
    sub: str
    email: str
    name: str


class CandidateLoginRequest(BaseModel):
    session_id: str
    email: EmailStr


class CandidateLoginResponse(BaseModel):
    candidate_id: UUID
    name: str
    email: str
    session_token: str
    job_title: str
    can_start_interview: bool
    interview_status: Optional[str] = None
    interview_id: Optional[UUID] = None


# ── Recruiter Authentication Routes ──────────────────────────────


@router.post("/signup", response_model=SignupResponse)
async def recruiter_signup(
    request: RecruiterSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new recruiter account.
    
    Creates a new user in AWS Cognito and stores recruiter info in database.
    """
    cognito = get_cognito_service()
    
    # Register with Cognito
    result = await cognito.sign_up(
        email=request.email,
        password=request.password,
        name=request.name,
        phone_number=request.phone_number,
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Email may already be registered.",
        )
    
    # Store recruiter in database
    from app.models.models import Recruiter
    recruiter = Recruiter(
        cognito_sub=result.get("user_sub", ""),
        email=request.email,
        name=request.name,
    )
    db.add(recruiter)
    await db.commit()
    
    logger.info(f"Recruiter registered: {request.email}")
    
    return SignupResponse(
        message="Registration successful. Please check your email for confirmation.",
        user_sub=result.get("user_sub"),
        requires_confirmation=result.get("requires_confirmation", True),
    )


class ConfirmSignupRequest(BaseModel):
    email: EmailStr
    confirmation_code: str


class ResendCodeRequest(BaseModel):
    email: EmailStr


@router.post("/confirm-signup")
async def confirm_signup(request: ConfirmSignupRequest):
    """
    Confirm a recruiter account with the OTP code sent via email.
    """
    cognito = get_cognito_service()
    
    success = await cognito.confirm_sign_up(
        email=request.email,
        confirmation_code=request.confirmation_code,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation code.",
        )
    
    logger.info(f"Recruiter confirmed: {request.email}")
    return {"message": "Account confirmed successfully. You can now log in."}


@router.post("/resend-code")
async def resend_confirmation_code(request: ResendCodeRequest):
    """
    Resend the confirmation code to the user's email.
    """
    cognito = get_cognito_service()
    
    success = await cognito.resend_confirmation_code(request.email)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to resend confirmation code.",
        )
    
    return {"message": "Confirmation code sent. Please check your email."}

@router.post("/login", response_model=TokenResponse)
async def recruiter_login(request: RecruiterLoginRequest):
    """
    Authenticate recruiter with email and password.
    
    Returns access tokens on successful authentication.
    """
    cognito = get_cognito_service()
    
    result = await cognito.authenticate(request.email, request.password)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    logger.info(f"Recruiter logged in: {request.email}")
    
    return TokenResponse(
        access_token=result["access_token"],
        id_token=result.get("id_token"),
        refresh_token=result.get("refresh_token"),
        expires_in=result.get("expires_in", 3600),
        token_type=result.get("token_type", "Bearer"),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.
    """
    cognito = get_cognito_service()
    
    result = await cognito.refresh_tokens(request.refresh_token)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    return TokenResponse(
        access_token=result["access_token"],
        id_token=result.get("id_token"),
        expires_in=result.get("expires_in", 3600),
        token_type=result.get("token_type", "Bearer"),
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """
    Get current authenticated recruiter's information.
    """
    return UserInfoResponse(
        sub=user.sub,
        email=user.email,
        name=user.name,
    )


@router.post("/logout")
async def recruiter_logout(
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """
    Sign out the current recruiter (invalidate tokens).
    """
    cognito = get_cognito_service()
    
    success = await cognito.sign_out(user.access_token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed",
        )
    
    logger.info(f"Recruiter logged out: {user.email}")
    
    return {"message": "Successfully logged out"}


# ── Candidate Session Routes ─────────────────────────────────────


@router.post("/candidate/login", response_model=CandidateLoginResponse)
async def candidate_login(
    request: CandidateLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate candidate with session ID and email.
    
    Returns session token and interview information.
    """
    # Find candidate with matching session
    result = await db.execute(
        select(Candidate).where(
            Candidate.session_id == request.session_id,
            Candidate.email == request.email,
        )
    )
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session ID or email",
        )
    
    # Check session expiry
    if candidate.session_expires_at:
        if candidate.session_expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired. Please contact the recruiter.",
            )
    
    # Get job description
    from app.models.models import JobDescription
    jd = await db.get(JobDescription, candidate.jd_id)
    job_title = jd.title if jd else "Unknown Position"
    
    # Check interview status
    from app.models.models import Interview, InterviewStatus, CandidateStatus
    interview_result = await db.execute(
        select(Interview).where(Interview.candidate_id == candidate.candidate_id)
    )
    interview = interview_result.scalar_one_or_none()
    
    # Determine if candidate can start interview
    can_start = candidate.status in (
        CandidateStatus.SHORTLISTED,
        CandidateStatus.FOCUS_READY,
    )
    
    interview_status = None
    interview_id = None
    if interview:
        interview_status = interview.status.value if interview.status else None
        interview_id = interview.interview_id
        can_start = interview.status == InterviewStatus.PENDING
    
    # Generate session token (session_id:email format)
    session_token = f"{request.session_id}:{request.email}"
    
    logger.info(f"Candidate logged in: {candidate.email}")
    
    return CandidateLoginResponse(
        candidate_id=candidate.candidate_id,
        name=candidate.name,
        email=candidate.email,
        session_token=session_token,
        job_title=job_title,
        can_start_interview=can_start,
        interview_status=interview_status,
        interview_id=interview_id,
    )


@router.get("/candidate/validate")
async def validate_candidate_session(
    session_id: str,
    email: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a candidate session without full login.
    
    Used to check if session is valid before showing login form.
    """
    result = await db.execute(
        select(Candidate).where(
            Candidate.session_id == session_id,
            Candidate.email == email,
        )
    )
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        return {"valid": False, "reason": "Invalid session"}
    
    if candidate.session_expires_at:
        if candidate.session_expires_at < datetime.now(timezone.utc):
            return {"valid": False, "reason": "Session expired"}
    
    return {
        "valid": True,
        "candidate_name": candidate.name,
    }
