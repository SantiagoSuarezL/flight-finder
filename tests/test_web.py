"""Tests de Fase 13: UI web stdlib (sin red, con FakeClient).

Antifallas verificados:
- GET / y POST /search no instancian ni llaman al cliente (cero fantasma).
- POST /run ejecuta exactamente una vez aunque se repita (idempotencia).
- PRG: /run responde 303; recargar /result no re-ejecuta.
- Store acotado (MAX_TOKENS) + TTL.
- Todo input reflejado va escapado.
"""

import http.client
import json
import re
import threading
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytest

import flight_finder.web as web_mod
from flight_finder.web import (
    MAX_TOKENS,
    TOKEN_TTL_S,
    ServerState,
    build_config,
    create_handler,
    render_error,
    render_pending,
)

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_response.json"

TOKEN_RE = re.compile(r"name='token' value='([0-9a-f]{32})'")


def _future(days=60):
    return (date.today() + timedelta(days=days)).isoformat()


def _form(**overrides):
    data = {
        "origin": "BOG",
        "destination": "MAD",
        "date_mode": "fixed",
        "date_value": _future(),
        "stay_min": "10",
        "stay_max": "10",
        "max_combinations": "1",
        "provider": "serpapi",
        "currency": "USD",
        "drill": "off",
        "avoid_countries": "US",
        "avoid_airports": "ATL",
        "max_stops": "2",
        "top_n": "3",
    }
    data.update(overrides)
    return data


class FakeClient:
    calls = {"search": 0, "drill": 0, "instances": 0}

    def __init__(self, provider, api_key, **kwargs):
        type(self).calls["instances"] += 1
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self._raws = list(payload.get("best_flights", []))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def search_round_trip(self, *args, **kwargs):
        type(self).calls["search"] += 1
        return list(self._raws)

    def drill_down(self, *args, **kwargs):
        type(self).calls["drill"] += 1
        return []


def _factory(provider, api_key, **kwargs):
    return FakeClient(provider, api_key, **kwargs)


@pytest.fixture()
def server():
    FakeClient.calls = {"search": 0, "drill": 0, "instances": 0}
    handler, state = create_handler(_factory)
    from http.server import ThreadingHTTPServer

    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{srv.server_port}", state
    srv.shutdown()
    thread.join(timeout=5)
    srv.server_close()


def _conn(addr):
    host, port = addr.split(":")
    return http.client.HTTPConnection(host, int(port), timeout=10)


def _get(addr, path):
    conn = _conn(addr)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    headers = dict(resp.getheaders())
    conn.close()
    return resp.status, body, headers


