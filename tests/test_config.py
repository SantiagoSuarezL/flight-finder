"""Tests de Fase 3: carga y validación de `config.yaml` (spec §3.1)."""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from flight_finder.config import ConfigError, FlightFinderConfig, load_config, main

TODAY = date.today()
FUTURE = (TODAY + timedelta(days=60)).isoformat()
FUTURE2 = (TODAY + timedelta(days=75)).isoformat()
PAST = (TODAY - timedelta(days=1)).isoformat()

EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


def _base_dict(**overrides):
    cfg = {
        "provider": "serpapi",
        "currency": "USD",
        "search": {
            "origin": "BOG",
            "destination": "MAD",
            "passengers": 1,
            "cabin_class": "economy",
            "drill_down": "top_n",
        },
        "departure": {"fixed_date": FUTURE, "before": None},
        "stay": {"min_days": 10, "max_days": 15},
        "avoid": {"countries": ["US"], "airports": ["ATL"]},
        "max_stops": 2,
        "sort": {"primary": "total_price", "secondary": "duration"},
        "output": {"top_n": 10, "export": None},
    }
    for section, values in overrides.items():
        if isinstance(values, dict):
            cfg[section].update(values)
        else:
            cfg[section] = values
    return cfg


def _write(tmp_path, cfg_dict):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")
    return p


def test_config_valida_carga(tmp_path):
    cfg = load_config(_write(tmp_path, _base_dict()))
    assert isinstance(cfg, FlightFinderConfig)
    assert cfg.provider == "serpapi"
    assert cfg.search.origin == "BOG"
    assert cfg.avoid.countries == ["US"]


def test_provider_obligatorio_se_rechaza_si_falta(tmp_path):
    d = _base_dict()
    d.pop("provider")
    with pytest.raises(ConfigError, match="provider"):
        load_config(_write(tmp_path, d))


def test_provider_invalido_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="provider"):
        load_config(_write(tmp_path, _base_dict(provider="duffel")))


def test_provider_searchapi_valido(tmp_path):
    cfg = load_config(_write(tmp_path, _base_dict(provider="searchapi")))
    assert cfg.provider == "searchapi"


def test_currency_por_defecto_es_usd(tmp_path):
    d = _base_dict()
    d.pop("currency")
    cfg = load_config(_write(tmp_path, d))
    assert cfg.currency == "USD"


def test_currency_invalida_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="ISO 4217"):
        load_config(_write(tmp_path, _base_dict(currency="usd")))


def test_drill_down_off_valido(tmp_path):
    cfg = load_config(
        _write(tmp_path, _base_dict(search={"drill_down": "off"}))
    )
    assert cfg.search.drill_down == "off"


def test_drill_down_por_defecto_es_top_n(tmp_path):
    d = _base_dict()
    d["search"].pop("drill_down")
    cfg = load_config(_write(tmp_path, d))
    assert cfg.search.drill_down == "top_n"


def test_drill_down_invalido_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="drill_down"):
        load_config(
            _write(tmp_path, _base_dict(search={"drill_down": "always"}))
        )


def test_max_combinations_menor_que_1_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="max_combinations"):
        load_config(
            _write(tmp_path, _base_dict(search={"max_combinations": 0}))
        )


def test_origen_igual_destino_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="no pueden ser iguales"):
        load_config(_write(tmp_path, _base_dict(search={"destination": "BOG"})))


def test_iata_mal_formado_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="IATA"):
        load_config(_write(tmp_path, _base_dict(search={"origin": "bog"})))


def test_ambas_fechas_presentes_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="exactamente uno"):
        load_config(
            _write(
                tmp_path,
                _base_dict(departure={"fixed_date": FUTURE, "before": FUTURE2}),
            )
        )


def test_ninguna_fecha_presente_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="exactamente uno"):
        load_config(
            _write(tmp_path, _base_dict(departure={"fixed_date": None}))
        )


def test_min_mayor_que_max_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="min_days"):
        load_config(
            _write(tmp_path, _base_dict(stay={"min_days": 15, "max_days": 10}))
        )


def test_dias_no_positivos_se_rechazan(tmp_path):
    with pytest.raises(ConfigError, match="mayores que 0"):
        load_config(
            _write(tmp_path, _base_dict(stay={"min_days": 0, "max_days": 5}))
        )


def test_pais_iso_mal_formado_se_rechaza_con_mensaje_de_formato(tmp_path):
    with pytest.raises(ConfigError, match="alpha-2"):
        load_config(
            _write(tmp_path, _base_dict(avoid={"countries": ["USA"]}))
        )


def test_fecha_pasada_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="ya pasó"):
        load_config(
            _write(tmp_path, _base_dict(departure={"fixed_date": PAST}))
        )


def test_max_stops_negativo_se_rechaza(tmp_path):
    with pytest.raises(ConfigError, match="negativo"):
        load_config(_write(tmp_path, _base_dict(max_stops=-1)))


def test_archivo_faltante_da_error_humano(tmp_path):
    with pytest.raises(ConfigError, match="No se encontró"):
        load_config(tmp_path / "no_existe.yaml")


def test_yaml_mal_formado_da_error_humano(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("search: [desbalanceado\n  foo", encoding="utf-8")
    with pytest.raises(ConfigError, match="no es un YAML válido"):
        load_config(p)


def test_main_con_yaml_invalido_no_lanza_traceback(tmp_path, capsys):
    rc = main([str(_write(tmp_path, _base_dict(max_stops=-1)))])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "max_stops" in err


def test_main_con_yaml_valido(tmp_path, capsys):
    rc = main([str(_write(tmp_path, _base_dict()))])
    assert rc == 0
    assert "BOG->MAD" in capsys.readouterr().out


def test_ejemplo_tiene_estructura_esperada():
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert raw["provider"] == "serpapi"
    assert raw["currency"] == "USD"
    assert raw["search"]["origin"] == "BOG"
    assert raw["search"]["destination"] == "MAD"
    assert raw["search"]["drill_down"] == "top_n"
    assert "mode" not in raw
    assert raw["avoid"]["countries"] == ["US"]
    assert raw["avoid"]["airports"] == ["ATL"]
    assert (raw["stay"]["min_days"], raw["stay"]["max_days"]) == (10, 15)
    assert raw["output"]["top_n"] == 3  # preset óptimo: 6 combos + drill 3


def test_ejemplo_carga_sin_errores():
    cfg = load_config(EXAMPLE)
    assert cfg.provider == "serpapi"
    assert cfg.search.drill_down == "top_n"
