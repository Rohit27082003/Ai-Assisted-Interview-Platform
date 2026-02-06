"""Authentication middleware for protecting routes."""

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Candidate
from app.services.aws.cognito_service import get_cognito_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# Security scheme for Bearer tokens
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents an authenticated recruiter user."""
    
    def __init__(
        self,
        sub: str,
        email: str,
        name: str,
        access_token: str,
    ):
        self.sub = sub  # Cognito user ID
        self.email = email
        self.name = name
        self.access_token = access_token


class AuthenticatedCandidate:
    """Represents an authenticated candidate via session."""
    
    def __init__(
        self,
        candidate_id: UUID,
        email: str,
        name: str,
        session_id: str,
        jd_id: UUID,
    ):
        self.candidate_id = candidate_id
        self.email = email
        self.name = name
        self.session_id = session_id
        self.jd_id = jd_id


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    Extract and validate the current user from Bearer token.
    Returns None if no token or invalid token.
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    cognito = get_cognito_service()
    
    # Validate token
    payload = await cognito.validate_token(token)
    if not payload:
        return None
    
    # Get user info
    user_info = await cognito.get_user_info(token)
    if not user_info:
        return None
    
    return AuthenticatedUser(
        sub=user_info.get("sub", ""),
        email=user_info.get("email", ""),
        name=user_info.get("name", ""),
        access_token=token,
    )


async def require_recruiter(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Dependency that requires a valid recruiter authentication.
    Raises 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    cognito = get_cognito_service()
    
    # Validate token
    payload = await cognito.validate_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user info
    user_info = await cognito.get_user_info(token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not retrieve user information",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Authenticated recruiter: {user_info.get('email')}")
    
    return AuthenticatedUser(
        sub=user_info.get("sub", ""),
        email=user_info.get("email", ""),
        name=user_info.get("name", ""),
        access_token=token,
    )


async def get_candidate_from_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[AuthenticatedCandidate]:
    """
    Extract and validate candidate from session token in header.
    Returns None if no session or invalid session.
    """
    session_token = request.headers.get("X-Candidate-Session")
    if not session_token:
        return None
    
    # Parse session token (format: session_id:email)
    try:
        parts = session_token.split(":", 1)
        if len(parts) != 2:
            return None
        session_id, email = parts
    except Exception:
        return None
    
    # Find candidate with matching session
    result = await db.execute(
        select(Candidate).where(
            Candidate.session_id == session_id,
            Candidate.email == email,
        )
    )
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        return None
    
    # Check session expiry
    if candidate.session_expires_at:
        if candidate.session_expires_at < datetime.now(timezone.utc):
            logger.warning(f"Session expired for candidate: {candidate.candidate_id}")
            return None
    
    return AuthenticatedCandidate(
        candidate_id=candidate.candidate_id,
        email=candidate.email,
        name=candidate.name,
        session_id=session_id,
        jd_id=candidate.jd_id,
    )


async def require_candidate_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedCandidate:
    """
    Dependency that requires a valid candidate session.
    Raises 401 if not authenticated.
    """
    candidate = await get_candidate_from_session(request, db)
    
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired candidate session",
            headers={"WWW-Authenticate": "X-Candidate-Session"},
        )
    
    logger.info(f"Authenticated candidate: {candidate.email}")
    return candidate


def generate_session_id(length: int = 32) -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(length)
