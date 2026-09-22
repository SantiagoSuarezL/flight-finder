"""Cliente de SerpApi/SearchApi (Google Flights) — UNICO modulo de red (§6, §12).

SEARCH-ONLY por arquitectura: este cliente solo expone `_get` para
búsqueda round trip y drill-down con `departure_token`. No existe método
alguno de reserva ni de pago (el flujo de reserva de Google Flights usa un
cuerpo propio que queda fuera de alcance); cualquier intento de añadirlos
debe ser rechazado por revisión y por el test estructural
`test_no_booking` (TECHNICAL_SPEC.md §12, §15).

Registry `PROVIDERS`: base URL + env var por proveedor; el mapeo de
parámetros vive en `map_search_params` (puro, testeable sin red). La API
key viene de `.env` (`SERP_API` / `SEARCH_API_IO`), nunca hardcodeada.

Manejo de errores:
- 401/403 -> `FlightsAuthError` inmediato (detiene la ejecución).
- 429 -> backoff exponencial con hasta `max_attempts` intentos (respeta
  `Retry-After` si viene); agotados -> `FlightsRateLimitError`.
- Timeout / error de red / 5xx -> reintento acotado; si persiste en una
  combinación, esa combinación se registra como fallida sin abortar el
  batch.
- 4xx (no auth) -> `FlightsError` con el mensaje de la API, sin reintento.
- Sin itinerarios -> resultado vacío legítimo, no error.

Cuota gratuita (§12.4): requests secuenciales por defecto; antes de cualquier
request real el CLI imprime la estimación (dry-run de params).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from flight_finder.models import extract_itineraries

log = logging.getLogger(__name__)


class FlightsError(Exception):
    """Error base del cliente de vuelos."""


class FlightsAuthError(FlightsError):
    """API key ausente, inválida o expirada."""


class FlightsRateLimitError(FlightsError):
    """Rate limit (429) persistente tras agotar los reintentos."""


class FlightsNetworkError(FlightsError):
    """Error de red/timeout/5xx persistente tras agotar los reintentos."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    env_var: str


PROVIDERS: dict[str, ProviderSpec] = {
    "serpapi": ProviderSpec(
        name="serpapi",
        base_url="https://serpapi.com/search",
        env_var="SERP_API",
    ),
    "searchapi": ProviderSpec(
        name="searchapi",
        base_url="https://www.searchapi.io/api/v1/search",
        env_var="SEARCH_API_IO",
    ),
}

# cabin_class -> travel_class del proveedor (v1 solo economy, §3).
_TRAVEL_CLASS: dict[tuple[str, str], str] = {
    ("serpapi", "economy"): "1",
    ("searchapi", "economy"): "economy",
}


def _stops_value(provider: str, max_stops: int) -> str:
    """max_stops del config -> enum de stops del proveedor (INFORME §5).

    SerpApi: 0=any, 1=nonstop, 2=1-stop-or-fewer, 3=2-stops-or-fewer.
    SearchApi: any | nonstop | one_stop_or_fewer | two_stops_or_fewer.
    """
    if provider == "serpapi":
        return {0: "1", 1: "2", 2: "3"}.get(max_stops, "0")
    return {
        0: "nonstop",
        1: "one_stop_or_fewer",
        2: "two_stops_or_fewer",
    }.get(max_stops, "any")


