import json

from mock_hardware import MockHardware
from sensors import NtcSensor, PressureSensor
from rest import RestServer


def print_block(title: str, value) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print(value)


def main() -> None:
    # Mock-Hardware statt echter ESP32-Hardware
    hardware = MockHardware()

    # Sensorlogik mit Mock verdrahten
    ntc_sensor = NtcSensor(hardware=hardware)
    pressure_sensor = PressureSensor(hardware=hardware)

    # REST-Server-Logik instanziieren
    rest_server = RestServer(
        ntc_sensor=ntc_sensor,
        pressure_sensor=pressure_sensor,
        hardware=hardware,
    )

    # 1) Health prüfen
    if hasattr(rest_server, "_route_health"):
        status_code, payload = rest_server._route_health()
        print_block("HEALTH", f"HTTP {status_code}\n{json.dumps(payload, indent=2)}")
    else:
        print_block("HEALTH", "_route_health() nicht gefunden")

    # 2) Status vor Änderungen
    if hasattr(rest_server, "_route_status"):
        status_code, payload = rest_server._route_status()
        print_block("STATUS VORHER", f"HTTP {status_code}\n{json.dumps(payload, indent=2)}")
    else:
        print_block("STATUS VORHER", "_route_status() nicht gefunden")

    # 3) Temperatur setzen
    temperatur_request = json.dumps({
        "channel": 1,
        "temperature_c": 25.0,
    }).encode("utf-8")

    if hasattr(rest_server, "_route_setze_temperatur"):
        status_code, payload = rest_server._route_setze_temperatur(temperatur_request)
        print_block(
            "PUT /sensors/temperature",
            f"HTTP {status_code}\n{json.dumps(payload, indent=2)}"
        )
    else:
        print_block("PUT /sensors/temperature", "_route_setze_temperatur() nicht gefunden")

    # Mock-Zustand nach Temperatur prüfen
    print_block(
        "MOCK-STATUS NACH TEMPERATUR",
        json.dumps(hardware.lese_status(), indent=2)
    )

    print_block(
        "DIGIPOT-KANÄLE",
        json.dumps(
            {
                "kanal_1": hardware.letzter_ntc_code_kanal_1,
                "kanal_2": hardware.letzter_ntc_code_kanal_2,
                "gleich": hardware.letzter_ntc_code_kanal_1 == hardware.letzter_ntc_code_kanal_2,
            },
            indent=2
        )
    )

    # 4) Druck setzen
    druck_request = json.dumps({
        "pressure_pa": 1200.0,
    }).encode("utf-8")

    if hasattr(rest_server, "_route_setze_druck"):
        status_code, payload = rest_server._route_setze_druck(druck_request)
        print_block(
            "PUT /sensors/pressure",
            f"HTTP {status_code}\n{json.dumps(payload, indent=2)}"
        )
    else:
        print_block("PUT /sensors/pressure", "_route_setze_druck() nicht gefunden")

    # Mock-Zustand nach Druck prüfen
    print_block(
        "MOCK-STATUS NACH DRUCK",
        json.dumps(hardware.lese_status(), indent=2)
    )

    # 5) Status nach Änderungen
    if hasattr(rest_server, "_route_status"):
        status_code, payload = rest_server._route_status()
        print_block("STATUS NACHHER", f"HTTP {status_code}\n{json.dumps(payload, indent=2)}")

    # 6) Fehlerfall Temperatur
    fehler_request_temp = json.dumps({
        "channel": 1,
        "temperature_c": "abc",
    }).encode("utf-8")

    if hasattr(rest_server, "_route_setze_temperatur"):
        status_code, payload = rest_server._route_setze_temperatur(fehler_request_temp)
        print_block(
            "FEHLERFALL TEMPERATUR",
            f"HTTP {status_code}\n{json.dumps(payload, indent=2)}"
        )

    # 7) Fehlerfall Druck
    fehler_request_druck = json.dumps({
        "pressure_pa": 3000.0,
    }).encode("utf-8")

    if hasattr(rest_server, "_route_setze_druck"):
        status_code, payload = rest_server._route_setze_druck(fehler_request_druck)
        print_block(
            "FEHLERFALL DRUCK",
            f"HTTP {status_code}\n{json.dumps(payload, indent=2)}"
        )


if __name__ == "__main__":
    main()