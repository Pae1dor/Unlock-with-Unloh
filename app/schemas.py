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


class CheckinIn(BaseModel):
    """The visitor's current GPS fix; used to verify distance, never stored."""

    osm_id: str = Field(pattern=r"^(node|way|relation)/\d{1,15}$")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float = Field(ge=0, le=100000)   # metres, from the Geolocation API


class MosqueOut(BaseModel):
    id: int
    name: str
    address: str
    phone: str | None = None
    lat: float
    lng: float
