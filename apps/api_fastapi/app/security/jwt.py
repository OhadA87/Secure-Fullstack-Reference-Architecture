import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from jose import JWTError, jwt
from pydantic import BaseModel

from ..config import settings

logger = structlog.get_logger()


class TokenData(BaseModel):
    user_id: str
    email: str
    roles: List[str]
    token_type: str  # "access" or "refresh"


class JWTTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class JWTManager:
    """JWT token management for access and refresh tokens."""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        self.audience = settings.JWT_AUDIENCE
        self.issuer = settings.JWT_ISSUER
    
    def create_access_token(self, user_id: str, email: str, roles: List[str]) -> str:
        """Create an access token with standard claims."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        
        payload = {
            "sub": user_id,  # Subject (user ID)
            "email": email,
            "roles": roles,
            "token_type": "access",
            "exp": expire,  # Expiration time
            "iat": now,     # Issued at
            "aud": self.audience,  # Audience
            "iss": self.issuer,    # Issuer
            "jti": str(uuid.uuid4()),  # JWT ID
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: str, email: str) -> str:
        """Create a refresh token with minimal claims."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            "sub": user_id,
            "email": email,
            "token_type": "refresh",
            "exp": expire,
            "iat": now,
            "aud": self.audience,
            "iss": self.issuer,
            "jti": str(uuid.uuid4()),
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_tokens(self, user_id: str, email: str, roles: List[str]) -> JWTTokens:
        """Create both access and refresh tokens."""
        access_token = self.create_access_token(user_id, email, roles)
        refresh_token = self.create_refresh_token(user_id, email)
        
        return JWTTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60
        )
    
    def decode_token(self, token: str) -> Optional[TokenData]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer
            )
            
            # Validate required claims
            user_id = payload.get("sub")
            email = payload.get("email")
            token_type = payload.get("token_type")
            
            if not all([user_id, email, token_type]):
                logger.warning("jwt_decode_missing_claims", payload=payload)
                return None
            
            # Get roles (only present in access tokens)
            roles = payload.get("roles", [])
            
            return TokenData(
                user_id=user_id,
                email=email,
                roles=roles,
                token_type=token_type
            )
            
        except JWTError as e:
            logger.warning("jwt_decode_error", error=str(e), token_length=len(token))
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Generate a new access token from a valid refresh token."""
        token_data = self.decode_token(refresh_token)
        
        if not token_data or token_data.token_type != "refresh":
            return None
        
        # TODO: Get user roles from database
        # For now, return default user role
        user_roles = ["user"]
        
        return self.create_access_token(
            user_id=token_data.user_id,
            email=token_data.email,
            roles=user_roles
        )
    
    def extract_token_from_header(self, authorization: str) -> Optional[str]:
        """Extract token from Authorization header."""
        if not authorization:
            return None
        
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                return None
            return token
        except ValueError:
            return None


# Global JWT manager instance
jwt_manager = JWTManager()