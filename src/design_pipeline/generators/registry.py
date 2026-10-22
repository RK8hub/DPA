"""Registro de perfiles de generación.

Agregar un destino nuevo = crear la clase Profile e indicarla en
``PROFILES``. El núcleo no tiene acoplamiento con perfiles concretos.
"""

from __future__ import annotations

from design_pipeline.errors import DesignPipelineError
from design_pipeline.generators.astro_profile import AstroCssProfile
from design_pipeline.generators.base import Profile
from design_pipeline.generators.react_profile import ReactCssProfile

PROFILES: dict[str, Profile] = {
    profile.id: profile for profile in (ReactCssProfile(), AstroCssProfile())
}


def get_profile(profile_id: str) -> Profile:
    profile = PROFILES.get(profile_id)
    if profile is None:
        raise DesignPipelineError(
            f"Perfil desconocido: {profile_id}. Disponibles: {', '.join(sorted(PROFILES))}"
        )
    return profile


def list_profiles() -> list[dict[str, str]]:
    return [
        {"id": profile.id, "label": profile.label, "description": profile.description}
        for profile in PROFILES.values()
    ]
