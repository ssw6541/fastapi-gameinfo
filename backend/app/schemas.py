from typing import Literal

from pydantic import BaseModel


class Price(BaseModel):
    currency: str | None = None
    initial: float | None = None
    final: float | None = None
    discount_percent: int | None = 0
    final_formatted: str | None = None


class GameSummary(BaseModel):
    appid: int
    name: str | None
    name_en: str | None
    name_ko: str | None
    header_image: str
    capsule_image: str
    release_date: str | None
    release_ts: int | None
    is_free: bool | None
    price: Price | None
    review_pct: int | None
    review_count: int | None
    genres: list[str]


class SearchResponse(BaseModel):
    query: str | None
    total: int
    page: int
    page_size: int
    items: list[GameSummary]
    live_discovery: bool = False


class ReviewSummary(BaseModel):
    score_desc: str | None
    score: int | None
    total_positive: int
    total_negative: int
    total_reviews: int
    positive_ratio: float | None


class Movie(BaseModel):
    name: str | None
    thumbnail: str | None
    url: str | None = None
    hls: str | None = None


class Trailer(BaseModel):
    appid: int
    name: str | None
    thumbnail: str | None
    hls: str | None
    url: str | None


class GameDetail(BaseModel):
    appid: int
    type: str | None
    name: str | None
    name_en: str | None
    short_description: str
    about: str
    header_image: str
    background: str | None
    website: str | None
    is_free: bool
    price: Price | None
    release_date: str | None
    coming_soon: bool
    developers: list[str]
    publishers: list[str]
    genres: list[str]
    categories: list[str]
    platforms: dict[str, bool]
    supported_languages: str
    metacritic: int | None
    recommendations: int | None
    screenshots: list[str]
    movies: list[Movie]
    store_url: str
    review_summary: ReviewSummary | None
    fetched_at: int | None
    stale: bool


class Review(BaseModel):
    id: str
    language: str | None
    text: str
    voted_up: bool
    votes_up: int
    votes_funny: int
    helpful_score: float
    comment_count: int
    created_at: int
    updated_at: int
    playtime_forever_min: int
    playtime_at_review_min: int
    author_num_reviews: int
    steam_purchase: bool
    received_for_free: bool
    early_access: bool
    url: str | None


class ReviewsResponse(BaseModel):
    appid: int
    reviews: list[Review]
    cursor: str | None
    has_more: bool
    summary: ReviewSummary | None
    query: dict
    fetched_at: int
    cached: bool


class ReviewStats(BaseModel):
    appid: int
    official: ReviewSummary | None
    sample: dict
    fetched_at: int
    cached: bool


class Genre(BaseModel):
    id: int
    name_en: str
    name: str
    count: int


SortKey = Literal["relevance", "reviews", "rating", "newest", "oldest", "price_asc", "price_desc", "name"]
ReviewSort = Literal["helpful", "recent", "updated"]
