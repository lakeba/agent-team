"""Ranking a project's files by relevance to a task, for focused context in big codebases.

A small BM25 search over each file's path and contents, standard library only: identifiers are
split into words (camelCase, snake_case), the path counts extra, and very large files are read
only in part. It runs in about a second on thousands of files, and gives the lead a shortlist to
start from instead of only a map of every file.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from . import files

MAX_READ = 200_000
WORD_RE = re.compile(r"[A-Za-z][a-z]+|[A-Z]+(?![a-z])|\d+")
STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "are", "was", "not", "but", "you", "your",
        "all", "any", "can", "will", "should", "must", "add", "make", "use", "new", "get", "set", "return",
        "import", "def", "class", "function", "const", "let", "var", "self", "true", "false", "none", "null"}


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text) if len(w) > 2 and w.lower() not in STOP]


def rank(root, query: str, skip: tuple[str, ...] = (), top: int = 40) -> list[tuple[str, float]]:
    """[(path, score)] best first, for the files a prompt may include."""
    q = Counter(words(query))
    if not q:
        return []
    docs: dict[str, Counter] = {}
    lengths: dict[str, int] = {}
    for rel, full in files.project_files(root, skip=skip):
        try:
            with open(full, encoding="utf-8") as f:
                text = f.read(MAX_READ)
        except (UnicodeDecodeError, OSError):
            continue
        tokens = words(text) + words(rel) * 3          # the path is strong evidence
        docs[rel], lengths[rel] = Counter(tokens), len(tokens) or 1
    if not docs:
        return []
    n, avg = len(docs), sum(lengths.values()) / len(docs)
    df = Counter(t for c in docs.values() for t in set(c) if t in q)
    k1, b = 1.4, 0.75
    scores = []
    for rel, counts in docs.items():
        score = 0.0
        for term, qf in q.items():
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += qf * idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[rel] / avg))
        if score > 0:
            scores.append((rel, round(score, 3)))
    scores.sort(key=lambda s: -s[1])
    return scores[:top]


def shortlist(root, query: str, skip: tuple[str, ...] = (), top: int = 30) -> str:
    ranked = rank(root, query, skip, top)
    if not ranked:
        return "(no file matches the task's words)"
    return "\n".join(f"{rel}  ({Path(root, rel).stat().st_size:,} bytes)" for rel, _ in ranked)
