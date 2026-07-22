from __future__ import annotations

import json
import math
import os
import re
import secrets
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row


app = FastAPI(title="MEZO Indexer", docs_url=None, redoc_url=None)
TOKEN = os.getenv("ORCHESTRATOR_INTERNAL_TOKEN", "")
MODEL_TOKEN = os.getenv("MODEL_INTERNAL_TOKEN", "")
DATABASE_URL = os.getenv("INDEXER_DATABASE_URL", os.getenv("DATABASE_URL", ""))
APP_NAME = os.getenv("MEZO_APP_NAME", "mezo-ai")
EMBED_URL = os.getenv("EMBEDDING_URL", os.getenv("EMBEDDING_MODEL_URL", ""))
RERANK_URL = os.getenv("RERANKER_URL", os.getenv("RERANK_MODEL_URL", ""))


class FileInput(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1_000_000)


class IndexInput(BaseModel):
    project_id: str
    revision: str
    files: list[FileInput] = Field(max_length=20_000)


class SearchInput(BaseModel):
    project_id: str
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=12, ge=1, le=50)


def authorize(value: str | None) -> None:
    if not TOKEN or not value or not secrets.compare_digest(value, f"Bearer {TOKEN}"):
        raise HTTPException(401, "Invalid orchestration credential")


def migrate() -> None:
    if not DATABASE_URL:
        return
    with psycopg.connect(DATABASE_URL) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS repository_chunks(
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision TEXT NOT NULL,
            path TEXT NOT NULL, symbol TEXT, content TEXT NOT NULL, embedding TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS repository_chunks_project ON repository_chunks(project_id)")
        db.commit()


def chunks(path: str, content: str) -> list[tuple[str, str]]:
    lines = content.splitlines()
    result: list[tuple[str, str]] = []
    for start in range(0, len(lines), 120):
        text = "\n".join(lines[start:start + 160])
        symbol_match = re.search(r"(?m)^(?:class|def|function|interface|struct|enum)\s+([\w$]+)", text)
        symbol = symbol_match.group(1) if symbol_match else f"lines-{start + 1}-{min(len(lines), start + 160)}"
        if text.strip():
            result.append((symbol, f"{path}:{start + 1}\n{text}"))
    return result


async def embed(values: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{EMBED_URL}/embeddings", headers={"Authorization": f"Bearer {MODEL_TOKEN}"},
            json={"model": "local", "input": values},
        )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


@app.on_event("startup")
def startup() -> None:
    migrate()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/index")
async def index(body: IndexInput, authorization: str | None = Header(default=None)) -> dict[str, int]:
    authorize(authorization)
    records: list[tuple[str, str, str]] = []
    for item in body.files:
        records.extend((item.path, symbol, text) for symbol, text in chunks(item.path, item.content))
    vectors: list[list[float]] = []
    for start in range(0, len(records), 32):
        vectors.extend(await embed([record[2] for record in records[start:start + 32]]))
    with psycopg.connect(DATABASE_URL) as db:
        db.execute("DELETE FROM repository_chunks WHERE project_id=?".replace("?", "%s"), (body.project_id,))
        for index_value, (path, symbol, content) in enumerate(records):
            identifier = f"{body.project_id}:{index_value}"
            db.execute(
                "INSERT INTO repository_chunks(id,project_id,revision,path,symbol,content,embedding) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (identifier, body.project_id, body.revision, path, symbol, content, json.dumps(vectors[index_value])),
            )
        db.commit()
    return {"files": len(body.files), "chunks": len(records)}


@app.post("/search")
async def search(body: SearchInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    query_vector = (await embed([body.query]))[0]
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as db:
        rows = list(db.execute("SELECT id,path,symbol,content,embedding FROM repository_chunks WHERE project_id=%s", (body.project_id,)).fetchall())
    ranked = sorted(rows, key=lambda row: cosine(query_vector, json.loads(row["embedding"])), reverse=True)[: body.limit * 3]
    documents = [row["content"] for row in ranked]
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{RERANK_URL}/rerank", headers={"Authorization": f"Bearer {MODEL_TOKEN}"},
                json={"model": "local", "query": body.query, "documents": documents, "top_n": body.limit},
            )
        response.raise_for_status()
        order = [item["index"] for item in response.json()["results"]]
        ranked = [ranked[index] for index in order]
    except (httpx.HTTPError, KeyError, IndexError):
        ranked = ranked[: body.limit]
    return {"results": [{key: row[key] for key in ("id", "path", "symbol", "content")} for row in ranked[: body.limit]]}
