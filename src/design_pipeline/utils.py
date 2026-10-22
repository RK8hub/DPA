"""Utilidades transversales: tiempo, hashes, escritura atómica y redacción."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Claves cuyo valor nunca debe aparecer en logs o reportes.
_SECRET_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|credential|private[_-]?key|session)"
)

# Valores de entorno que jamás se registran completos.
_SECRET_ENV_RE = re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|API_?KEY|CREDENTIAL|AUTH)")

# Patrones de CONTENIDO que se enmascaran dentro de textos (salidas de
# agentes, stderr, comandos) además de las claves estructuradas.
_SECRET_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(
        r"(?i)\b(authorization|api[_-]?key|access[_-]?token|password|passwd|secret)"
        r"\s*[:=]\s*[\"']?[^\s\"']{6,}"
    ),
)


def redact_text(text: str) -> str:
    """Enmascara secretos por CONTENIDO dentro de un texto libre."""
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Timestamp ISO-8601 en UTC con sufijo Z."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def iter_files(root: Path, exclusions: Iterable[str] | None = None) -> list[Path]:
    """Lista archivos bajo ``root`` respetando exclusiones de nombre/glob simples.

    Se usa para fingerprints e inventarios; nunca sigue symlinks.
    """
    excluded = list(exclusions or [])
    results: list[Path] = []
    if not root.is_dir():
        return results
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not _is_excluded(d, excluded) and not (current / d).is_symlink()
        )
        for name in sorted(filenames):
            if _is_excluded(name, excluded):
                continue
            candidate = current / name
            if candidate.is_symlink():
                continue
            results.append(candidate)
    return results


def _is_excluded(name: str, patterns: Iterable[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(name, pattern) for pattern in patterns)


def tree_fingerprint(root: Path, exclusions: Iterable[str] | None = None) -> str:
    """Hash estable de un árbol: rutas relativas + hashes de contenido."""
    digest = hashlib.sha256()
    if not root.is_dir():
        return sha256_bytes(b"<missing-tree>")
    for path in iter_files(root, exclusions):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Escribe de forma atómica para no dejar archivos a medias."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def redact(value: Any) -> Any:
    """Redacta claves sensibles de estructuras anidadas antes de loguear."""
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_env(env: dict[str, str]) -> dict[str, str]:
    """Devuelve un entorno filtrado: solo claves no sensibles, valores truncados."""
    safe: dict[str, str] = {}
    for key, value in sorted(env.items()):
        if _SECRET_ENV_RE.search(key):
            safe[key] = "***REDACTED***"
        else:
            safe[key] = value[:200]
    return safe


def format_bytes(size: int) -> str:
    step = 1024.0
    amount = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if amount < step:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= step
    return f"{amount:.1f} TiB"


def project_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", value))


def short(value: str, limit: int = 12) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Fusión profunda de dicts; los valores escalares del overlay ganan."""
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def dotted_get(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current
