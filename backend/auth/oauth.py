from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from database import SessionLocal # Adjusted import path, direct import from backend/
from models import User # Adjusted import path, direct import from backend/

load_dotenv()

# --- OAuth2 Client Setup ---
config_data = {
    "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
    "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
}

config = Config(environ=config_data)

oauth = OAuth(config)

oauth.register(
    name='google',
    client_id=config_data["GOOGLE_CLIENT_ID"],
    client_secret=config_data["GOOGLE_CLIENT_SECRET"],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# --- JWT Authentication Setup ---
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set. Please generate a strong secret key.")

# This is the FastAPI dependency that looks for a bearer token in the Authorization header
# The `tokenUrl` points to where the client can obtain a token (your login endpoint)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/google/login") # Updated tokenUrl

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# For this project, "active" simply means the user exists and has a valid token.
# You could add more checks here (e.g., user.is_active if you had such a field in User model)
async def get_current_active_user(current_user: User = Depends(get_current_user)):
    # You can add logic here to check if the user is "active" based on your application's rules
    # For now, we simply return the user obtained from the token.
    return current_user