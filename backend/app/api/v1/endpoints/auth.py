"""Authentication endpoints (register, login, get current user)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import urllib.parse
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import httpx
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_oauth_token,
    encrypt_oauth_token,
    get_password_hash,
    verify_password,
)
from app.database.session import get_db
from app.models.user import OAuthAccount, User

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)


# --- Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


# --- Current User Dependency ---
async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Return authenticated user or fallback to first active user in local single-user mode."""
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            try:
                user_uuid = uuid.UUID(payload["sub"])
                result = await db.execute(select(User).where(User.id == user_uuid))
                user = result.scalar_one_or_none()
                if user and user.is_active:
                    return user
            except Exception:
                pass

    # In local desktop mode, default to the first active user if present
    result = await db.execute(select(User).where(User.is_active == True).order_by(User.created_at.asc()))
    return result.scalars().first()


# --- Endpoints ---
@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Register a new user account."""
    existing_user = await db.execute(select(User).where(User.email == user_in.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists.",
        )

    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(subject=user.id)
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """OAuth2 compatible token login."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")

    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get the currently authenticated user profile."""
    return current_user


# --- Google Workspace OAuth 2.0 Integration ---
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthUrlResponse(BaseModel):
    configured: bool
    url: Optional[str] = None
    redirect_uri: str
    message: str


class GoogleAuthStatusResponse(BaseModel):
    configured: bool
    connected: bool
    email: Optional[str] = None
    expires_at: Optional[str] = None
    scopes: Optional[str] = None


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    user: Optional[User] = Depends(get_optional_current_user),
) -> Any:
    """Generate the Google Workspace OAuth 2.0 authorization URL."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return GoogleAuthUrlResponse(
            configured=False,
            url=None,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            message="Google OAuth credentials not configured in backend/.env. Enter GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable live sync.",
        )

    state = str(user.id) if user else "nexus_local_operator"
    query_params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(query_params)}"
    return GoogleAuthUrlResponse(
        configured=True,
        url=auth_url,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        message="Google OAuth authorization URL ready.",
    )


