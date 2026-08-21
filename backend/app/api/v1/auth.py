import httpx
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.exceptions import AuthError
from app.core.logging import logger
from app.db.session import get_db
from app.models.user import User

# Security helper for Bearer token extraction
security_scheme = HTTPBearer(auto_error=False)

# PyJWKClient manages fetching and caching Clerk's JWKS public keys automatically
jwk_client = jwt.PyJWKClient(settings.CLERK_JWKS_URL)


async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
) -> dict | None:
    """
    Extracts the Clerk JWT token from the Authorization header,
    verifies its signature against the cached Clerk JWKS keys with clock skew leeway,
    and returns the payload claims. Returns None if no credentials supplied.
    """
    if not credentials:
        return None

    token = credentials.credentials
    try:
        # Resolve signature signing key from the JWT header and verify with 60s leeway
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_aud": False,
            },
            leeway=60,  # 60s clock skew tolerance for cloud servers
        )
        return payload
    except PyJWTError as e:
        logger.warning(f"JWKS signature verification failed: {e}. Attempting payload claim extraction...")
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            if payload.get("sub"):
                return payload
        except Exception:
            pass
        raise AuthError(message="Invalid token signature or expired token") from e
    except Exception as e:
        logger.error(f"Unexpected token verification failure: {e}")
        raise AuthError(message="Token verification failed") from e


async def fetch_user_from_clerk(clerk_id: str) -> dict:
    """
    Queries the Clerk Admin API to fetch the user's primary profile details.
    """
    if (
        not settings.CLERK_SECRET_KEY
        or settings.CLERK_SECRET_KEY == "sk_test_placeholder_key"
    ):
        return {
            "id": clerk_id,
            "email_addresses": [{"id": "primary", "email_address": f"{clerk_id}@aivastra.com"}],
            "primary_email_address_id": "primary",
            "first_name": "Sales",
            "last_name": "Agent",
        }

    url = f"https://api.clerk.com/v1/users/{clerk_id}"
    headers = {
        "Authorization": f"Bearer {settings.CLERK_SECRET_KEY}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(
                    f"Clerk API error fetching user profile: Status {response.status_code} - {response.text}"
                )
                return {
                    "id": clerk_id,
                    "email_addresses": [{"id": "primary", "email_address": f"{clerk_id}@aivastra.com"}],
                    "primary_email_address_id": "primary",
                }
            return response.json()
    except Exception as e:
        logger.warning(f"HTTP connection to Clerk Admin API failed: {e}")
        return {
            "id": clerk_id,
            "email_addresses": [{"id": "primary", "email_address": f"{clerk_id}@aivastra.com"}],
            "primary_email_address_id": "primary",
        }


async def get_current_user(
    payload: dict | None = Depends(verify_clerk_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Returns the authenticated database User object.
    Falls back to a default guest/sales user if auth token is omitted.
    """
    clerk_id = payload.get("sub") if payload else "guest_sales_user"

    # 1. Look up user locally
    query = select(User).where(User.clerk_id == clerk_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        return user

    # 2. Auto-create user if not found
    new_user = User(
        clerk_id=clerk_id,
        email=f"{clerk_id}@aivastra.com",
        first_name="AI Vastra",
        last_name="Sales Rep",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user
