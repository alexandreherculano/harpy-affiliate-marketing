"""Post approval queue — manages individual content posts awaiting review and publishing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.logger import get_logger

logger = get_logger()


class PostEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"post_{uuid.uuid4().hex[:8]}")
    niche: str
    product: str = ""
    video_path: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["tiktok", "instagram"])
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: str | None = None
    posted_at: str | None = None
    feedback: str = ""
    render_metadata: dict[str, Any] = Field(default_factory=dict)


class PostQueueModel(BaseModel):
    posts: list[PostEntry] = Field(default_factory=list)


class PostQueue:
    """Manages the semi-automatic preview and approval queue."""

    QUEUE_FILE = "outputs/queue.json"

    def __init__(self, filepath: str | None = None) -> None:
        self.filepath = Path(filepath or self.QUEUE_FILE)

    def load(self) -> list[PostEntry]:
        if not self.filepath.exists():
            return []
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            model = PostQueueModel(**data)
            return model.posts
        except Exception as e:
            logger.error("Failed to load queue: %s", e)
            return []

    def save(self, posts: list[PostEntry]) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        model = PostQueueModel(posts=posts)
        self.filepath.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Queue saved: %d posts", len(posts))

    def add(self, entry: PostEntry) -> PostEntry:
        posts = self.load()
        posts.append(entry)
        self.save(posts)
        logger.info("Post added to queue: %s (%s)", entry.id, entry.niche)
        return entry

    def get(self, post_id: str) -> PostEntry | None:
        posts = self.load()
        for p in posts:
            if p.id == post_id:
                return p
        return None

    def approve(self, post_id: str) -> PostEntry | None:
        posts = self.load()
        for p in posts:
            if p.id == post_id:
                p.status = "approved"
                p.approved_at = datetime.now(timezone.utc).isoformat()
                self.save(posts)
                logger.info("Post approved: %s", post_id)
                return p
        return None

    def reject(self, post_id: str, feedback: str = "") -> PostEntry | None:
        posts = self.load()
        for p in posts:
            if p.id == post_id:
                p.status = "rejected"
                p.feedback = feedback
                self.save(posts)
                logger.info("Post rejected: %s — %s", post_id, feedback)
                return p
        return None

    def mark_posted(self, post_id: str) -> PostEntry | None:
        posts = self.load()
        for p in posts:
            if p.id == post_id:
                p.status = "posted"
                p.posted_at = datetime.now(timezone.utc).isoformat()
                self.save(posts)
                logger.info("Post marked as posted: %s", post_id)
                return p
        return None

    def list_by_status(self, status: str) -> list[PostEntry]:
        return [p for p in self.load() if p.status == status]

    def pending(self) -> list[PostEntry]:
        return self.list_by_status("pending")

    def approved(self) -> list[PostEntry]:
        return self.list_by_status("approved")

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.load():
            counts[p.status] = counts.get(p.status, 0) + 1
        return counts

    def remove(self, post_id: str) -> bool:
        posts = self.load()
        before = len(posts)
        posts = [p for p in posts if p.id != post_id]
        if len(posts) < before:
            self.save(posts)
            logger.info("Post removed from queue: %s", post_id)
            return True
        return False
