"""Explicit, owned personal memory. Retrieval is bounded lexical relevance, not chat copying."""

import hashlib
import math
import re
import unicodedata
from collections import Counter

from sqlalchemy import func, select, update

from app.database import MemorySetting, PersonalMemory, User
from app.errors import AppError

CATEGORIES = {"preference", "fact", "project", "decision"}
SECRET_WORDS = re.compile(
    r"\b(?:api[ _-]?key|pass[ _-]?word|passphrase|secret|token|authorization|bearer|"
    r"private[ _-]?key|credential|session[ _-]?(?:id|cookie)|access[ _-]?key)\b",
    re.I,
)
SECRET_SHAPES = re.compile(
    r"(?:sk-[\w-]{8,}|gh[pousr]_[\w]{8,}|AKIA[A-Z0-9]{16}|-----BEGIN|"
    r"eyJ[\w-]+\.[\w-]+\.[\w-]+|https?://[^\s/]+:[^\s/]+@|"
    r"(?:hf_|gsk_|github_pat_)[\w]{8,}|xox[baprs]-[\w-]{8,}|AIza[\w-]{20,}|"
    r"cookie\s*[:=])",
    re.I,
)
STOP = set(
    "i me my mine you your yours we our a an the to of for on in is are that this "
    "it with and or please remember prefer preference what which do does use using "
    "tell about have how can should would be want know saved memory workflow".split()
)
SYNONYMS = {
    "deployment": "hosting",
    "deploy": "hosting",
    "host": "hosting",
    "dependencies": "package",
    "dependency": "package",
    "packages": "package",
}


def clean_content(text):
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = " ".join(text.split())
    if not 3 <= len(text) <= 500:
        raise AppError("invalid_memory", "Use 3–500 characters for a durable memory.", 422)
    suspicious = bool(SECRET_WORDS.search(text.replace("_", " ")) or SECRET_SHAPES.search(text))
    for token in re.findall(r"[A-Za-z0-9_+/=-]{24,}", text):
        entropy = -sum(
            (n / len(token)) * math.log2(n / len(token)) for n in Counter(token).values()
        )
        if re.search(r"[a-zA-Z]", token) and re.search(r"[0-9]", token) and entropy > 3:
            suspicious = True
    if suspicious:
        raise AppError(
            "memory_secret", "Credentials and possible secrets cannot be saved as memory.", 422
        )
    return text


def explicit_memory(message):
    match = re.match(
        r"^\s*(?:please\s+)?remember\s+(?:(?:that|this)\s*[:,-]?\s*)?(.+)$", message, re.I | re.S
    )
    if not match:
        return None
    if match.group(1).strip().casefold().rstrip(".:!?") in {"this", "that"}:
        raise AppError("invalid_memory", "Include the fact after ‘Remember that…’.", 422)
    content = clean_content(match.group(1))
    category = "preference" if re.search(r"\bprefer\b", content, re.I) else "fact"
    return content, category


async def enabled(db, owner):
    setting = await db.get(MemorySetting, owner)
    return setting is None or setting.enabled


def view(item):
    return {
        "id": item.id,
        "category": item.category,
        "content": item.content,
        "created_at": item.created_at,
    }


async def save(db, owner, content, category):
    content = clean_content(content)
    if category not in CATEGORIES:
        raise AppError("invalid_memory", "Choose a supported memory category.", 422)
    # Serialize per account to keep deduplication and quotas correct across requests.
    await db.execute(update(User).where(User.id == owner).values(is_active=User.is_active))
    if not await enabled(db, owner):
        raise AppError("memory_disabled", "Memory is disabled. Enable it in the Memory panel.", 409)
    digest = hashlib.sha256(content.casefold().encode()).hexdigest()
    existing = await db.scalar(
        select(PersonalMemory).where(
            PersonalMemory.user_id == owner, PersonalMemory.content_hash == digest
        )
    )
    if existing:
        return existing
    count = await db.scalar(
        select(func.count()).select_from(PersonalMemory).where(PersonalMemory.user_id == owner)
    )
    if count >= 200:
        raise AppError("memory_full", "Delete a memory before adding another (limit 200).", 409)
    item = PersonalMemory(user_id=owner, category=category, content=content, content_hash=digest)
    db.add(item)
    await db.flush()
    return item


def words(text):
    tokens = re.findall(r"[\w]+", text.casefold())
    return {
        SYNONYMS.get(t, t[:-1] if len(t) > 4 and t.endswith("s") else t)
        for t in tokens
        if t not in STOP and len(t) > 1
    }


async def retrieve(db, owner, query):
    if not await enabled(db, owner):
        return []
    relevant = []
    query_words = words(query)
    if not query_words:
        return []
    items = (
        await db.scalars(
            select(PersonalMemory)
            .where(PersonalMemory.user_id == owner)
            .order_by(PersonalMemory.created_at.desc())
            .limit(200)
        )
    ).all()
    for item in items:
        overlap = query_words & words(item.content)
        if overlap:
            relevant.append((len(overlap), item.created_at, item))
    relevant.sort(key=lambda row: (row[0], row[1]), reverse=True)
    result = []
    remaining = 1600
    for _, _, item in relevant[:4]:
        if len(item.content) <= remaining:
            result.append({"category": item.category, "content": item.content})
            remaining -= len(item.content)
    return result
