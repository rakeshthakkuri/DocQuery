from fastapi import APIRouter, Request, Depends, HTTPException, status
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import User
from .oauth import oauth

load_dotenv()
router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set. Please generate a strong secret key.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/google/login", summary="Initiate Google OAuth2 login")
async def login(request: Request):
    """
    Redirects the user to Google's authentication page.
    """
    redirect_uri = request.url_for('auth_callback')
    
    # Clear any existing session data to prevent state conflicts
    if hasattr(request, 'session'):
        request.session.clear()
    
    return await oauth.google.authorize_redirect(
        request, 
        redirect_uri,
        state=None  # Let authlib generate a fresh state
    )

@router.get("/google/callback", name="auth_callback", summary="Google OAuth2 callback endpoint")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handles the callback from Google after successful authentication.
    Retrieves user information, creates/updates user in DB, and issues a JWT token.
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        error_msg = str(e)
        print(f"OAuth callback error: {error_msg}")  # Debug logging
        
        # Handle specific CSRF state mismatch error
        if "mismatching_state" in error_msg or "CSRF Warning" in error_msg:
            # Redirect to login page with error message
            frontend_redirect_url = os.getenv("FRONTEND_REDIRECT_URL", "https://docquerytest2.onrender.com/app.html")
            error_redirect_url = f"{frontend_redirect_url}?error=csrf_state_mismatch"
            return RedirectResponse(url=error_redirect_url)
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed during token exchange: {e}"
        )

    user_info = token.get("userinfo")
    if not user_info:
        try:
            user_info = await oauth.google.parse_id_token(request, token)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse ID token: {e}"
            )

    if not user_info or not user_info.get("sub") or not user_info.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google login failed: Incomplete user information received."
        )

    user_email = user_info["email"].lower() # Get the email and convert to lowercase for consistent comparison
    # Check if user exists in our database
    user = db.query(User).filter(User.id == user_info["sub"]).first()
    if not user:
        # Create new user if they don't exist
        user = User(
            id=user_info["sub"],
            name=user_info.get("name", "Unknown"),
            email=user_info["email"],
            picture=user_info.get("picture", None)
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create JWT token
    payload = {"sub": user.id, "name": user.name, "email": user.email}
    jwt_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # Redirect to the frontend with the JWT token
    frontend_redirect_url = os.getenv("FRONTEND_REDIRECT_URL")
    redirect_url = f"{frontend_redirect_url}?token={jwt_token}"

    return RedirectResponse(url=redirect_url)