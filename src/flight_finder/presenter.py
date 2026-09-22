"""Presentación de resultados: tabla en terminal + export CSV/HTML (§7, §14).

Única capa que sabe de formato visual. Todo string emitido es ASCII seguro
para consola Windows (Regla de Oro 5.1): `->` en vez de flechas, sin simbolos
fuera de latin-1.

Fase 11 (TECHNICAL_SPEC.md §14): encabezado `SOURCE ... SEARCHED AT` con
honesty note; sin banners TEST/SANDBOX ni `ZZ` (Google Flights no tiene
sandbox); sin `EXPIRATION`/`LIVE-TEST` (no hay `expires_at` ni `live_mode`).
`inbound is None` (drill-down off o pendiente) -> etiqueta honesta
"not expanded (cheapest return included in price)".
"""

from __future__ import annotations

import csv
import html
import urllib.parse
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Union

from rich.console import Console
from rich.table import Table

from flight_finder.models import Offer, Segment, Slice

PathLike = Union[str, Path]

_NOT_EXPANDED = "not expanded (cheapest return included in price)"

_GF_BASE = "https://www.google.com/travel/flights"


def google_flights_url(
    origin: str,
    destination: str,
    departure: date,
    return_date: date,
) -> str:
    """Deep link a los resultados de Google Flights para un combo.

    Puro, sin red: solo formatea la URL de busqueda (`q=Flights to ...`).
    Abre la busqueda ida+vuelta de esas fechas — NO apunta a un vuelo ni
    precio exactos (Google no lo permite sin su flujo de reserva con POST,
    fuera del alcance SEARCH-ONLY). Todo ASCII (IATA + ISO dates).
    """
    query = (
        f"Flights to {destination} from {origin} "
        f"on {departure.isoformat()} through {return_date.isoformat()}"
    )
    return f"{_GF_BASE}?q={urllib.parse.quote(query, safe='')}"


def make_console(file=None) -> Console:
    return Console(file=file, highlight=False)


def fmt_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def fmt_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def fmt_route(slc: Slice) -> str:
    airports = [slc.segments[0].origin] + [s.destination for s in slc.segments]
    return " -> ".join(airports)


def _airline_label(seg: Segment) -> str:
    """Nombre + codigo IATA derivado (nunca inventado; ver models._airline_code)."""
    if seg.airline and seg.airline_code:
        return f"{seg.airline} ({seg.airline_code})"
    if seg.airline:
        return seg.airline
    if seg.airline_code:
        return seg.airline_code
    return "desconocida"


def airlines(offer: Offer) -> str:
    """Aerolineas unicas (nombre/codigo) de ida y vuelta, en orden de vuelo."""
    labels: list[str] = []
    for slc in (offer.outbound, offer.inbound):
        if slc is None:
            continue
        for seg in slc.segments:
            labels.append(_airline_label(seg))
    seen = list(dict.fromkeys(labels))
    return ", ".join(seen) if seen else "desconocida"


def flight_numbers(slc: Slice) -> str:
    nums = [s.flight_number for s in slc.segments if s.flight_number]
    return " ".join(nums) if nums else "n/a"


def layover_ids(slc: Slice) -> list[str]:
    if slc.layovers:
        return [l.id for l in slc.layovers]
    return slc.stopover_airports


def stopover_label(slc: Slice) -> str:
    stops = slc.stopover_airports
    if not stops:
        return "directo"
    return "+".join(stops) + " (verificada)"


def format_baggage(offer: Offer) -> str:
    if offer.baggage_note is None:
        return "not confirmed by API"
    return offer.baggage_note


def format_carbon(offer: Offer) -> str:
    if offer.carbon_emissions_kg is None:
        return "n/a"
    return f"{offer.carbon_emissions_kg} kg"


def format_airplane(offer: Offer) -> str:
    for slc in (offer.outbound, offer.inbound):
        if slc is None:
            continue
        for seg in slc.segments:
            if seg.airplane:
                return seg.airplane
    return "n/a"


def print_banner(
    console: Console,
    provider: str,
    searched_at: datetime | None = None,
) -> None:
    """Encabezado de fuente (§14.1) — siempre visible, primera linea.

    `provider`: serpapi | searchapi (de config; no depende de que haya
    ofertas, asi funciona tambien con lote vacio).
    """
    name = {
        "serpapi": "SerpApi",
        "searchapi": "SearchApi",
    }.get(provider, provider)
    ts = (searched_at or datetime.now(timezone.utc)).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    console.print(f"SOURCE: {name} (Google Flights)")
    console.print(f"SEARCHED AT: {ts}")
    console.print(
        "NOTE: displayed prices from Google Flights - not bookable offers; "
        "final price and availability may change at booking"
    )