def map_search_params(
    provider: str,
    *,
    origin: str,
    destination: str,
    departure: date,
    return_date: date,
    currency: str = "USD",
    passengers: int = 1,
    cabin_class: str = "economy",
    max_stops: int = 2,
    avoid_airports: Sequence[str] = (),
) -> dict[str, str]:
    """Construye los query params de búsqueda round trip por proveedor.

    Puro: sin red, sin API key (la agrega `_get`). Nombres de params según
    `INFORME_FASE_11.md` §4-§5 (`type` vs `flight_type`, stops numérico vs
    enum, `exclude_conns` vs `excluded_connecting_airports`).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Provider desconocido: {provider!r}")
    try:
        travel_class = _TRAVEL_CLASS[(provider, cabin_class)]
    except KeyError:
        raise ValueError(
            f"cabin_class no soportado para {provider}: {cabin_class!r}"
        ) from None
    params: dict[str, str] = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure.isoformat(),
        "return_date": return_date.isoformat(),
        "currency": currency,
        "adults": str(passengers),
        "travel_class": travel_class,
        "stops": _stops_value(provider, max_stops),
    }
    if provider == "serpapi":
        params["type"] = "1"  # round trip
        if avoid_airports:
            params["exclude_conns"] = ",".join(avoid_airports)
    else:
        params["flight_type"] = "round_trip"
        # INFORME_FASE_11 §11: oculta self-transfer/split tickets.
        params["separate_tickets"] = "1"
        if avoid_airports:
            params["excluded_connecting_airports"] = ",".join(avoid_airports)
    return params


def _api_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if value:
                return str(value)
    return f"HTTP {response.status_code}"


class FlightsClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        *,
        timeout: float = 45.0,
        max_attempts: int = 3,
        backoff_base: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if provider not in PROVIDERS:
            raise FlightsError(f"Provider desconocido: {provider!r}")
        self._spec = PROVIDERS[provider]
        self._provider = provider
        if not api_key:
            raise FlightsAuthError(
                f"Falta {self._spec.env_var}: copia .env.example a .env "
                "y completa la API key (dashboard del proveedor)."
            )
        self._api_key = api_key
        self._http = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json"},
            transport=transport,
        )
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def env_var(self) -> str:
        return self._spec.env_var

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FlightsClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _guard_search_only(self, params: dict[str, str]) -> None:
        """Barrera en runtime: solo engine=google_flights (§12).

        No es solo un test estático: si alguien intentara apuntar este GET a
        otra cosa, falla de inmediato.
        """
        if params.get("engine") != "google_flights":
            raise FlightsError(
                "Operacion bloqueada por politica SEARCH-ONLY: "
                f"solo engine=google_flights (recibido: "
                f"{params.get('engine')!r})"
            )

    def _get(self, params: dict[str, str]) -> dict:
        self._guard_search_only(params)
        request_params = {**params, "api_key": self._api_key}
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._http.get(
                    self._spec.base_url, params=request_params
                )
            except httpx.HTTPError as exc:
                last_error = exc
                wait = self.backoff_base * (2 ** (attempt - 1))
                log.warning("Intento %d: error de red (%s)", attempt, exc)
            else:
                if response.status_code in (401, 403):
                    raise FlightsAuthError(
                        f"{self._spec.name} rechazo la API key "
                        f"({response.status_code}): invalida o expirada. "
                        f"Revisa {self._spec.env_var} en .env."
                    )
                if response.status_code == 429:
                    last_error = FlightsRateLimitError(
                        f"Rate limit (429): {_api_message(response)}"
                    )
                    retry_after = response.headers.get("Retry-After")
                    wait = (
                        float(retry_after)
                        if retry_after
                        else self.backoff_base * (2 ** (attempt - 1))
                    )
                    log.warning(
                        "Intento %d: rate limit, reintentando en %.1fs",
                        attempt,
                        wait,
                    )
                elif response.status_code >= 500:
                    last_error = FlightsNetworkError(
                        f"Error del servidor {self._spec.name}: "
                        f"{_api_message(response)}"
                    )
                    wait = self.backoff_base * (2 ** (attempt - 1))
                    log.warning("Intento %d: %s", attempt, last_error)
                elif response.status_code >= 400:
                    raise FlightsError(
                        f"{self._spec.name} devolvio error: "
                        f"{_api_message(response)}"
                    )
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise FlightsError(
                            f"Respuesta no JSON de {self._spec.name}: "
                            f"HTTP {response.status_code}"
                        ) from exc
                    if isinstance(payload, dict) and payload.get("error"):
                        # p. ej. "Google hasn't returned any results":
                        # sin itinerarios = vacio legitimo, no crash.
                        log.warning(
                            "Aviso de %s: %s",
                            self._spec.name,
                            payload["error"],
                        )
                    return payload if isinstance(payload, dict) else {}
            if attempt < self.max_attempts:
                time.sleep(wait)
        if isinstance(last_error, FlightsRateLimitError):
            raise FlightsRateLimitError(
                f"{last_error} (tras {self.max_attempts} intentos)"
            )
        raise FlightsNetworkError(
            f"Sin respuesta de {self._spec.name} tras "
            f"{self.max_attempts} intentos: {last_error}"
        )

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        departure: date,
        return_date: date,
        *,
        currency: str = "USD",
        passengers: int = 1,
        cabin_class: str = "economy",
        max_stops: int = 2,
        avoid_airports: Sequence[str] = (),
    ) -> list[dict]:
        """Busca ida+vuelta para UNA combinación de fechas (1 GET).

        Devuelve los itinerarios crudos (best_flights + other_flights);
        `[]` si no hay. La normalización a `Offer` la hace `models`.
        """
        params = map_search_params(
            self._provider,
            origin=origin,
            destination=destination,
            departure=departure,
            return_date=return_date,
            currency=currency,
            passengers=passengers,
            cabin_class=cabin_class,
            max_stops=max_stops,
            avoid_airports=avoid_airports,
        )
        payload = self._get(params)
        itineraries = extract_itineraries(payload)
        log.info(
            "%s->%s %s/%s: %d itinerarios",
            origin,
            destination,
            departure.isoformat(),
            return_date.isoformat(),
            len(itineraries),
        )
        return itineraries

    def drill_down(
        self,
        departure_token: str,
        *,
        origin: str,
        destination: str,
        departure: date,
        return_date: date,
        currency: str = "USD",
        passengers: int = 1,
        cabin_class: str = "economy",
        max_stops: int = 2,
        avoid_airports: Sequence[str] = (),
    ) -> list[dict]:
        """Obtiene las vueltas de UNA ida elegida (1 GET con departure_token).

        El token es opaco y efímero: solo drill-down inmediato de la misma
        corrida, nunca se persiste (§12.4).
        """
        if not departure_token:
            raise FlightsError("drill-down requiere un departure_token")
        params = map_search_params(
            self._provider,
            origin=origin,
            destination=destination,
            departure=departure,
            return_date=return_date,
            currency=currency,
            passengers=passengers,
            cabin_class=cabin_class,
            max_stops=max_stops,
            avoid_airports=avoid_airports,
        )
        params["departure_token"] = departure_token
        payload = self._get(params)
        return extract_itineraries(payload)

    def search_combinations(
        self,
        origin: str,
        destination: str,
        combinations: list[tuple[date, date]],
        *,
        currency: str = "USD",
        passengers: int = 1,
        cabin_class: str = "economy",
        max_stops: int = 2,
        avoid_airports: Sequence[str] = (),
    ) -> tuple[list[dict], dict[str, int]]:
        """Busca todas las combinaciones; fallos parciales no abortan el batch.

        Secuencial por defecto (sin paralelización) para respetar la cuota
        gratuita (§12.4). `FlightsAuthError` sí se propaga (key inválida =
        detener todo). Devuelve (itinerarios_crudos, stats).
        """
        all_itineraries: list[dict] = []
        stats = {"consultadas": 0, "con_resultados": 0, "fallidas": 0}
        for departure, return_date in combinations:
            stats["consultadas"] += 1
            try:
                itineraries = self.search_round_trip(
                    origin,
                    destination,
                    departure,
                    return_date,
                    currency=currency,
                    passengers=passengers,
                    cabin_class=cabin_class,
                    max_stops=max_stops,
                    avoid_airports=avoid_airports,
                )
            except FlightsAuthError:
                raise
            except FlightsError as exc:
                stats["fallidas"] += 1
                log.warning(
                    "Combinacion %s/%s fallida (se continua): %s",
                    departure.isoformat(),
                    return_date.isoformat(),
                    exc,
                )
                continue
            if itineraries:
                stats["con_resultados"] += 1
            all_itineraries.extend(itineraries)
        log.info(
            "Batch completo: %d consultadas, %d con resultados, %d fallidas, "
            "%d itinerarios en bruto",
            stats["consultadas"],
            stats["con_resultados"],
            stats["fallidas"],
            len(all_itineraries),
        )
        return all_itineraries, stats
