"""Pydantic schemas for the small JSON endpoints the vanilla-JS front end calls."""
from pydantic import BaseModel, Field


class LikeOut(BaseModel):
    liked: bool
    like_count: int


class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    author_name: str
    author_initial: str
    content: str
    created_at: str


class MosqueOut(BaseModel):
    id: int
    name: str
    address: str
    phone: str | None = None
    lat: float
    lng: float
