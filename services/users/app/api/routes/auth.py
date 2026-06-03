# app/api/routes/auth.py
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.database.session import get_db
from app.api import service
from app.infra.rabbitmq import publish_event
from app.schemas.user import UserCreate, UserOut
from app.schemas.auth import Token

router = APIRouter(tags=["auth"])
logger = logging.getLogger("users-service")


@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(
  user_in: UserCreate,
  db: AsyncSession = Depends(get_db),
):
  logger.info(
    "Registering new user",
    extra={"email": user_in.email, "role": user_in.role.value},
  )

  existing = await service.get_user_by_email(db, user_in.email)
  if existing:
    logger.warning(
      "Registration failed: email already registered",
      extra={"email": user_in.email},
    )
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Email already registered",
    )

  hashed_pw = get_password_hash(user_in.password)
  user = await service.create_user(db, user_in, hashed_pw)

  logger.info(
    "User registered successfully",
    extra={"user_id": user.id, "email": user.email, "role": user.role.value},
  )

  event = {
    "event_type": "employee_created",
    "version": 1,
    "data": {
      "user_id": user.id,
      "full_name": user.full_name,
      "email": user.email,
      # "manager_id": user.manager_id,
    },
  }
  publish_event(event, routing_key="employee.created")
  logger.info(
    "Published employee_created event",
    extra={"user_id": user.id, "email": user.email},
  )

  return user


@router.post("/token", response_model=Token)
async def login_for_access_token(
  form_data: OAuth2PasswordRequestForm = Depends(),
  db: AsyncSession = Depends(get_db),
):
  logger.info(
    "Login attempt",
    extra={"username": form_data.username},
  )

  user = await service.get_user_by_email(db, form_data.username)
  if not user or not verify_password(form_data.password, user.hashed_password):
    logger.warning(
      "Login failed: invalid credentials",
      extra={"username": form_data.username},
    )
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Incorrect username or password",
      headers={"WWW-Authenticate": "Bearer"},
    )

  access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
  access_token = create_access_token(
    user_id=user.id,
    email=user.email,
    role=user.role.value,
    expires_delta=access_token_expires,
  )

  logger.info(
    "Login successful, JWT issued",
    extra={"user_id": user.id, "email": user.email, "role": user.role.value},
  )

  return Token(access_token=access_token)