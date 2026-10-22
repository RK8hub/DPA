from __future__ import annotations

from pathlib import Path

from design_pipeline.utils import (
    atomic_write_text,
    deep_merge,
    dotted_get,
    project_slug,
    redact,
    redact_env,
    sha256_file,
    sha256_text,
    tree_fingerprint,
)


def test_sha256_stable_y_distinto():
    assert sha256_text("a") == sha256_text("a")
    assert sha256_text("a") != sha256_text("b")


def test_tree_fingerprint_cambia_con_contenido(tmp_path: Path):
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("hola")
    first = tree_fingerprint(root)
    assert first == tree_fingerprint(root)
    (root / "a.txt").write_text("halo")
    assert tree_fingerprint(root) != first


def test_tree_fingerprint_respeta_exclusiones(tmp_path: Path):
    root = tmp_path / "tree"
    (root / "node_modules").mkdir(parents=True)
    (root / "keep.txt").write_text("x")
    (root / "node_modules" / "junk.js").write_text("y")
    solo_keep = tree_fingerprint(root, ["node_modules"])
    (root / "node_modules" / "junk.js").write_text("z")
    assert tree_fingerprint(root, ["node_modules"]) == solo_keep
    assert tree_fingerprint(root) != solo_keep


def test_tree_fingerprint_no_sigue_symlinks(tmp_path: Path):
    root = tmp_path / "tree"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("externo")
    (root / "link.txt").symlink_to(outside)
    # El symlink se ignora: agregar/modificar el destino no cambia la huella.
    before = tree_fingerprint(root)
    outside.write_text("modificado")
    assert tree_fingerprint(root) == before


def test_redact_claves_sensibles():
    data = {"api_key": "abc", "nested": {"password": "x", "ok": 1}}
    result = redact(data)
    assert result["api_key"] == "***REDACTED***"
    assert result["nested"]["password"] == "***REDACTED***"
    assert result["nested"]["ok"] == 1


def test_redact_env_filtra_valores():
    env = {"PATH": "/usr/bin", "GITHUB_TOKEN": "ghp_123", "MY_SECRET_THING": "v"}
    safe = redact_env(env)
    assert safe["PATH"] == "/usr/bin"
    assert safe["GITHUB_TOKEN"] == "***REDACTED***"
    assert safe["MY_SECRET_THING"] == "***REDACTED***"


def test_atomic_write(tmp_path: Path):
    target = tmp_path / "nested" / "file.txt"
    atomic_write_text(target, "contenido")
    assert target.read_text() == "contenido"
    assert list(target.parent.glob("*.tmp")) == []


def test_deep_merge_profundo():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    overlay = {"a": {"c": 9}, "e": 4}
    merged = deep_merge(base, overlay)
    assert merged == {"a": {"b": 1, "c": 9}, "d": 3, "e": 4}


def test_dotted_get():
    data = {"skills": {"allow_executive": False}}
    assert dotted_get(data, "skills.allow_executive") is False
    assert dotted_get(data, "skills.missing", "fallback") == "fallback"


def test_project_slug():
    assert project_slug("dashboard-operadores")
    assert not project_slug("Dashboard Operadores")
    assert not project_slug("a")
    assert not project_slug("-inicio")


def test_sha256_file(tmp_path: Path):
    target = tmp_path / "f.bin"
    target.write_bytes(b"abc")
    assert sha256_file(target) == sha256_text("abc")


def test_redact_text_enmascara_contenido():
    from design_pipeline.utils import redact_text

    text = (
        "Bearer abcdefghijklmnop1234 "
        "api_key=supersecreta123456 "
        "sk-abcdef1234567890abcd "
        "token: mi-token-largo-9999\n"
        "export GH_TOKEN=ghp_abcdefghijklmnopqrstuv "
        "sin problema normal"
    )
    clean = redact_text(text)
    assert "supersecreta123456" not in clean
    assert "sk-abcdef1234567890abcd" not in clean
    assert "ghp_" not in clean
    assert "abcdefghijklmnop1234" not in clean
    assert "***REDACTED***" in clean
    assert "sin problema normal" in clean
    # Llave privada completa.
    key = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    assert "abc" not in redact_text(key)


def test_redact_aplica_contenido_a_strings():
    from design_pipeline.utils import redact

    result = redact({"nota": "password=hunter2secret"})
    assert "hunter2secret" not in result["nota"]
