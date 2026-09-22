"""Interfaz web local (stdlib solamente) — Fase 13.

Sin dependencias nuevas: `http.server` + `urllib` + `html`. Solo escucha en
`127.0.0.1` (un usuario local; las API keys quedan en el proceso servidor,
nunca viajan al HTML).

Flujo anti-cuota y anti-doble-ejecucion:
- `GET /` → solo formulario (cero requests).
- `POST /search` → valida y muestra la ESTIMACION (cero requests) con un
  token de un solo uso + boton Confirmar.
- `POST /run` → consume el token y ejecuta exactamente una vez; responde
  `303` a `GET /result?token=...` (PRG: recargar no re-ejecuta).
- Doble click / doble POST con el mismo token → 303 a la misma pagina de
  resultado (en curso → con auto-refresh; terminado → resultado guardado).
  Nunca se repite la busqueda: el token pasa estimated → running → done.
- Memoria acotada: como maximo `MAX_TOKENS` registros con TTL (`TOKEN_TTL_S`);
  limpieza en cada POST + eviccion del mas viejo. Sin archivos de estado.

La busqueda misma la hace `search.run_search` (mismo nucleo que el CLI).
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import logging
import os
import secrets
import sys
import threading
import time
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from flight_finder.config import FlightFinderConfig
from flight_finder.filters import load_airport_country_map
from flight_finder.flights_client import PROVIDERS, FlightsAuthError
from flight_finder.presenter import (
    airlines,
    fmt_datetime,
    fmt_duration,
    format_carbon,
    format_offer_card,
    google_flights_url,
    rows_for_export,
)
from flight_finder.search import estimate_requests, plan_combinations, run_search

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data"

BIND_HOST = "127.0.0.1"  # local solamente, por diseno (las keys viven aca)
DEFAULT_PORT = 8080

MAX_BODY_BYTES = 64 * 1024
MAX_TOKENS = 32  # registros en memoria como maximo (tokens + resultados)
TOKEN_TTL_S = 15 * 60  # un token/resultados vive 15 minutos
MAX_WEB_TOP_N = 50  # tope de UI (acota memoria y requests del drill-down)
MAX_WEB_COMBINATIONS = 31  # tope de UI (acota requests por corrida)

log = logging.getLogger(__name__)


class WebInputError(Exception):
    """Dato del formulario invalido (mensaje ya humano)."""


# --- Formulario <-> config (puro, sin red) -----------------------------------

FIELDS = (
    "origin",
    "destination",
    "date_mode",
    "date_value",
    "stay_min",
    "stay_max",
    "max_combinations",
    "provider",
    "currency",
    "drill",
    "avoid_countries",
    "avoid_airports",
    "max_stops",
    "top_n",
)


def _int(value: str, name: str) -> int:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        raise WebInputError(f"{name} debe ser un numero entero.") from None


def _codes(text: str) -> list[str]:
    return [c for c in text.replace(",", " ").upper().split() if c]


def build_config(data: dict[str, str]) -> FlightFinderConfig:
    """Valida el formulario con los modelos pydantic del proyecto.

    Lanza `WebInputError` con mensaje humano. No toca la red.
    """
    mode = (data.get("date_mode") or "fixed").strip()
    if mode not in ("fixed", "before"):
        raise WebInputError("date_mode debe ser fixed o before.")
    departure = {"fixed_date": None, "before": None}
    try:
        parsed = date.fromisoformat((data.get("date_value") or "").strip())
    except ValueError:
        raise WebInputError(
            "La fecha debe tener formato AAAA-MM-DD (ej. 2026-10-15)."
        ) from None
    departure["fixed_date" if mode == "fixed" else "before"] = parsed.isoformat()

    top_n = _int(data.get("top_n", "10"), "top_n")
    if not 1 <= top_n <= MAX_WEB_TOP_N:
        raise WebInputError(f"top_n debe estar entre 1 y {MAX_WEB_TOP_N}.")
    max_comb = _int(data.get("max_combinations", "6"), "max_combinations")
    if not 1 <= max_comb <= MAX_WEB_COMBINATIONS:
        raise WebInputError(
            f"max_combinations debe estar entre 1 y {MAX_WEB_COMBINATIONS}."
        )

    raw = {
        "provider": (data.get("provider") or "").strip(),
        "currency": (data.get("currency") or "USD").strip().upper(),
        "search": {
            "origin": (data.get("origin") or "").strip().upper(),
            "destination": (data.get("destination") or "").strip().upper(),
            "passengers": 1,
            "cabin_class": "economy",
            "max_combinations": max_comb,
            "drill_down": (data.get("drill") or "top_n").strip(),
        },
        "departure": departure,
        "stay": {
            "min_days": _int(data.get("stay_min", "10"), "stay_min"),
            "max_days": _int(data.get("stay_max", "15"), "stay_max"),
        },
        "avoid": {
            "countries": _codes(data.get("avoid_countries", "")),
            "airports": _codes(data.get("avoid_airports", "")),
        },
        "max_stops": _int(data.get("max_stops", "2"), "max_stops"),
        "sort": {"primary": "total_price", "secondary": "duration"},
        "output": {"top_n": top_n, "export": None},
    }
    try:
        return FlightFinderConfig.model_validate(raw)
    except ValidationError as exc:
        msgs = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'config'}: {e['msg']}"
            for e in exc.errors()
        )
        raise WebInputError(f"Configuracion invalida — {msgs}") from None


def default_form() -> dict[str, str]:
    """Precarga del formulario (de `config.example.yaml`, con fallback)."""
    import yaml

    fallback = {
        "origin": "BOG",
        "destination": "MAD",
        "date_mode": "before",
        "date_value": "2026-12-15",
        "stay_min": "10",
        "stay_max": "15",
        "max_combinations": "6",
        "provider": "serpapi",
        "currency": "USD",
        "drill": "top_n",
        "avoid_countries": "US",
        "avoid_airports": "ATL",
        "max_stops": "2",
        "top_n": "3",  # preset óptimo: 6 combos + drill top 3 = 9 requests
    }
    example = DATA_PATH.parent / "config.example.yaml"
    try:
        raw = yaml.safe_load(example.read_text(encoding="utf-8"))
        dep = raw.get("departure", {})
        mode = "fixed" if dep.get("fixed_date") else "before"
        return {
            "origin": str(raw["search"]["origin"]),
            "destination": str(raw["search"]["destination"]),
            "date_mode": mode,
            "date_value": str(dep.get("fixed_date") or dep.get("before") or ""),
            "stay_min": str(raw["stay"]["min_days"]),
            "stay_max": str(raw["stay"]["max_days"]),
            "max_combinations": str(raw["search"]["max_combinations"]),
            "provider": str(raw.get("provider", "serpapi")),
            "currency": str(raw.get("currency", "USD")),
            "drill": str(raw["search"].get("drill_down", "top_n")),
            "avoid_countries": ",".join(raw.get("avoid", {}).get("countries", [])),
            "avoid_airports": ",".join(raw.get("avoid", {}).get("airports", [])),
            "max_stops": str(raw.get("max_stops", 2)),
            "top_n": str(raw.get("output", {}).get("top_n", 10)),
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return fallback


# --- HTML (puro; todo input escapado) ------------------------------------------

_CSS = (
    "body{font-family:sans-serif;max-width:900px;margin:2em auto;padding:0 1em}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border:1px solid #999;padding:.3em .6em;text-align:left}"
    ".card{border:1px solid #999;padding:.6em;margin:.6em 0;white-space:pre-wrap}"
    ".warn{background:#fff3cd;padding:.6em;border:1px solid #cc9}"
    ".err{background:#fdd;padding:.6em;border:1px solid #c99}"
)


def _page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    ).encode("utf-8")


def _input_row(label: str, field: str, value: str, extra: str = "") -> str:
    return (
        f"<label>{html.escape(label)} "
        f"<input name='{field}' value='{html.escape(value)}'{extra}></label><br>"
    )


def render_form(defaults: dict[str, str], error: str | None = None) -> bytes:
    d = {k: defaults.get(k, "") for k in FIELDS}
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    opts = "".join(
        f"<option value='{p}'{' selected' if d['provider'] == p else ''}>{p}</option>"
        for p in PROVIDERS
    )
    drill_opts = "".join(
        f"<option value='{v}'{' selected' if d['drill'] == v else ''}>{v}</option>"
        for v in ("top_n", "off")
    )
    mode_opts = "".join(
        f"<option value='{v}'{' selected' if d['date_mode'] == v else ''}>{v}</option>"
        for v in ("fixed", "before")
    )
    body = (
        f"{err}<form method='POST' action='/search' "
        "onsubmit=\"this.querySelector('button[type=submit]').disabled=true;"
        "this.querySelector('button[type=submit]').textContent='Calculando...'"
        "\">"
        f"{_input_row('Origen (IATA)', 'origin', d['origin'])}"
        f"{_input_row('Destino (IATA)', 'destination', d['destination'])}"
        f"<label>Fecha <select name='date_mode'>{mode_opts}</select></label> "
        f"<input name='date_value' value='{html.escape(d['date_value'])}"
        "' placeholder='AAAA-MM-DD'><br>"
        f"{_input_row('Estadia min (dias)', 'stay_min', d['stay_min'])}"
        f"{_input_row('Estadia max (dias)', 'stay_max', d['stay_max'])}"
        f"{_input_row('Max combinaciones', 'max_combinations', d['max_combinations'])}"
        f"<label>Proveedor <select name='provider'>{opts}</select></label><br>"
        f"{_input_row('Moneda', 'currency', d['currency'])}"
        f"<label>Drill-down <select name='drill'>{drill_opts}</select></label><br>"
        f"{_input_row('Evitar paises (ISO, coma)', 'avoid_countries', d['avoid_countries'])}"
        f"{_input_row('Evitar aeropuertos (IATA, coma)', 'avoid_airports', d['avoid_airports'])}"
        f"{_input_row('Max escalas', 'max_stops', d['max_stops'])}"
        f"{_input_row('Top N', 'top_n', d['top_n'])}"
        "<p class='warn'>La busqueda gasta cuota gratuita (SerpApi 250/mes, "
        "SearchApi 100). El siguiente paso muestra la estimacion exacta "
        "ANTES de gastar — nada se ejecuta desde este formulario.</p>"
        "<button type='submit'>Ver estimacion</button></form>"
    )
    return _page("flight-finder — nueva busqueda", body)


def render_estimate(
    cfg: FlightFinderConfig,
    n_effective: int,
    n_total: int,
    truncated: int,
    max_requests: int,
    data: dict[str, str],
    token: str,
) -> bytes:
    hidden = "".join(
        f"<input type='hidden' name='{k}' value='{html.escape(data.get(k, ''))}'>"
        for k in FIELDS
    )
    combo_note = (
        f" (de {n_total} generadas; {truncated} omitidas por max_combinations)"
        if truncated
        else ""
    )
    drill_note = (
        f"+{cfg.output.top_n} drill-down top_n"
        if cfg.search.drill_down == "top_n"
        else "drill-down off"
    )
    body = (
        "<ul>"
        f"<li>Combinaciones: <b>{n_effective}</b>{html.escape(combo_note)}</li>"
        f"<li>Maximo de API requests: <b>{max_requests}</b> "
        f"({html.escape(drill_note)})</li>"
        f"<li>Proveedor: <b>{html.escape(cfg.provider)}</b></li>"
        "<li>Search-only: no se reserva ni se paga nada.</li>"
        "</ul>"
        "<form method='POST' action='/run' "
        "onsubmit=\"this.querySelector('button[type=submit]').disabled=true;"
        "this.querySelector('button[type=submit]').textContent='Buscando...'"
        "\">"
        f"{hidden}<input type='hidden' name='token' value='{token}'>"
        "<button type='submit'>Confirmar y buscar "
        f"(hasta {max_requests} requests)</button></form>"
        "<p><a href='/'>Volver (no se gasto nada)</a></p>"
    )
    return _page("flight-finder — estimacion (sin gasto aun)", body)


def render_result(
    cfg: FlightFinderConfig,
    outcome,
    token: str,
    elapsed_s: float,
) -> bytes:
    name = {"serpapi": "SerpApi", "searchapi": "SearchApi"}.get(
        cfg.provider, cfg.provider
    )
    parts = [
        f"<p>SOURCE: {html.escape(name)} (Google Flights)<br>"
        f"Combinaciones consultadas: {outcome.stats['consultadas']} / "
        f"con resultados: {outcome.stats['con_resultados']} / "
        f"fallidas: {outcome.stats['fallidas']}<br>"
        f"NOTE: displayed prices from Google Flights - not bookable offers; "
        f"final price and availability may change at booking<br>"
        f"Busqueda completada en {elapsed_s:.1f}s.</p>",
    ]
    if getattr(outcome, "cancelled", False):
        parts.append(
            "<p class='warn'>Corrida cancelada por el usuario: resultados "
            "parciales (solo lo consultado hasta la cancelacion).</p>"
        )
    top = outcome.ordered[: cfg.output.top_n]
    if top:
        rows = []
        for i, offer in enumerate(top, 1):
            out = offer.outbound
            back = offer.inbound
            if back is None:
                vuelta = "not expanded (cheapest return included in price)"
            else:
                vuelta = (
                    f"{fmt_datetime(back.segments[0].departure_time)} "
                    f"{back.segments[0].origin} -> {back.segments[-1].destination}"
                )
            rows.append(
                "<tr><td>" + "</td><td>".join(
                    html.escape(c)
                    for c in (
                        str(i),
                        f"{offer.price} {offer.currency}",
                        f"{fmt_datetime(out.segments[0].departure_time)} "
                        f"{out.segments[0].origin} -> {out.segments[-1].destination}",
                        vuelta,
                        airlines(offer),
                        fmt_duration(offer.total_duration_minutes),
                        format_carbon(offer),
                    )
                ) + "</td></tr>"
            )
        parts.append(
            "<table><thead><tr><th>#</th><th>Precio</th><th>Ida</th>"
            "<th>Vuelta</th><th>Aerolineas</th><th>Duracion</th>"
            "<th>Carbon</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>"
        )
        for i, offer in enumerate(top, 1):
            entry = outcome.combo_of.get(offer.id)
            card = html.escape(
                format_offer_card(
                    offer, i, return_date=entry[1] if entry else None
                )
            )
            # Link clicable dentro de la card (URL ya ASCII segura).
            link = None
            if entry:
                link = google_flights_url(
                    offer.outbound.segments[0].origin,
                    offer.outbound.segments[-1].destination,
                    offer.outbound.segments[0].departure_time.date(),
                    entry[1],
                )
            if link:
                card = card.replace(
                    html.escape(link),
                    f"<a href='{html.escape(link)}'>{html.escape(link)}</a>",
                )
            parts.append(f"<div class='card'>{card}</div>")
        c = outcome.discard_reasons
        parts.append(
            "<p>VALID OFFERS: "
            f"{len(outcome.ordered)} / FILTERED BY US: "
            f"{sum(v for k, v in c.items() if 'pais excluido' in k)} / "
            f"FILTERED BY AIRPORT: "
            f"{sum(v for k, v in c.items() if 'aeropuerto excluido' in k)} / "
            f"FILTERED BY MAX STOPS: "
            f"{sum(v for k, v in c.items() if 'Exceso de escalas' in k)}</p>"
        )
        parts.append(
            f"<p><a href='/csv?token={html.escape(token)}'>Descargar CSV</a></p>"
        )
    else:
        reasons = "".join(
            f"<li>{n}x: {html.escape(str(r))}</li>"
            for r, n in outcome.discard_reasons.most_common()
        )
        parts.append(
            f"<p>Sin resultados validos: {outcome.total_raw} ofertas en bruto, "
            f"{sum(outcome.discard_reasons.values())} descartadas.</p>"
            f"<ul>{reasons}</ul>"
        )
    parts.append("<p><a href='/'>Nueva busqueda</a></p>")
    return _page("flight-finder — resultados", "".join(parts))


def render_pending(token: str, done: int = 0, total: int = 0) -> bytes:
    if total:
        progress = f"<p>Progreso: {done}/{total} combinaciones consultadas.</p>"
    else:
        progress = "<p>Iniciando busqueda…</p>"
    body = (
        f"{progress}<p>Esta pagina se actualiza sola.</p>"
        f"<meta http-equiv='refresh' content='2;url=/result?token={html.escape(token)}'>"
        f"<form method='POST' action='/cancel' "
        "onsubmit=\"this.querySelector('button[type=submit]').disabled=true;"
        "this.querySelector('button[type=submit]').textContent='Cancelando...'"
        "\">"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<button type='submit'>Cancelar busqueda</button></form>"
        "<p><a href='/'>Volver al formulario (la busqueda sigue en curso)</a></p>"
    )
    return _page("flight-finder — buscando…", body)


def render_error(message: str, status: int = 400) -> tuple[int, bytes]:
    return status, _page(
        "flight-finder — error",
        f"<p class='err'>{html.escape(message)}</p>"
        "<p><a href='/'>Volver al formulario</a></p>",
    )


# --- Estado del servidor (acotado) ----------------------------------------------

class ServerState:
    """Tokens de un solo uso + resultados guardados, todo acotado por
    `MAX_TOKENS` y `TOKEN_TTL_S`. Un token vale para UNA corrida: el flujo
    es estimated → running → done; re-POSTs redirigen al resultado."""

    def __init__(self, client_factory):
        self._factory = client_factory
        self._lock = threading.Lock()
        self._store: dict[str, dict] = {}

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [
            t for t, r in self._store.items()
            if now - r["created"] > TOKEN_TTL_S
        ]
        for t in expired:
            del self._store[t]
        while len(self._store) > MAX_TOKENS:
            oldest = min(self._store, key=lambda t: self._store[t]["created"])
            del self._store[oldest]

    def mint(self, form: dict[str, str]) -> str:
        with self._lock:
            token = secrets.token_hex(16)
            self._store[token] = {
                "state": "estimated",
                "form": dict(form),
                "created": time.monotonic(),
                "progress": {"done": 0, "total": 0},
                "cancel": False,
            }
            self._sweep()  # despues de agregar: nunca supera MAX_TOKENS
            return token

    def claim(self, token: str) -> str:
        """Intenta adueñarse del token para correr la busqueda.

        Devuelve 'run' (este llamante es el dueño y debe ejecutar),
        'replay' (ya en curso o terminada: redirigir al resultado) o
        'missing' (token inexistente o expirado).
        """
        with self._lock:
            self._sweep()
            rec = self._store.get(token)
            if rec is None or not token:
                return "missing"
            if rec["state"] != "estimated":
                return "replay"
            rec["state"] = "running"
            return "run"

    def finish(self, token: str, html_page: bytes, csv_text: str) -> None:
        with self._lock:
            rec = self._store.get(token)
            if rec is None:
                return
            rec.update(
                {"state": "done", "html": html_page, "csv": csv_text}
            )

    def get(self, token: str) -> dict | None:
        with self._lock:
            self._sweep()
            return self._store.get(token)

    def set_progress(self, token: str, done: int, total: int) -> None:
        with self._lock:
            rec = self._store.get(token)
            if rec is not None:
                rec["progress"] = {"done": done, "total": total}

    def request_cancel(self, token: str) -> bool:
        """Pide cancelar una corrida en curso. True si estaba corriendo."""
        with self._lock:
            rec = self._store.get(token)
            if rec is None or rec["state"] != "running":
                return False
            rec["cancel"] = True
            return True

    def is_cancelled(self, token: str) -> bool:
        with self._lock:
            rec = self._store.get(token)
            return rec is not None and bool(rec.get("cancel"))

    def count(self) -> int:
        with self._lock:
            return len(self._store)


def outcome_to_csv(outcome) -> str:
    buf = io.StringIO()
    rows = rows_for_export(outcome.ordered, len(outcome.ordered))
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return buf.getvalue()


def execute_run(state: ServerState, token: str) -> None:
    """Ejecuta la busqueda del token y guarda el resultado.

    Solo la llama el dueño del token (ver `claim`): un doble POST
    concurrente recibe 'replay' y jamas llega aca, asi que la corrida
    ocurre exactamente una vez. No mantiene el lock durante la red.
    Ante cualquier error, el token termina en `done` con pagina de error
    (nunca queda colgado en `running`; el TTL lo limpiaria igual).
    """
    with state._lock:
        rec = state._store.get(token)
        if rec is None or rec["state"] != "running":
            return
        form = dict(rec["form"])
    started = time.monotonic()

    def on_progress(done: int, total: int) -> None:
        state.set_progress(token, done, total)

    def should_cancel() -> bool:
        return state.is_cancelled(token)

    try:
        cfg = build_config(form)
        airport_country_map = load_airport_country_map(
            DATA_PATH / "country_airports.json"
        )
        env_var = PROVIDERS[cfg.provider].env_var
        api_key = os.getenv(env_var, "")
        client = state._factory(cfg.provider, api_key)
        outcome = run_search(
            cfg, client, airport_country_map,
            on_progress=on_progress, should_cancel=should_cancel,
        )
        elapsed = time.monotonic() - started
        state.finish(
            token,
            render_result(cfg, outcome, token, elapsed),
            outcome_to_csv(outcome),
        )
        log.info(
            "Web run %s: %s->%s %d combos, %d validas (%.1fs)",
            token[:8],
            cfg.search.origin,
            cfg.search.destination,
            len(outcome.effective),
            len(outcome.ordered),
            elapsed,
        )
    except FlightsAuthError as exc:
        # Mensaje sin la key (solo el nombre de la env var).
        state.finish(token, render_error(str(exc))[1], "")
    except (WebInputError, OSError, ValueError) as exc:
        state.finish(token, render_error(str(exc))[1], "")
    except Exception:  # noqa: BLE001 — pagina generica, sin detalle
        log.warning("Web run %s: error interno", token[:8], exc_info=True)
        state.finish(
            token,
            render_error(
                "Error interno inesperado (sin detalle por seguridad)."
            )[1],
            "",
        )


# --- HTTP -----------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    state: ServerState  # inyectado por create_handler
    server_version = "flight-finder-web/13"

    def log_message(self, *args):  # silencioso: log estructurado en execute_run
        pass

    def _send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_form(self) -> dict[str, str]:
        data = _read_form_unbound(self)
        self._form_data = data
        return data

    def do_GET(self) -> None:  # noqa: N802 (API de BaseHTTPRequestHandler)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, render_form(default_form()))
        elif parsed.path == "/result":
            qs = urllib.parse.parse_qs(parsed.query)
            rec = self.state.get((qs.get("token") or [""])[0])
            if rec is None:
                status, body = render_error(
                    "Resultado inexistente o expirado (15 min). "
                    "Hace una busqueda nueva.",
                    404,
                )
                self._send(status, body)
            elif rec["state"] == "done":
                self._send(200, rec["html"])
            else:
                token_qs = (qs.get("token") or [""])[0]
                prog = rec.get("progress") or {"done": 0, "total": 0}
                self._send(
                    200,
                    render_pending(
                        token_qs, prog.get("done", 0), prog.get("total", 0)
                    ),
                )
        elif parsed.path == "/csv":
            qs = urllib.parse.parse_qs(parsed.query)
            rec = self.state.get((qs.get("token") or [""])[0])
            if rec is None or rec["state"] != "done":
                status, body = render_error(
                    "CSV inexistente o expirado (15 min).", 404
                )
                self._send(status, body)
            else:
                payload = rec["csv"].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header(
                    "Content-Disposition",
                    "attachment; filename=vuelos.csv",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        else:
            status, body = render_error("Pagina inexistente.", 404)
            self._send(status, body)

    def do_POST(self) -> None:  # noqa: N802 (API de BaseHTTPRequestHandler)
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/search":
                data = self._read_form()
                cfg = build_config(data)  # valida; cero requests
                all_combos, effective, truncated = plan_combinations(cfg)
                max_requests = estimate_requests(cfg, len(effective))
                token = self.state.mint(
                    {k: data.get(k, "") for k in FIELDS}
                )
                self._send(
                    200,
                    render_estimate(
                        cfg,
                        len(effective),
                        len(all_combos),
                        truncated,
                        max_requests,
                        data,
                        token,
                    ),
                )
            elif parsed.path == "/run":
                data = self._read_form()
                token = (data.get("token") or "").strip()
                verdict = self.state.claim(token)
                if verdict == "missing":
                    status, body = render_error(
                        "Confirmacion expirada o invalida (hace la busqueda "
                        "de nuevo desde el formulario).",
                        400,
                    )
                    self._send(status, body)
                    return
                if verdict == "replay":
                    # Doble click / re-POST / refresh: redirigir al mismo
                    # resultado, jamas re-ejecutar.
                    self._redirect(f"/result?token={token}")
                    return
                # 'run': lanzar en background y redirigir YA (PRG). El
                # navegador muestra progreso en vivo en vez de colgarse
                # los ~2 min que tarda el proveedor en responder.
                thread = threading.Thread(
                    target=execute_run, args=(self.state, token), daemon=True
                )
                thread.start()
                self._redirect(f"/result?token={token}")
            elif parsed.path == "/cancel":
                data = self._read_form()
                token = (data.get("token") or "").strip()
                self.state.request_cancel(token)  # no-op si ya termino
                self._redirect(f"/result?token={token}")
            else:
                status, body = render_error("Pagina inexistente.", 404)
                self._send(status, body)
        except WebInputError as exc:
            if parsed.path == "/search":
                # Re-muestra el formulario con los datos cargados + error.
                data = getattr(self, "_form_data", {})
                self._send(200, render_form(data or default_form(), str(exc)))
            else:
                status, body = render_error(str(exc), 400)
                self._send(status, body)


def _read_form_unbound(handler: _Handler) -> dict[str, str]:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        raise WebInputError("Content-Length invalido.")
    if length <= 0:
        return {}
    if length > MAX_BODY_BYTES:
        raise WebInputError("Formulario demasiado grande.")
    raw = handler.rfile.read(length)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise WebInputError("El formulario debe estar en UTF-8.") from None
    return {
        k: v[0]
        for k, v in urllib.parse.parse_qs(text, keep_blank_values=True).items()
    }


def create_handler(client_factory):
    """Fabrica el handler con la factoria de clientes inyectada.

    En produccion: `FlightsClient`. En tests: un fake que cuenta llamadas
    (cero red).
    """
    state = ServerState(client_factory)

    class Handler(_Handler):
        pass

    Handler.state = state
    return Handler, state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interfaz web local de flight-finder (solo 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Puerto local"
    )
    return parser


def _entrypoint() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        print(f"Puerto invalido: {args.port} (1-65535).", file=sys.stderr)
        sys.exit(2)
    load_dotenv()
    from flight_finder.flights_client import FlightsClient

    if not os.getenv("SERP_API", "") and not os.getenv("SEARCH_API_IO", ""):
        print(
            "Faltan SERP_API y SEARCH_API_IO: copia .env.example a .env "
            "y completa al menos una API key.",
            file=sys.stderr,
        )
        sys.exit(1)
    handler, _ = create_handler(FlightsClient)
    server = ThreadingHTTPServer((BIND_HOST, args.port), handler)
    print(f"Sirviendo en http://{BIND_HOST}:{args.port} (local solamente).")
    print("Ctrl+C para detener. La busqueda gasta cuota: siempre pide confirmacion.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    _entrypoint()