def print_filter_summary(
    console: Console,
    *,
    origin: str,
    destination: str,
    n_combinations: int,
    avoid_countries: list[str],
    avoid_airports: list[str],
    max_stops: int,
) -> None:
    console.print(
        f"Busqueda: {origin} -> {destination} "
        f"({n_combinations} combinaciones de fecha)"
    )
    console.print(
        "Filtros: paises evitados "
        f"[{', '.join(avoid_countries) or 'ninguno'}], aeropuertos evitados "
        f"[{', '.join(avoid_airports) or 'ninguno'}], "
        f"maximo {max_stops} escalas por tramo"
    )


def print_offers(console: Console, offers: list[Offer], top_n: int) -> None:
    table = Table(title=f"Mejores {min(top_n, len(offers))} vuelos")
    table.add_column("#", justify="right")
    table.add_column("Precio")
    table.add_column("Ida")
    table.add_column("Vuelta")
    table.add_column("Aerolineas")
    table.add_column("Escalas")
    table.add_column("Duracion", justify="right")
    table.add_column("Carbon", justify="right")
    for i, offer in enumerate(offers[:top_n], 1):
        out = offer.outbound
        back = offer.inbound
        if back is None:
            back_cell = f"{_NOT_EXPANDED}"
        else:
            back_cell = (
                f"{fmt_datetime(back.segments[0].departure_time)}\n"
                f"{fmt_route(back)}"
            )
        stops_cell = stopover_label(out)
        if back is not None:
            stops_cell += f" / {stopover_label(back)}"
        else:
            stops_cell += " / vuelta no expandida"
        table.add_row(
            str(i),
            f"{offer.price} {offer.currency}",
            f"{fmt_datetime(out.segments[0].departure_time)}\n{fmt_route(out)}",
            back_cell,
            airlines(offer),
            stops_cell,
            fmt_duration(offer.total_duration_minutes),
            format_carbon(offer),
        )
    console.print(table)


def format_offer_card(
    offer: Offer, rank: int, *, return_date: date | None = None
) -> str:
    """Ficha textual por oferta para salida no tabular (§14.2).

    `return_date`: fecha de vuelta del combo (de `combo_of` en el CLI) —
    con ella se agrega la linea `LINK:` (deep link a la busqueda; el
    precio puede variar). Sin ella se omite (comportamiento anterior).
    """
    out = offer.outbound
    back = offer.inbound
    stops_back = (
        str(len(back.stopover_airports)) if back is not None else "n/a"
    )
    layovers_out = "+".join(layover_ids(out)) or "ninguna"
    layovers_back = (
        "+".join(layover_ids(back)) if back is not None else "n/a"
    )
    if back is None:
        return_line = f"RETURN:   {_NOT_EXPANDED}"
        stops_line = (
            f"STOPS: {len(out.stopover_airports)} ida / {stops_back} vuelta"
            f" / LAYOVERS: {layovers_out} ida / n/a vuelta"
            f" / DURATION: {fmt_duration(offer.total_duration_minutes)}"
        )
    else:
        return_line = (
            f"RETURN:   {fmt_route(back)} ("
            f"{fmt_datetime(back.segments[0].departure_time)} -> "
            f"{fmt_datetime(back.segments[-1].arrival_time)}) "
            f"{flight_numbers(back)}"
        )
        stops_line = (
            f"STOPS: {len(out.stopover_airports)} ida / {stops_back} vuelta"
            f" / LAYOVERS: {layovers_out} ida / {layovers_back} vuelta"
            f" / DURATION: {fmt_duration(offer.total_duration_minutes)}"
        )
    lines = [
        f"--- Oferta #{rank}: {offer.id} ---",
        f"PRICE: {offer.price} {offer.currency} (round trip total)",
        f"AIRLINE: {airlines(offer)}",
        f"OUTBOUND: {fmt_route(out)} ("
        f"{fmt_datetime(out.segments[0].departure_time)} -> "
        f"{fmt_datetime(out.segments[-1].arrival_time)}) {flight_numbers(out)}",
        return_line,
        stops_line,
        f"BAGGAGE: {format_baggage(offer)}",
        f"CARBON: {format_carbon(offer)} / AIRPLANE: {format_airplane(offer)}",
    ]
    if return_date is not None:
        link = google_flights_url(
            out.segments[0].origin,
            out.segments[-1].destination,
            out.segments[0].departure_time.date(),
            return_date,
        )
        lines.append(f"LINK: {link} (abre la busqueda; el precio puede variar)")
    lines.append(
        "Para reservar, busca este vuelo manualmente por numero de vuelo y "
        "aerolinea (este buscador no reserva - solo consulta)."
    )
    return "\n".join(lines)


