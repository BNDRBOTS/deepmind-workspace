from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import os
import logging
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from supabase import create_client, Client
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Auth Service",
    version="1.0.0",
    description="JWT authentication and user identity management"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=3, max_length=50)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: str
    email: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        if user_id is None or email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return TokenData(user_id=user_id, email=email)
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    return decode_token(credentials.credentials)

@app.get("/health")
async def health():
    return {
        "status": "online",
        "service": "auth",
        "jwt_configured": bool(SECRET_KEY)
    }

@app.post("/register", status_code=201)
async def register(user: UserRegister, supabase: Client = Depends(get_supabase)):
    try:
        # Check if user exists
        existing = supabase.table("users").select("*").eq("email", user.email).execute()
        if existing.data:
            raise HTTPException(400, "Email already registered")
        
        # Hash password
        hashed_password = hash_password(user.password)
        
        # Create user
        user_data = {
            "email": user.email,
            "username": user.username,
            "password_hash": hashed_password,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("users").insert(user_data).execute()
        
        if not result.data:
            raise HTTPException(500, "Failed to create user")
        
        created_user = result.data[0]
        user_id = created_user["id"]
        
        # Generate tokens
        access_token = create_access_token({"sub": user_id, "email": user.email})
        refresh_token = create_refresh_token({"sub": user_id, "email": user.email})
        
        logger.info(f"User registered: {user.email}")
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(500, str(e))

@app.post("/login")
async def login(credentials: UserLogin, supabase: Client = Depends(get_supabase)):
    try:
        # Get user
        result = supabase.table("users").select("*").eq("email", credentials.email).execute()
        
        if not result.data:
            raise HTTPException(401, "Invalid email or password")
        
        user = result.data[0]
        
        # Verify password
        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(401, "Invalid email or password")
        
        # Generate tokens
        access_token = create_access_token({"sub": user["id"], "email": user["email"]})
        refresh_token = create_refresh_token({"sub": user["id"], "email": user["email"]})
        
        logger.info(f"User logged in: {credentials.email}")
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(500, str(e))

@app.post("/refresh")
async def refresh_token(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        
        user_id = payload.get("sub")
        email = payload.get("email")
        
        if not user_id or not email:
            raise HTTPException(401, "Invalid token")
        
        # Generate new access token
        new_access_token = create_access_token({"sub": user_id, "email": email})
        
        return {"access_token": new_access_token, "token_type": "bearer"}
    
    except JWTError as e:
        logger.error(f"Refresh token error: {str(e)}")
        raise HTTPException(401, "Invalid or expired refresh token")

@app.get("/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user), supabase: Client = Depends(get_supabase)):
    try:
        result = supabase.table("users").select("id, email, username, created_at").eq("id", current_user.user_id).execute()
        
        if not result.data:
            raise HTTPException(404, "User not found")
        
        return result.data[0]
    
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        raise HTTPException(500, str(e))

@app.post("/verify")
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token_data = decode_token(credentials.credentials)
    return {"valid": True, "user_id": token_data.user_id, "email": token_data.email}