"""Lokale End-to-End-Tests fuer die REST-Schicht mit Mock-Hardware."""
import asyncio
import json
import pytest
from mock_hardware import MockHardware
from rest import RestServer
from sensors import NtcSensor, PressureSensor


def _server():
    hardware = MockHardware()
    return RestServer(NtcSensor(hardware), PressureSensor(hardware), hardware), hardware


def _request_bytes(method, path, payload=None):
    body = b"" if payload is None else json.dumps(payload).encode()
    return (f"{method} {path} HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)


async def _send(server, method, path, payload=None):
    reader = asyncio.StreamReader()
    reader.feed_data(_request_bytes(method, path, payload)); reader.feed_eof()
    return await server._verarbeite_http_anfrage(reader)


def send(server, method, path, payload=None):
    return asyncio.run(_send(server, method, path, payload))


def test_health_und_initialer_status():
    server, _ = _server()
    assert send(server, "GET", "/api/v1/health")[0] == 200
    code, status = send(server, "GET", "/api/v1/status")
    assert code == 200 and status["ok"] is True
    assert status["last_values"]["temperature"]["channels"]["1"]["temperature_c"] == 0.0


def test_temperature_same_aktualisiert_beide():
    server, hardware = _server()
    code, payload = send(server, "PUT", "/api/v1/sensors/temperature", {"mode": "same", "temperature_c": 25})
    assert code == 200 and len(payload["results"]) == 2
    assert hardware.temperature_1_c == hardware.temperature_2_c == 25.0
    assert hardware.letzter_ntc_code_kanal_1 == hardware.letzter_ntc_code_kanal_2


def test_temperature_separate_aktualisiert_getrennt():
    server, hardware = _server()
    code, _ = send(server, "PUT", "/api/v1/sensors/temperature", {"mode": "separate", "temperature_1_c": 25, "temperature_2_c": 60})
    assert code == 200
    assert hardware.temperature_1_c == 25.0 and hardware.temperature_2_c == 60.0
    assert hardware.letzter_ntc_code_kanal_1 != hardware.letzter_ntc_code_kanal_2


@pytest.mark.parametrize("channel", [1, 2])
def test_temperature_single_veraendert_nur_gewaehlten_kanal(channel):
    server, hardware = _server()
    other = 2 if channel == 1 else 1
    old_code = getattr(hardware, f"letzter_ntc_code_kanal_{other}")
    code, _ = send(server, "PUT", "/api/v1/sensors/temperature", {"channel": channel, "temperature_c": 25})
    assert code == 200
    assert getattr(hardware, f"temperature_{channel}_c") == 25.0
    assert getattr(hardware, f"letzter_ntc_code_kanal_{other}") == old_code


def test_pressure_und_status_sind_konsistent():
    server, hardware = _server()
    code, payload = send(server, "PUT", "/api/v1/sensors/pressure", {"pressure_pa": 1200})
    assert code == 200 and payload["pwm_duty"] == hardware.letztes_pwm_duty
    _, status = send(server, "GET", "/api/v1/status")
    assert status["last_values"]["pressure"] == {"pressure_pa": 1200.0, "pwm_duty": payload["pwm_duty"]}


@pytest.mark.parametrize("path,payload", [
    ("/api/v1/sensors/temperature", {"mode": "same", "temperature_c": True}),
    ("/api/v1/sensors/temperature", {"mode": "separate", "temperature_1_c": 25}),
    ("/api/v1/sensors/temperature", {"channel": 3, "temperature_c": 25}),
    ("/api/v1/sensors/pressure", {"pressure_pa": 2453}),
])
def test_fehlerfaelle(path, payload):
    code, response = send(_server()[0], "PUT", path, payload)
    assert code == 400 and response["ok"] is False


def test_unbekannte_route():
    code, response = send(_server()[0], "GET", "/api/v1/unbekannt")
    assert code == 404 and response["error"]["code"] == "NOT_FOUND"