def _post(addr, path, data):
    conn = _conn(addr)
    body = urlencode(data).encode("utf-8")
    conn.request(
        "POST", path, body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp = conn.getresponse()
    payload = resp.read().decode("utf-8")
    headers = dict(resp.getheaders())
    conn.close()
    return resp.status, payload, headers


def _estimate_token(addr):
    status, body, _ = _post(addr, "/search", _form())
    assert status == 200
    match = TOKEN_RE.search(body)
    assert match, "la estimacion debe traer token de un solo uso"
    return match.group(1), body


def _wait_result(addr, token, timeout=15):
    """Poll de /result hasta estado done (corrida async en background)."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body, _ = _get(addr, f"/result?token={token}")
        assert status == 200
        if "SOURCE:" in body or "Sin resultados validos" in body:
            return body
        time.sleep(0.2)
    raise AssertionError("la corrida no termino a tiempo")


def test_get_form_no_toca_red(server):
    addr, _ = server
    status, body, _ = _get(addr, "/")
    assert status == 200
    assert "<form" in body and "Ver estimacion" in body
    assert FakeClient.calls["instances"] == 0
    assert FakeClient.calls["search"] == 0


def test_search_estima_sin_requests(server):
    addr, _ = server
    token, body = _estimate_token(addr)
    assert "Maximo de API requests" in body
    assert "Confirmar y buscar" in body
    assert FakeClient.calls["instances"] == 0
    assert FakeClient.calls["search"] == 0


def test_search_invalido_no_gasta_y_explica(server):
    addr, _ = server
    status, body, _ = _post(addr, "/search", _form(destination="BOG"))
    assert status == 200
    assert "no pueden ser iguales" in body
    assert FakeClient.calls["search"] == 0

    status, body, _ = _post(addr, "/search", _form(date_value="ayer"))
    assert status == 200
    assert "AAAA-MM-DD" in body
    assert FakeClient.calls["search"] == 0


def test_run_flujo_completo_prg_y_csv(server):
    addr, _ = server
    token, _ = _estimate_token(addr)
    status, _, headers = _post(addr, "/run", {**_form(), "token": token})
    assert status == 303
    assert headers.get("Location") == f"/result?token={token}"

    body = _wait_result(addr, token)
    assert "SOURCE: SerpApi (Google Flights)" in body
    assert "LINK: <a href='https://www.google.com/travel/flights?q=" in body
    assert "VALID OFFERS:" in body
    assert FakeClient.calls["search"] == 1  # 1 combo = 1 request
    assert FakeClient.calls["drill"] == 0  # drill off

    status, body, headers = _get(addr, f"/csv?token={token}")
    assert status == 200
    assert "text/csv" in headers.get("Content-Type", "")
    assert body.splitlines()[0].startswith("puesto,precio")


def test_doble_post_y_reload_no_repiten(server):
    addr, _ = server
    token, _ = _estimate_token(addr)
    form = {**_form(), "token": token}
    first = _post(addr, "/run", form)
    second = _post(addr, "/run", form)
    assert first[0] == 303 and second[0] == 303
    assert first[2].get("Location") == second[2].get("Location")
    _wait_result(addr, token)
    assert FakeClient.calls["search"] == 1  # exactamente una corrida

    before = FakeClient.calls["search"]
    status, _, _ = _get(addr, f"/result?token={token}")
    assert status == 200
    assert FakeClient.calls["search"] == before  # reload = replay


def test_token_invalido_no_gasta(server):
    addr, _ = server
    status, _, _ = _post(addr, "/run", {**_form(), "token": "0" * 32})
    assert status == 400
    assert FakeClient.calls["search"] == 0
    status, _, _ = _get(addr, "/result?token=" + "0" * 32)
    assert status == 404


def test_ruta_inexistente_404(server):
    addr, _ = server
    status, _, _ = _get(addr, "/nope")
    assert status == 404


def test_body_gigante_rechazado_sin_gastar(server):
    addr, _ = server
    conn = _conn(addr)
    big = "x" * (web_mod.MAX_BODY_BYTES + 1)
    conn.request(
        "POST", "/search", body=big.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    # Por diseno /search re-muestra el formulario (200) con el error.
    assert resp.status == 200
    assert "demasiado grande" in body
    assert FakeClient.calls["search"] == 0


def test_store_acotado_y_ttl():
    state = ServerState(_factory)
    for _ in range(MAX_TOKENS + 5):
        state.mint({"origin": "BOG"})
    assert state.count() <= MAX_TOKENS  # eviccion del mas viejo

    token = state.mint({"origin": "BOG"})
    assert state.claim(token) == "run"
    assert state.claim(token) == "replay"  # segundo claim no re-ejecuta
    assert state.claim("f" * 32) == "missing"

    # Expiracion por TTL.
    with state._lock:
        state._store[token]["created"] -= TOKEN_TTL_S + 1
    assert state.get(token) is None
    assert state.claim(token) == "missing"


def test_error_escapa_input():
    status, body = render_error("<script>alert(1)</script>")
    text = body.decode("utf-8")
    assert status == 400
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_form_invalido_escapa_input(server):
    addr, _ = server
    status, body, _ = _post(addr, "/search", _form(origin="<b>BOG"))
    assert status == 200
    assert "<b>BOG" not in body  # el valor crudo jamas vuelve sin escapar


def test_build_config_reusa_pydantic():
    cfg = build_config(_form())
    assert cfg.provider == "serpapi"
    assert cfg.search.origin == "BOG"
    with pytest.raises(Exception, match="no pueden ser iguales"):
        build_config(_form(destination="BOG"))


def test_pending_muestra_progreso_y_cancelar():
    body = render_pending("abc123", 2, 6).decode("utf-8")
    assert "Progreso: 2/6" in body
    assert "refresh" in body
    assert "Cancelar busqueda" in body
    body = render_pending("abc123").decode("utf-8")
    assert "Iniciando" in body


class SlowClient(FakeClient):
    gate = None

    def search_round_trip(self, *args, **kwargs):
        type(self).calls["search"] += 1
        assert type(self).gate is not None
        type(self).gate.wait(timeout=15)
        return list(self._raws)


def _slow_factory(provider, api_key, **kwargs):
    return SlowClient(provider, api_key, **kwargs)


@pytest.fixture()
def slow_server():
    SlowClient.calls = {"search": 0, "drill": 0, "instances": 0}
    SlowClient.gate = __import__("threading").Event()
    handler, state = create_handler(_slow_factory)
    from http.server import ThreadingHTTPServer

    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = __import__("threading").Thread(
        target=srv.serve_forever, daemon=True
    )
    thread.start()
    yield f"127.0.0.1:{srv.server_port}", state
    SlowClient.gate.set()
    srv.shutdown()
    thread.join(timeout=5)
    srv.server_close()


def test_cancel_frena_corrida_y_muestra_parcial(slow_server):
    import time

    addr, _ = slow_server
    form = _form(stay_min="10", stay_max="12", max_combinations="3")
    status, body, _ = _post(addr, "/search", form)
    assert status == 200
    token = TOKEN_RE.search(body).group(1)

    status, _, _ = _post(addr, "/run", {**form, "token": token})
    assert status == 303
    time.sleep(1)  # la corrida queda bloqueada en el combo 1
    status, _, _ = _post(addr, "/cancel", {"token": token})
    assert status == 303
    SlowClient.gate.set()  # libera el request en vuelo
    body = _wait_result(addr, token)
    assert "cancelada por el usuario" in body
    assert SlowClient.calls["search"] == 1  # no lanzo los combos 2 y 3


def test_run_search_reporta_progreso_y_cancela():
    from flight_finder.search import run_search

    cfg = build_config(_form(stay_min="10", stay_max="12", max_combinations="3"))
    seen = []
    outcome = run_search(
        cfg,
        FakeClient("serpapi", "k"),
        {},
        on_progress=lambda done, total: seen.append((done, total)),
    )
    assert seen[-1] == (3, 3)  # un reporte por combo
    assert outcome.stats["consultadas"] == 3

    calls = {"n": 0}

    def cancel_after_first():
        return calls["n"] >= 1

    class Counting(FakeClient):
        def search_round_trip(self, *a, **k):
            calls["n"] += 1
            return super().search_round_trip(*a, **k)

    outcome = run_search(
        cfg, Counting("serpapi", "k"), {}, should_cancel=cancel_after_first
    )
    assert outcome.cancelled is True
    assert calls["n"] == 1  # freno antes del combo 2
