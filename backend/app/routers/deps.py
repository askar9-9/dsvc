from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.dependencies import get_current_user_for_sse
from app.database import get_db
from app.models import User

CurrentUser = Annotated[User, Depends(get_current_user)]
SseCurrentUser = Annotated[User, Depends(get_current_user_for_sse)]
Db = Annotated[AsyncSession, Depends(get_db)]