@router.get("/google/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle Google OAuth 2.0 authorization redirect and persist encrypted tokens."""
    if error or not code:
        err_msg = error or "Authorization code was not provided by Google."
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: sans-serif; background: #0f172a; color: #f87171; text-align: center; padding: 50px;">
                    <h2>Google Authorization Failed</h2>
                    <p>{err_msg}</p>
                    <a href="{settings.FRONTEND_URL}" style="color: #38bdf8;">Return to Nexus</a>
                </body>
            </html>
            """,
            status_code=400,
        )

    # Exchange authorization code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(token_url, data=token_payload)
            if token_resp.status_code != 200:
                return HTMLResponse(
                    content=f"""
                    <html>
                        <body style="font-family: sans-serif; background: #0f172a; color: #f87171; text-align: center; padding: 50px;">
                            <h2>Token Exchange Error</h2>
                            <pre style="text-align: left; background: #1e293b; padding: 15px; border-radius: 8px;">{token_resp.text}</pre>
                            <a href="{settings.FRONTEND_URL}" style="color: #38bdf8;">Return to Nexus</a>
                        </body>
                    </html>
                    """,
                    status_code=400,
                )

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            granted_scopes = token_data.get("scope", "")

            # Fetch Google user profile
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo = userinfo_resp.json() if userinfo_resp.status_code == 200 else {}
            google_email = userinfo.get("email", "unknown@gmail.com")
            google_sub = userinfo.get("id", str(uuid.uuid4()))

        # Determine target user
        user = None
        if state and state != "nexus_local_operator":
            try:
                user_uuid = uuid.UUID(state)
                u_res = await db.execute(select(User).where(User.id == user_uuid))
                user = u_res.scalar_one_or_none()
            except Exception:
                pass

        if not user:
            # Match by email or get first active user or create local user
            u_res = await db.execute(select(User).where(User.email == google_email))
            user = u_res.scalar_one_or_none()

        if not user:
            # Fall back to first user in system
            u_res = await db.execute(select(User).where(User.is_active == True).order_by(User.created_at.asc()))
            user = u_res.scalars().first()

        if not user:
            # Auto-provision operator user
            user = User(
                email=google_email,
                hashed_password=get_password_hash(uuid.uuid4().hex),
                full_name=userinfo.get("name", "Google User"),
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Store or update OAuth Account record
        oa_res = await db.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user.id,
                OAuthAccount.provider == "google",
            )
        )
        oauth_account = oa_res.scalar_one_or_none()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        enc_access = encrypt_oauth_token(access_token)
        enc_refresh = encrypt_oauth_token(refresh_token) if refresh_token else (oauth_account.encrypted_refresh_token if oauth_account else None)

        if oauth_account:
            oauth_account.encrypted_access_token = enc_access
            if enc_refresh:
                oauth_account.encrypted_refresh_token = enc_refresh
            oauth_account.scopes = granted_scopes
            oauth_account.expires_at = expires_at
            oauth_account.provider_user_id = google_sub
        else:
            oauth_account = OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_user_id=google_sub,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                scopes=granted_scopes,
                expires_at=expires_at,
            )
            db.add(oauth_account)

        await db.commit()

        # Render successful connection page with auto-close / redirect
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Nexus - Google Workspace Connected</title>
                    <style>
                        body {{
                            background-color: #0b0f19;
                            color: #f8fafc;
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                        }}
                        .card {{
                            background: #111827;
                            border: 1px solid #1f2937;
                            border-radius: 16px;
                            padding: 40px;
                            text-align: center;
                            max-width: 440px;
                            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
                        }}
                        .icon {{
                            font-size: 48px;
                            margin-bottom: 16px;
                        }}
                        h2 {{
                            margin: 0 0 10px 0;
                            color: #38bdf8;
                        }}
                        p {{
                            color: #94a3b8;
                            font-size: 14px;
                            line-height: 1.5;
                        }}
                        .btn {{
                            display: inline-block;
                            margin-top: 20px;
                            padding: 10px 24px;
                            background: #4f46e5;
                            color: white;
                            text-decoration: none;
                            border-radius: 8px;
                            font-weight: 600;
                        }}
                    </style>
                </head>
                <body>
                    <div class="card">
                        <div class="icon">✨</div>
                        <h2>Google Workspace Connected!</h2>
                        <p>Connected account: <strong>{google_email}</strong></p>
                        <p>Gmail and Google Calendar are now synchronized with your Nexus Agentic AI Assistant.</p>
                        <a href="{settings.FRONTEND_URL}?google_auth=success" class="btn" id="closeBtn">Return to Dashboard</a>
                    </div>
                    <script>
                        if (window.opener) {{
                            window.opener.postMessage({{ type: 'GOOGLE_CONNECTED', email: '{google_email}' }}, '*');
                            setTimeout(() => {{ window.close(); }}, 1200);
                        }} else {{
                            setTimeout(() => {{ window.location.href = '{settings.FRONTEND_URL}?google_auth=success'; }}, 2000);
                        }}
                    </script>
                </body>
            </html>
            """
        )

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: sans-serif; background: #0f172a; color: #f87171; text-align: center; padding: 50px;">
                    <h2>OAuth Processing Error</h2>
                    <p>{str(e)}</p>
                    <a href="{settings.FRONTEND_URL}" style="color: #38bdf8;">Return to Nexus</a>
                </body>
            </html>
            """,
            status_code=500,
        )


@router.get("/google/status", response_model=GoogleAuthStatusResponse)
async def get_google_auth_status(
    user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Check whether Google Workspace OAuth credentials and an active connection exist."""
    is_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    if not user:
        return GoogleAuthStatusResponse(
            configured=is_configured,
            connected=False,
            email=None,
            expires_at=None,
            scopes=None,
        )

    stmt = select(OAuthAccount).where(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider == "google",
    )
    result = await db.execute(stmt)
    oa = result.scalar_one_or_none()

    if not oa or not oa.encrypted_access_token:
        return GoogleAuthStatusResponse(
            configured=is_configured,
            connected=False,
            email=None,
            expires_at=None,
            scopes=None,
        )

    return GoogleAuthStatusResponse(
        configured=is_configured,
        connected=True,
        email=user.email,
        expires_at=oa.expires_at.isoformat() if oa.expires_at else None,
        scopes=oa.scopes,
    )


@router.post("/google/disconnect")
async def disconnect_google_workspace(
    user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Disconnect and revoke Google Workspace integration for the active operator."""
    if not user:
        raise HTTPException(status_code=400, detail="No active user found.")

    stmt = select(OAuthAccount).where(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider == "google",
    )
    result = await db.execute(stmt)
    oa = result.scalar_one_or_none()
    if oa:
        await db.delete(oa)
        await db.commit()

    return {"success": True, "message": "Google Workspace integration disconnected successfully."}
