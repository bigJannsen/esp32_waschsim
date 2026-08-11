import json
import asyncio

from mock_hardware import MockHardware
from rest import RestServer
from sensors import NtcSensor, PressureSensor


def server(callback):
    hardware = MockHardware()
    return RestServer(NtcSensor(hardware), PressureSensor(hardware), hardware,
                      event_callback=callback)


def body(data):
    return json.dumps(data).encode()


def test_erfolgreiche_semantische_events_genau_einmal():
    events = []
    rest = server(lambda kind, payload: events.append((kind, payload)))
    assert rest._route_setze_temperatur(body({"channel": 1, "temperature_c": 25}))[0] == 200
    assert events[0][0] == "temperature_updated"
    assert events[0][1]["temperature_2_c"] == 0.0
    assert rest._route_setze_druck(body({"pressure_pa": 1200}))[0] == 200
    assert rest._route_status()[0] == 200
    assert [event[0] for event in events] == [
        "temperature_updated", "pressure_updated", "status_requested"
    ]
    assert events[1][1]["pressure_mmws"] == rest.pressure_sensor.berechne_druck_mmws(1200)


def test_fehler_und_unbekannte_route_senden_keine_events():
    events = []
    rest = server(lambda *args: events.append(args))
    assert rest._route_setze_temperatur(body({"channel": 3, "temperature_c": 25}))[0] == 400
    async def unknown_request():
        reader = asyncio.StreamReader()
        reader.feed_data(b"GET /api/v1/unbekannt HTTP/1.1\r\n\r\n")
        reader.feed_eof()
        return await rest._verarbeite_http_anfrage(reader)

    assert asyncio.run(unknown_request())[0] == 404
    assert events == []


def test_callback_exception_aendert_rest_erfolg_nicht():
    def broken_callback(*args):
        raise RuntimeError("OLED kaputt")

    rest = server(broken_callback)
    assert rest._route_setze_druck(body({"pressure_pa": 1200}))[0] == 200
