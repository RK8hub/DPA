"""Registro de skills: descubrimiento, inspección, importación y control.

Modelo de formato: carpeta con ``SKILL.md`` (metadatos en frontmatter YAML)
más recursos opcionales. Las skills se tratan como **contenido no confiable**:

- Importarlas solo copia archivos y calcula hashes; nunca ejecuta nada.
- Los scripts declarados se muestran para inspección previa; nada se ejecuta
  automáticamente ni se hereda el bit de ejecución del origen.
- Se rechazan symlinks, traversal de rutas, archivos gigantes y nombres raros.
- Habilitar una skill es un permiso explícito por proyecto; las skills
  ``executive`` requieren además ``skills.allow_executive`` en la configuración.

Precedencia de instrucciones (documentada y aplicada por los consumidores):
principios del sistema y controles de seguridad > reglas aprobadas del
proyecto > recomendaciones de skills externas.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from design_pipeline.config import global_skills_dir
from design_pipeline.engine.stages import STAGE_IDS
from design_pipeline.errors import SkillError
from design_pipeline.utils import dotted_get, iso_now, sha256_file
from design_pipeline.workspace.project import Project

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
VALID_MODES = ("instructive", "executive")
META_FILE = "skill.yaml"

# Permisos que el registro reconoce (lista abierta; se reportan tal cual).
KNOWN_PERMISSIONS = (
    "read-workspace",
    "read-output",
    "write-reports",
    "write-rules",
    "write-specs",
    "write-output",
)


@dataclass
class SkillRecord:
    name: str
    path: str
    origin: str  # internal | global | project
    description: str = ""
    version: str = ""
    format: str = "markdown-folder"
    mode: str = "instructive"
    permissions: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    enabled: bool = False
    digest: str = ""
    imported_at: str = ""
    body_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    record: SkillRecord | None = None


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extrae ``--- yaml ---`` inicial. Devuelve (metadata, cuerpo)."""
    if not text.startswith("---"):
        raise SkillError("SKILL.md no tiene frontmatter (debe empezar con `---`).")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillError("Frontmatter sin cierre `---`.")
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"Frontmatter YAML inválido: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillError("El frontmatter debe ser un mapping YAML.")
    return meta, parts[2].strip()


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def validate_skill_dir(path: Path, assumed_name: str | None = None) -> SkillValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_dir():
        return SkillValidation(ok=False, errors=[f"No es una carpeta: {path}"])

    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        return SkillValidation(ok=False, errors=["Falta SKILL.md en la carpeta."])

    try:
        text = skill_md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
    except (SkillError, OSError, UnicodeDecodeError) as exc:
        return SkillValidation(ok=False, errors=[f"SKILL.md ilegible: {exc}"])

    name = str(meta.get("name", assumed_name or path.name))
    if not NAME_RE.match(name):
        errors.append(f"Nombre inválido: {name!r} (esperado kebab-case, 2-64 caracteres).")
    if assumed_name and name != assumed_name:
        errors.append(f"El nombre del frontmatter ({name}) no coincide con {assumed_name!r}.")
    if not str(meta.get("description", "")).strip():
        errors.append("Falta `description`.")
    mode = str(meta.get("mode", "instructive"))
    if mode not in VALID_MODES:
        errors.append(f"`mode` inválido: {mode!r} (opciones: {', '.join(VALID_MODES)}).")
    if mode == "executive":
        warnings.append(
            "Modo executive: esta skill declara que requiere ejecución de herramientas; "
            "habilitarla exige skills.allow_executive y aprobación explícita."
        )
    stages = meta.get("stages", []) or []
    for stage in stages:
        if stage not in STAGE_IDS:
            errors.append(f"`stages` contiene una etapa desconocida: {stage!r}.")
    scripts = [str(item) for item in (meta.get("scripts", []) or [])]
    for script in scripts:
        script_path = Path(script)
        if script_path.is_absolute() or ".." in script_path.parts:
            errors.append(f"Ruta de script insegura: {script!r}.")
        elif not (path / script).exists():
            errors.append(f"Script declarado inexistente: {script!r}.")
        else:
            warnings.append(
                f"Script declarado: {script}. NO se ejecutará automáticamente; "
                "inspeccionalo antes de habilitar la skill."
            )
    if len(body) < 40:
        warnings.append("El cuerpo del SKILL.md es muy corto; probablemente incompleto.")
    for permission in meta.get("permissions", []) or []:
        if permission not in KNOWN_PERMISSIONS:
            warnings.append(f"Permiso no estándar declarado: {permission!r} (se ignora decorativamente).")

    record = SkillRecord(
        name=name,
        path=str(path),
        origin="",
        description=str(meta.get("description", "")),
        version=str(meta.get("version", "")),
        format=str(meta.get("format", "markdown-folder")),
        mode=mode,
        permissions=[str(p) for p in (meta.get("permissions", []) or [])],
        tools=[str(t) for t in (meta.get("tools", []) or [])],
        stages=[str(s) for s in stages],
        scripts=scripts,
        body_preview=body[:400],
    )
    return SkillValidation(ok=not errors, errors=errors, warnings=warnings, record=record)


