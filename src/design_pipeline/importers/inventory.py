"""Etapa B: inventario seguro de exportaciones.

Nunca ejecuta ni modifica los archivos de entrada. Produce ``inventory.json``
con rutas, categorías, tamaños, hashes, referencias entre archivos, recursos
duplicados y problemas detectados (referencias rotas, binarios grandes, etc.).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline.utils import (
    format_bytes,
    iso_now,
    sha256_file,
    tree_fingerprint,
)

# Extensiones que identifican componentes y código de interfaz.
COMPONENT_EXT = {".jsx", ".tsx"}
SCRIPT_EXT = {".js", ".ts", ".mjs", ".cjs"}
STYLE_EXT = {".css", ".scss"}
DATA_EXT = {".json", ".yml", ".yaml"}
VECTOR_EXT = {".svg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico"}
FONT_EXT = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
DOC_EXT = {".md", ".txt", ".html"}

# Referencias potenciales en código de text o estilos.
_IMPORT_RE = re.compile(
    r"""(?:import|export)\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]"""
)
_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""")
_SRC_RE = re.compile(r"""\b(?:src|href)=['"]([^'"]+)['"]""")

_EXTERNAL_RE = re.compile(r"^(?:https?:|data:|mailto:|tel:|//)")


@dataclass
class FileEntry:
    path: str
    size: int
    sha256: str
    category: str
    analyzed: bool = True
    reason: str = ""
    references: list[str] = field(default_factory=list)