def print_offer_cards(
    console: Console,
    offers: list[Offer],
    top_n: int,
    combo_of: dict[str, tuple[date, date]] | None = None,
) -> None:
    combo_of = combo_of or {}
    for i, offer in enumerate(offers[:top_n], 1):
        entry = combo_of.get(offer.id)
        console.print(
            format_offer_card(
                offer, i, return_date=entry[1] if entry else None
            )
        )
        console.print("")


def print_aggregate_counts(
    console: Console,
    *,
    valid: int,
    filtered_by_country: int,
    filtered_by_airport: int,
    filtered_by_max_stops: int,
    filtered_by_unverified: int,
) -> None:
    console.print(f"VALID OFFERS: {valid}")
    console.print(f"FILTERED BY US: {filtered_by_country}")
    console.print(f"FILTERED BY AIRPORT: {filtered_by_airport}")
    console.print(f"FILTERED BY MAX STOPS: {filtered_by_max_stops}")
    if filtered_by_unverified:
        console.print(f"FILTERED BY UNVERIFIED: {filtered_by_unverified}")


def print_no_results(
    console: Console, total_raw: int, discard_reasons: Counter
) -> None:
    console.print(
        f"Sin resultados validos: {total_raw} ofertas en bruto, "
        f"{sum(discard_reasons.values())} descartadas."
    )
    for reason, count in discard_reasons.most_common():
        console.print(f"  - {count}x: {reason}")


def _first_logo(offer: Offer) -> str:
    for slc in (offer.outbound, offer.inbound):
        if slc is None:
            continue
        for seg in slc.segments:
            if seg.airline_logo:
                return seg.airline_logo
    return ""


def _row(offer: Offer, rank: int) -> dict[str, str]:
    out = offer.outbound
    back = offer.inbound
    if back is None:
        vuelta_salida = "not expanded"
        vuelta_ruta = _NOT_EXPANDED
        escalas_vuelta = "n/a"
    else:
        vuelta_salida = fmt_datetime(back.segments[0].departure_time)
        vuelta_ruta = fmt_route(back)
        escalas_vuelta = stopover_label(back)
    return {
        "puesto": str(rank),
        "precio": str(offer.price),
        "moneda": offer.currency,
        "ida_salida": fmt_datetime(out.segments[0].departure_time),
        "ida_ruta": fmt_route(out),
        "vuelta_salida": vuelta_salida,
        "vuelta_ruta": vuelta_ruta,
        "aerolineas": airlines(offer),
        "escalas_ida": stopover_label(out),
        "escalas_vuelta": escalas_vuelta,
        "duracion_min": str(offer.total_duration_minutes),
        "emissions_kg": (
            str(offer.carbon_emissions_kg)
            if offer.carbon_emissions_kg is not None
            else ""
        ),
        "baggage": format_baggage(offer),
        "airline_logo": _first_logo(offer),
    }


def rows_for_export(offers: list[Offer], top_n: int) -> list[dict[str, str]]:
    """Filas del top N como dicts (columnas estables, ver `_row`).

    Lo usan `export_csv`/`export_html` y la UI web (descarga CSV en
    memoria sin pasar por archivo).
    """
    return [_row(o, i) for i, o in enumerate(offers[:top_n], 1)]


def export_csv(path: PathLike, offers: list[Offer], top_n: int) -> Path:
    path = Path(path)
    rows = rows_for_export(offers, top_n)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_html(path: PathLike, offers: list[Offer], top_n: int) -> Path:
    path = Path(path)
    rows = rows_for_export(offers, top_n)
    if not rows:
        path.write_text(
            "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<title>Vuelos encontrados</title></head><body><p>Sin resultados.</p></body></html>",
            encoding="utf-8",
        )
        return path
    cells = list(rows[0].keys())
    head = "".join(f"<th>{c}</th>" for c in cells)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(r[c])}</td>" for c in cells) + "</tr>"
        for r in rows
    )
    path.write_text(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Vuelos encontrados</title></head><body>"
        f"<table border='1'><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>",
        encoding="utf-8",
    )
    return path
