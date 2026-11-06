"""Accès HTTP minimal pour les collecteurs (bibliothèque standard uniquement)."""

from __future__ import annotations

import urllib.request
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from typing import BinaryIO

USER_AGENT = "barometre-democratie/0.1 (collecte open data, Licence Ouverte Etalab 2.0)"
CHUNK_SIZE = 1 << 20
TIMEOUT = 120


# Ouvre une URL et fournit un flux binaire ; remplaçable dans les tests.
Opener = Callable[[str], AbstractContextManager[BinaryIO]]


@contextmanager
def urlopen(url: str) -> Iterator[BinaryIO]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        yield response


def iter_chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(CHUNK_SIZE):
        yield chunk


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