@dataclass
class Inventory:
    source_path: str
    created_at: str
    source_fingerprint: str
    exclusions: list[str]
    max_file_size_bytes: int
    files: list[FileEntry] = field(default_factory=list)
    duplicate_groups: list[dict[str, Any]] = field(default_factory=list)
    broken_references: list[dict[str, Any]] = field(default_factory=list)
    external_references: list[dict[str, Any]] = field(default_factory=list)
    unanalyzed: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def component_files(self) -> list[FileEntry]:
        return [entry for entry in self.files if entry.category == "component"]

    def files_by_path(self) -> dict[str, FileEntry]:
        return {entry.path: entry for entry in self.files}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def categorize(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in COMPONENT_EXT:
        return "component"
    if ext in SCRIPT_EXT:
        return "script"
    if ext in STYLE_EXT:
        return "style"
    if ext in DATA_EXT:
        return "data"
    if ext in VECTOR_EXT:
        return "vector"
    if ext in IMAGE_EXT:
        return "image"
    if ext in FONT_EXT:
        return "font"
    if ext in DOC_EXT:
        return "doc"
    if ext in {".jsx", ".js", ".ts", ".tsx"}:  # pragma: no cover - cubierto arriba
        return "script"
    return "other"


def extract_references(text: str, category: str) -> list[str]:
    refs: list[str] = []
    patterns = [_IMPORT_RE, _REQUIRE_RE, _SRC_RE]
    if category in {"style", "vector"}:
        patterns.append(_URL_RE)
    for pattern in patterns:
        refs.extend(match.group(1) for match in pattern.finditer(text))
    # Deduplicar preservando orden.
    seen: dict[str, None] = {}
    for ref in refs:
        seen.setdefault(ref, None)
    return list(seen)


def _is_external(ref: str) -> bool:
    return bool(_EXTERNAL_RE.match(ref)) or ref.startswith("#")


def build_inventory(
    source: Path,
    text_extensions: list[str],
    exclusions: list[str],
    max_file_size_bytes: int,
) -> Inventory:
    from design_pipeline.utils import iter_files

    source = source.resolve()
    inventory = Inventory(
        source_path=str(source),
        created_at=iso_now(),
        source_fingerprint=tree_fingerprint(source, exclusions),
        exclusions=list(exclusions),
        max_file_size_bytes=max_file_size_bytes,
    )

    by_hash: dict[str, list[FileEntry]] = {}
    for path in iter_files(source, exclusions):
        rel = path.relative_to(source).as_posix()
        size = path.stat().st_size
        digest = sha256_file(path)
        category = categorize(path)
        entry = FileEntry(path=rel, size=size, sha256=digest, category=category)
        if size > max_file_size_bytes:
            entry.analyzed = False
            entry.reason = f"supera el máximo de {format_bytes(max_file_size_bytes)}"
            inventory.unanalyzed.append({"path": rel, "reason": entry.reason})
        elif path.suffix.lower() not in text_extensions:
            entry.analyzed = False
            entry.reason = f"extensión no soportada para análisis ({path.suffix or 'sin extensión'})"
            inventory.unanalyzed.append({"path": rel, "reason": entry.reason})
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:  # pragma: no cover - permisos raros
                entry.analyzed = False
                entry.reason = f"no se pudo leer: {exc}"
                inventory.unanalyzed.append({"path": rel, "reason": entry.reason})
            else:
                entry.references = extract_references(text, category)
        inventory.files.append(entry)
        by_hash.setdefault(digest, []).append(entry)

    # Duplicados por contenido.
    for digest, entries in sorted(by_hash.items(), key=lambda kv: kv[0]):
        if len(entries) > 1:
            inventory.duplicate_groups.append(
                {
                    "sha256": digest,
                    "size": entries[0].size,
                    "paths": [entry.path for entry in entries],
                }
            )

    # Referencias internas/externas y rotas.
    known = {entry.path for entry in inventory.files}
    for entry in inventory.files:
        for ref in entry.references:
            if _is_external(ref):
                inventory.external_references.append({"from": entry.path, "ref": ref})
                continue
            if not ref.startswith("."):
                # Especificador de paquete (react, @scope/pkg, ...): no es ruta local.
                inventory.external_references.append({"from": entry.path, "ref": ref})
                continue
            resolved = _resolve_relative(entry.path, ref)
            if resolved is None:
                inventory.broken_references.append(
                    {"from": entry.path, "ref": ref, "reason": "ruta inválida (traversal)"}
                )
                continue
            if not _resolves_to_known(resolved, known):
                inventory.broken_references.append(
                    {"from": entry.path, "ref": ref, "reason": "archivo no encontrado"}
                )

    categories: dict[str, int] = {}
    total_size = 0
    for entry in inventory.files:
        categories[entry.category] = categories.get(entry.category, 0) + 1
        total_size += entry.size
    inventory.stats = {
        "total_files": len(inventory.files),
        "total_size_bytes": total_size,
        "total_size_human": format_bytes(total_size),
        "by_category": dict(sorted(categories.items())),
        "duplicates": len(inventory.duplicate_groups),
        "broken_references": len(inventory.broken_references),
        "external_references": len(inventory.external_references),
        "unanalyzed": len(inventory.unanalyzed),
    }
    return inventory


def _resolve_relative(from_rel: str, ref: str) -> str | None:
    """Resuelve un specificador relativo contra la carpeta del archivo."""
    if not ref.startswith("."):
        return None
    base_dir = Path(from_rel).parent
    parts = list(base_dir.parts)
    for part in Path(ref).parts:
        if part == "..":
            if not parts:
                return None  # traversal fuera de la raíz
            parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


# Extensiones que un bundler puede resolver de forma implícita.
_IMPLIED_EXTENSIONS = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".scss",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
)


def _resolves_to_known(resolved: str, known: set[str]) -> bool:
    """¿La ruta resuelta corresponde a un archivo conocido (extensión implícita incluida)?"""
    if resolved in known:
        return True
    for ext in _IMPLIED_EXTENSIONS:
        if f"{resolved}{ext}" in known:
            return True
    for ext in (".tsx", ".ts", ".jsx", ".js"):
        if f"{resolved}/index{ext}" in known:
            return True
    return False


def inventory_to_json(inventory: Inventory) -> dict[str, Any]:
    return inventory.to_dict()