# ---------------------------------------------------------------------------
# Descubrimiento
# ---------------------------------------------------------------------------

def _internal_root() -> Path:
    return Path(resources.files("design_pipeline").joinpath("data/skills").as_posix())


def _digest_tree(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file():
            digest.update(file_path.relative_to(path).as_posix().encode())
            digest.update(sha256_file(file_path).encode())
    return digest.hexdigest()


def _load_record(skill_dir: Path, origin: str) -> SkillRecord | None:
    validation = validate_skill_dir(skill_dir)
    if not validation.ok or validation.record is None:
        return None
    record = validation.record
    record.origin = origin
    record.digest = _digest_tree(skill_dir)
    meta_path = skill_dir / META_FILE
    if meta_path.exists():
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            provenance = meta.get("provenance", {}) or {}
            record.imported_at = str(provenance.get("imported_at", ""))
        except Exception:  # pragma: no cover - metadatos corruptos: se ignora el detalle
            pass
    return record


def discover_skills(project: Project | None, config: dict[str, Any]) -> list[SkillRecord]:
    records: list[SkillRecord] = []
    internal_root = _internal_root()
    if internal_root.is_dir():
        for child in sorted(internal_root.iterdir()):
            if child.is_dir():
                record = _load_record(child, "internal")
                if record:
                    records.append(record)
    roots: list[tuple[str, Path]] = [("global", global_skills_dir(config))]
    if project is not None:
        roots.append(("project", project.paths.project_skills_dir))
    for origin, root in roots:
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    record = _load_record(child, origin)
                    if record:
                        records.append(record)
    enabled = set(project.enabled_skills) if project is not None else set()
    for record in records:
        # Habilitación explícita por proyecto: la lista se siembra en `init`
        # con las skills internas y se amplía con `skills enable`.
        record.enabled = record.name in enabled
    return records


def find_skill(
    project: Project | None, config: dict[str, Any], name: str
) -> SkillRecord | None:
    return next((record for record in discover_skills(project, config) if record.name == name), None)


# ---------------------------------------------------------------------------
# Importación (solo copia + hashes; nunca ejecuta)
# ---------------------------------------------------------------------------

def _safe_copy_tree(src: Path, dest: Path) -> list[str]:
    """Copia validando cada archivo. Devuelve errores (vacío si todo OK)."""
    errors: list[str] = []
    total = 0
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        if any(part.startswith(".") for part in rel.parts):
            errors.append(f"Archivo oculto rechazado: {rel.as_posix()}")
            continue
        if item.is_symlink():
            errors.append(f"Symlink rechazado: {rel.as_posix()}")
            continue
        if item.is_dir():
            (dest / rel).mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            errors.append(f"Tipo de archivo no soportado: {rel.as_posix()}")
            continue
        size = item.stat().st_size
        total += size
        if size > MAX_FILE_BYTES:
            errors.append(f"Archivo demasiado grande ({size} bytes): {rel.as_posix()}")
            continue
        if total > MAX_TOTAL_BYTES:
            errors.append("Tamaño total de la skill excede el límite.")
            break
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Copia byte a byte SIN heredar permisos de ejecución.
        target.write_bytes(item.read_bytes())
    return errors


def add_skill(
    src: Path,
    project: Project | None,
    config: dict[str, Any],
    target: str = "global",
) -> SkillRecord:
    """Importa una skill desde una carpeta local. Nunca ejecuta sus archivos."""
    src = src.expanduser().resolve()
    validation = validate_skill_dir(src)
    if not validation.ok or validation.record is None:
        raise SkillError("Skill inválida: " + "; ".join(validation.errors))
    record = validation.record

    if record.mode == "executive" and not bool(dotted_get(config, "skills.allow_executive")):
        raise SkillError(
            f"La skill '{record.name}' es executive y la configuración "
            "skills.allow_executive está en false. Activala explícitamente para importarla."
        )

    root = global_skills_dir(config) if target == "global" else _project_skills_dir(project)
    dest = root / record.name
    if dest.exists():
        raise SkillError(
            f"Ya existe una skill llamada '{record.name}' en {root}. "
            "No se sobrescribe; eliminá la existente primero si querés reemplazarla."
        )

    copy_errors = _safe_copy_tree(src, dest)
    if copy_errors:
        # Limpieza ante fallo parcial (solo lo que esta importación creó).
        import shutil

        if dest.exists():
            shutil.rmtree(dest)
        raise SkillError("Importación rechazada: " + "; ".join(copy_errors[:5]))

    # Metadatos de procedencia + hash de los archivos importados.
    file_hashes = {
        file_path.relative_to(dest).as_posix(): sha256_file(file_path)
        for file_path in sorted(dest.rglob("*"))
        if file_path.is_file()
    }
    meta = {
        "name": record.name,
        "version": record.version,
        "mode": record.mode,
        "origin": {
            "kind": "local-path",
            "path": str(src),
            "imported_at": iso_now(),
        },
        "scripts": record.scripts,
        "scripts_executed_on_import": False,
        "file_sha256": file_hashes,
        "warnings": validation.warnings,
    }
    (dest / META_FILE).write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    new_record = _load_record(dest, "global" if target == "global" else "project")
    if new_record is None:  # pragma: no cover - la validación previa lo garantiza
        raise SkillError("La skill importada no valida tras la copia.")
    return new_record


def _project_skills_dir(project: Project | None) -> Path:
    if project is None:
        raise SkillError("La importación a nivel proyecto requiere --project.")
    return project.paths.project_skills_dir


def remove_skill(project: Project, config: dict[str, Any], name: str, confirm: bool) -> str:
    """Elimina una skill externa. Requiere confirmación explícita (destructivo)."""
    if not confirm:
        raise SkillError(
            "Eliminar una skill es destructivo: repetí el comando con --yes para confirmar."
        )
    record = find_skill(project, config, name)
    if record is None:
        raise SkillError(f"No existe la skill '{name}'.")
    if record.origin == "internal":
        raise SkillError("Las skills internas del paquete no se pueden eliminar.")
    import shutil

    shutil.rmtree(record.path)
    enabled = [item for item in project.enabled_skills if item != name]
    project.set_enabled_skills(enabled)
    project.save_data()
    return f"Skill '{name}' eliminada de {record.origin}."


# ---------------------------------------------------------------------------
# Habilitación y activación por etapa
# ---------------------------------------------------------------------------

def set_skill_enabled(project: Project, name: str, enabled: bool) -> None:
    current = project.enabled_skills
    if enabled:
        if name not in current:
            current.append(name)
    else:
        current = [item for item in current if item != name]
    project.set_enabled_skills(current)
    project.save_data()


def active_skills_for_stage(project: Project, stage_id: str) -> list[SkillRecord]:
    """Skills habilitadas que declaran participar en la etapa (solo registro)."""
    active: list[SkillRecord] = []
    for record in discover_skills(project, project.config):
        if not record.enabled:
            continue
        if stage_id in record.stages:
            active.append(record)
    return active


def seed_internal_skills(project: Project) -> list[str]:
    """Habilita en el proyecto todas las skills internas del paquete.

    Es el único momento en que se habilitan sin inspección previa: son
    instrucciones propias del paquete, no contenido externo.
    """
    names = [
        record.name
        for record in discover_skills(project, project.config)
        if record.origin == "internal"
    ]
    merged = sorted(set(project.enabled_skills) | set(names))
    project.set_enabled_skills(merged)
    project.save_data()
    return merged
