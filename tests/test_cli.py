"""Tests de Fase 7 + 11: CLI (solo rutas sin red)."""

from datetime import date, timedelta

import yaml

import flight_finder.cli as cli_mod
from flight_finder.cli import build_parser, main


def _write_config(tmp_path, **overrides):
    future = (date.today() + timedelta(days=60)).isoformat()
    cfg = {
        "provider": "serpapi",
        "currency": "USD",
        "search": {
            "origin": "BOG",
            "destination": "MAD",
            "passengers": 1,
            "cabin_class": "economy",
            "max_combinations": 2,
            "drill_down": "off",
        },
        "departure": {"fixed_date": future, "before": None},
        "stay": {"min_days": 10, "max_days": 11},
        "avoid": {"countries": ["US"], "airports": ["ATL"]},
        "max_stops": 2,
        "sort": {"primary": "total_price", "secondary": "duration"},
        "output": {"top_n": 10, "export": None},
    }
    cfg.update(overrides)
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


def test_config_por_defecto_es_config_yaml():
    assert build_parser().parse_args([]).config == "config.yaml"


def test_flag_config_apunta_a_otro_archivo():
    args = build_parser().parse_args(["--config", "otra_busqueda.yaml"])
    assert args.config == "otra_busqueda.yaml"


def test_archivo_faltante_da_error_limpio(capsys):
    assert main(["--config", "no_existe.yaml"]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "no_existe.yaml" in err


def test_api_key_faltante_error_limpio_sin_red(tmp_path, capsys, monkeypatch):
    """Sin SERP_API/SEARCH_API_IO -> FlightsAuthError limpia, sin request."""
    monkeypatch.setattr(cli_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SERP_API", raising=False)
    monkeypatch.delenv("SEARCH_API_IO", raising=False)
    cfg = _write_config(tmp_path)
    rc = main(["--config", str(cfg)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "SERP_API" in err


def test_estimacion_se_imprime_antes_del_primer_request(
    tmp_path, capsys, monkeypatch
):
    """Regla de cuota (§12.4): estimacion visible ANTES de cualquier GET."""
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, provider, api_key, **kwargs):
            self.provider = provider

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search_round_trip(self, *args, **kwargs):
            calls["n"] += 1
            print("--- REQUEST ---")
            return []

        def drill_down(self, *args, **kwargs):
            print("--- DRILL ---")
            return []

    monkeypatch.setattr(cli_mod, "FlightsClient", FakeClient)
    monkeypatch.setattr(cli_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("SERP_API", "fake_key_para_test")
    cfg = _write_config(tmp_path)
    rc = main(["--config", str(cfg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Search combinations: 2" in out
    assert "Maximum API requests:" in out
    assert "Provider: serpapi (SERP_API)" in out
    assert "Search-only operation" in out
    assert calls["n"] == 2  # max_combinations respetado
    assert out.index("Maximum API requests:") < out.index("--- REQUEST ---")


def test_drill_down_off_no_lo_llama(tmp_path, capsys, monkeypatch):
    """search.drill_down: off -> ni con ofertas se invoca drill_down."""
    fixture = (
        cli_mod.Path(__file__).parent / "fixtures" / "serpapi_response.json"
    )
    import json

    payload = json.loads(fixture.read_text(encoding="utf-8"))
    raws = payload.get("best_flights", [])

    class FakeClient:
        def __init__(self, provider, api_key, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search_round_trip(self, *args, **kwargs):
            return list(raws)

        def drill_down(self, *args, **kwargs):
            raise AssertionError("drill_down no debe llamarse con drill_down: off")

    monkeypatch.setattr(cli_mod, "FlightsClient", FakeClient)
    monkeypatch.setattr(cli_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("SERP_API", "fake_key_para_test")
    cfg = _write_config(tmp_path)  # drill_down: off en el base
    rc = main(["--config", str(cfg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SOURCE: SerpApi (Google Flights)" in out
    assert "not expanded (cheapest return included in price)" in out
