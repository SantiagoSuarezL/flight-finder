"""Carga y validación de `config.yaml` (TECHNICAL_SPEC.md §3).

Falla rápido con `ConfigError` (mensaje humano) ante cualquier problema:
archivo faltante, YAML mal formado o regla de validación violada (§3.1).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

PathLike = Union[str, Path]


class ConfigError(Exception):
    """Error de configuración con mensaje legible para el usuario."""


class SearchConfig(BaseModel):
    origin: str
    destination: str
    passengers: int = 1
    cabin_class: Literal["economy"] = "economy"
    max_combinations: int = 6
    drill_down: Literal["top_n", "off"] = "top_n"

    @field_validator("origin", "destination")
    @classmethod
    def _must_be_iata(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"[A-Z]{3}", v or ""):
            raise ValueError(
                f"{v!r} no es un código IATA válido "
                "(3 letras mayúsculas, ej. BOG)"
            )
        return v

    @field_validator("passengers")
    @classmethod
    def _only_one_passenger_in_v1(cls, v: int) -> int:
        if v != 1:
            raise ValueError("v1 solo soporta 1 pasajero (passengers: 1)")
        return v

    @field_validator("max_combinations")
    @classmethod
    def _at_least_one_combination(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                "search.max_combinations debe ser mayor que 0 "
                "(limita cuantas combinaciones de fecha se consultan)"
            )
        return v

    @model_validator(mode="after")
    def _origin_differs_from_destination(self) -> "SearchConfig":
        if self.origin == self.destination:
            raise ValueError(
                f"origin y destination no pueden ser iguales ({self.origin})"
            )
        return self


class DepartureConfig(BaseModel):
    fixed_date: date | None = None
    before: date | None = None

    @field_validator("fixed_date", "before")
    @classmethod
    def _not_in_the_past(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError(
                f"la fecha {v.isoformat()} ya pasó "
                f"(hoy es {date.today().isoformat()})"
            )
        return v

    @model_validator(mode="after")
    def _exactly_one_date_field(self) -> "DepartureConfig":
        given = [f for f in (self.fixed_date, self.before) if f is not None]
        if len(given) != 1:
            raise ValueError(
                "departure debe tener exactamente uno de "
                "'fixed_date' o 'before' (ni ambos, ni ninguno)"
            )
        return self


class StayConfig(BaseModel):
    min_days: int
    max_days: int

    @model_validator(mode="after")
    def _valid_range(self) -> "StayConfig":
        if self.min_days <= 0 or self.max_days <= 0:
            raise ValueError("min_days y max_days deben ser mayores que 0")
        if self.min_days > self.max_days:
            raise ValueError(
                f"min_days ({self.min_days}) no puede ser mayor que "
                f"max_days ({self.max_days})"
            )
        return self


class AvoidConfig(BaseModel):
    countries: list[str] = []
    airports: list[str] = []

    @field_validator("countries")
    @classmethod
    def _must_be_iso_alpha2(cls, v: list[str]) -> list[str]:
        import re

        for code in v:
            if not re.fullmatch(r"[A-Z]{2}", code or ""):
                raise ValueError(
                    f"{code!r} no es un código de país ISO 3166-1 alpha-2 "
                    "válido (2 letras mayúsculas, ej. US)"
                )
        return v

    @field_validator("airports")
    @classmethod
    def _must_be_iata(cls, v: list[str]) -> list[str]:
        import re

        for code in v:
            if not re.fullmatch(r"[A-Z]{3}", code or ""):
                raise ValueError(
                    f"{code!r} no es un código IATA válido "
                    "(3 letras mayúsculas, ej. ATL)"
                )
        return v


class SortConfig(BaseModel):
    primary: Literal["total_price", "duration"] = "total_price"
    secondary: Literal["duration", "total_price"] | None = "duration"

    @model_validator(mode="after")
    def _secondary_differs_from_primary(self) -> "SortConfig":
        if self.secondary is not None and self.secondary == self.primary:
            raise ValueError(
                "sort.secondary debe ser distinto de sort.primary "
                "(es el criterio de desempate)"
            )
        return self


class OutputConfig(BaseModel):
    top_n: int = 10
    export: Literal["csv", "html"] | None = None

    @field_validator("top_n")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("output.top_n debe ser mayor que 0")
        return v


class FlightFinderConfig(BaseModel):
    provider: Literal["serpapi", "searchapi"]
    currency: str = "USD"
    search: SearchConfig
    departure: DepartureConfig
    stay: StayConfig
    avoid: AvoidConfig = AvoidConfig()
    max_stops: int = 2
    sort: SortConfig = SortConfig()
    output: OutputConfig = OutputConfig()

    @field_validator("currency")
    @classmethod
    def _iso_4217(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"[A-Z]{3}", v or ""):
            raise ValueError(
                f"{v!r} no es un código ISO 4217 válido "
                "(3 letras mayúsculas, ej. USD)"
            )
        return v

    @field_validator("max_stops")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_stops no puede ser negativo")
        return v


def _humanize_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Error en {path}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(raíz)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_config(path: PathLike) -> FlightFinderConfig:
    """Lee y valida un archivo de configuración YAML.

    Lanza `ConfigError` con mensaje humano ante archivo faltante,
    YAML mal formado o validación fallida. Nunca deja escapar un
    traceback crudo hacia el usuario final (ver `main`).
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"No se encontró el archivo de configuración: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} no es un YAML válido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} debe contener un objeto YAML (clave: valor)")
    try:
        return FlightFinderConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_humanize_validation_error(path, exc)) from exc


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(
            "Uso: python -m flight_finder.config <config.yaml>",
            file=sys.stderr,
        )
        return 2
    try:
        cfg = load_config(args[0])
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    s = cfg.search
    print(
        f"Configuración válida: {s.origin}->{s.destination}, "
        f"estadía {cfg.stay.min_days}-{cfg.stay.max_days} días, "
        f"max_stops={cfg.max_stops}, provider={cfg.provider}, "
        f"max_combinations={s.max_combinations}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
