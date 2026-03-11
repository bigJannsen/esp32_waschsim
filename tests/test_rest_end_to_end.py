"""Lokale End-to-End-Tests fuer die REST-Schicht mit Mock-Hardware."""

import asyncio
import json

from mock_hardware import MockHardware
from rest import RestServer
from sensors import NtcSensor, PressureSensor


def _baue_rest_server():
    hardware = MockHardware()
    ntc_sensor = NtcSensor(hardware)
    pressure_sensor = PressureSensor(hardware)
    return RestServer(ntc_sensor, pressure_sensor, hardware), hardware


def _http_anfrage_bytes(methode, pfad, payload=None):
    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    headers = [
        f"{methode} {pfad} HTTP/1.1",
        "Host: localhost",
        f"Content-Length: {len(body)}",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("utf-8") + body


async def _sende_anfrage(rest_server, methode, pfad, payload=None):
    reader = asyncio.StreamReader()
    reader.feed_data(_http_anfrage_bytes(methode, pfad, payload))
    reader.feed_eof()
    return await rest_server._verarbeite_http_anfrage(reader)


def test_rest_health_route():
    rest_server, _ = _baue_rest_server()

    status_code, payload = asyncio.run(_sende_anfrage(rest_server, "GET", "/api/v1/health"))

    assert status_code == 200
    assert isinstance(payload, dict)
    assert payload["ok"] is True


def test_rest_status_route():
    rest_server, _ = _baue_rest_server()

    status_code, payload = asyncio.run(_sende_anfrage(rest_server, "GET", "/api/v1/status"))

    assert status_code == 200
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "backend" in payload


def test_rest_temperature_route_schreibt_beide_mock_digipots():
    rest_server, hardware = _baue_rest_server()

    status_code, payload = asyncio.run(
        _sende_anfrage(
            rest_server,
            "PUT",
            "/api/v1/sensors/temperature",
            {"channel": 1, "temperature_c": 25.0},
        )
    )

    assert status_code == 200
    assert payload["ok"] is True
    assert isinstance(payload["ntc_code"], int)
    assert hardware.letzter_ntc_code_kanal_1 == payload["ntc_code"]
    assert hardware.letzter_ntc_code_kanal_2 == payload["ntc_code"]
    assert hardware.letzter_ntc_code_kanal_1 == hardware.letzter_ntc_code_kanal_2


def test_rest_pressure_route_schreibt_pwm_in_mock():
    rest_server, hardware = _baue_rest_server()

    status_code, payload = asyncio.run(
        _sende_anfrage(
            rest_server,
            "PUT",
            "/api/v1/sensors/pressure",
            {"pressure_pa": 1200.0},
        )
    )

    assert status_code == 200
    assert payload["ok"] is True
    assert isinstance(payload["pwm_duty"], float)
    assert hardware.letztes_pwm_duty == payload["pwm_duty"]


def test_rest_temperature_route_ungueltiger_typ():
    rest_server, _ = _baue_rest_server()

    status_code, payload = asyncio.run(
        _sende_anfrage(
            rest_server,
            "PUT",
            "/api/v1/sensors/temperature",
            {"channel": 1, "temperature_c": "25.0"},
        )
    )

    assert status_code == 400
    assert payload["ok"] is False


def test_rest_pressure_route_ungueltiger_bereich():
    rest_server, _ = _baue_rest_server()

    status_code, payload = asyncio.run(
        _sende_anfrage(
            rest_server,
            "PUT",
            "/api/v1/sensors/pressure",
            {"pressure_pa": 2453.0},
        )
    )

    assert status_code == 400
    assert payload["ok"] is False


def test_rest_status_nach_temperatur_setzen():
    rest_server, _ = _baue_rest_server()

    asyncio.run(
        _sende_anfrage(
            rest_server,
            "PUT",
            "/api/v1/sensors/temperature",
            {"channel": 1, "temperature_c": 25.0},
        )
    )
    status_code, payload = asyncio.run(_sende_anfrage(rest_server, "GET", "/api/v1/status"))

    assert status_code == 200
    assert payload["ok"] is True
    assert payload["channel"] == 1
    assert payload["temperature_c"] == 25.0
    assert isinstance(payload["ntc_code"], int)
