"""AWS Cognito authentication service for recruiter login."""

import boto3
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class CognitoService:
    """Handles AWS Cognito authentication for recruiters."""

    def __init__(self):
        self.user_pool_id = settings.COGNITO_USER_POOL_ID
        self.client_id = settings.COGNITO_APP_CLIENT_ID
        
        # Derive region from user_pool_id (e.g., "ap-south-1_xxxx" -> "ap-south-1")
        self.region = self.user_pool_id.split("_")[0] if "_" in self.user_pool_id else settings.AWS_REGION
        
        self.client = boto3.client(
            "cognito-idp",
            region_name=self.region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        self._jwks = None
        self._jwks_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/"
            f"{self.user_pool_id}/.well-known/jwks.json"
        )

    async def _get_jwks(self) -> Dict[str, Any]:
        """Fetch JSON Web Key Set from Cognito for token validation."""
        if self._jwks is None:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self._jwks_url)
                    self._jwks = response.json()
            except Exception as e:
                logger.error(f"Failed to fetch JWKS: {e}")
                raise
        return self._jwks

    async def authenticate(
        self, email: str, password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate a recruiter with email and password using SRP.
        
        Returns tokens on success, None on failure.
        """
        try:
            # Use pycognito for SRP authentication (works without USER_PASSWORD_AUTH enabled)
            from pycognito import Cognito
            
            u = Cognito(
                self.user_pool_id,
                self.client_id,
                username=email,
            )
            u.authenticate(password=password)
            
            return {
                "access_token": u.access_token,
                "id_token": u.id_token,
                "refresh_token": u.refresh_token,
                "expires_in": 3600,  # Default expiry
                "token_type": "Bearer",
            }
        except Exception as e:
            error_msg = str(e)
            if "NotAuthorizedException" in error_msg or "UserNotFoundException" in error_msg:
                logger.warning(f"Authentication failed for user: {email}")
            else:
                logger.error(f"Authentication error: {e}")
            return None


    async def sign_up(
        self, email: str, password: str, name: str, phone_number: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Register a new recruiter user in Cognito.
        
        Returns user_sub on success, None on failure.
        """
        try:
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
            ]
            
            # Add phone number if provided (some Cognito pools require it)
            if phone_number:
                user_attributes.append({"Name": "phone_number", "Value": phone_number})
            
            response = self.client.sign_up(
                ClientId=self.client_id,
                Username=email,
                Password=password,
                UserAttributes=user_attributes,
            )
            
            return {
                "user_sub": response.get("UserSub"),
                "requires_confirmation": not response.get("UserConfirmed", False),
            }
        except self.client.exceptions.UsernameExistsException:
            logger.warning(f"User already exists: {email}")
            return None
        except self.client.exceptions.InvalidPasswordException as e:
            logger.warning(f"Invalid password: {e}")
            return None
        except self.client.exceptions.InvalidParameterException as e:
            logger.error(f"Invalid parameter: {e}")
            return None
        except Exception as e:
            logger.error(f"Sign up error: {e}")
            return None

    async def confirm_sign_up(self, email: str, confirmation_code: str) -> bool:
        """Confirm a user's email with the confirmation code."""
        try:
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                Username=email,
                ConfirmationCode=confirmation_code,
            )
            return True
        except Exception as e:
            logger.error(f"Confirmation failed: {e}")
            return False

    async def resend_confirmation_code(self, email: str) -> bool:
        """Resend the confirmation code to the user's email."""
        try:
            self.client.resend_confirmation_code(
                ClientId=self.client_id,
                Username=email,
            )
            return True
        except Exception as e:
            logger.error(f"Resend confirmation code failed: {e}")
            return False

    async def refresh_tokens(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh access token using refresh token."""
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={
                    "REFRESH_TOKEN": refresh_token,
                },
            )
            
            auth_result = response.get("AuthenticationResult", {})
            
            return {
                "access_token": auth_result.get("AccessToken"),
                "id_token": auth_result.get("IdToken"),
                "expires_in": auth_result.get("ExpiresIn"),
                "token_type": auth_result.get("TokenType", "Bearer"),
            }
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return None

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a Cognito JWT token.
        
        Returns decoded token payload if valid, None otherwise.
        """
        try:
            # Get JWKS for validation
            jwks = await self._get_jwks()
            
            # Get the key id from token header
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            
            # Find matching key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break
            
            if not key:
                logger.warning("No matching key found in JWKS")
                return None
            
            # Validate and decode token
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}",
            )
            
            return payload
            
        except ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except JWTError as e:
            logger.warning(f"Token validation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None

    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from Cognito using access token."""
        try:
            response = self.client.get_user(AccessToken=access_token)
            
            # Convert attributes list to dict
            attributes = {}
            for attr in response.get("UserAttributes", []):
                attributes[attr["Name"]] = attr["Value"]
            
            return {
                "username": response.get("Username"),
                "sub": attributes.get("sub"),
                "email": attributes.get("email"),
                "email_verified": attributes.get("email_verified") == "true",
                "name": attributes.get("name", attributes.get("email", "")),
            }
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    async def sign_out(self, access_token: str) -> bool:
        """Sign out user (invalidate tokens)."""
        try:
            self.client.global_sign_out(AccessToken=access_token)
            return True
        except Exception as e:
            logger.error(f"Sign out failed: {e}")
            return False


# Singleton instance
_cognito_service: Optional[CognitoService] = None


def get_cognito_service() -> CognitoService:
    """Get or create CognitoService singleton."""
    global _cognito_service
    if _cognito_service is None:
        _cognito_service = CognitoService()
    return _cognito_service
