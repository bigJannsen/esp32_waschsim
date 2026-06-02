"""End-to-End-Integrationstest fuer die REST-API im AP-Betrieb.

Dieser Test prueft deterministisch die oeffentlichen HTTP-Schnittstellen fuer
Health, Temperaturpfad, Druckpfad, Statuskonsistenz sowie einen negativen
Validierungsfall. Der Persistenztest wird als manuell auszufuehrender Schritt
im Ablauf dokumentiert, da dafuer ein Neustart des Zielsystems erforderlich ist.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict

if "pytest" in sys.modules:  # pragma: no cover - verhindert Pytest-Sammlung dieses Skripts.
    import pytest

    pytest.skip("integration_test.py ist ein ausfuehrbares Integrationsskript", allow_module_level=True)

try:
    import requests
except ImportError:  # pragma: no cover - Laufzeit-Hinweis fuer lokale Umgebung.
    requests = None


DEFAULT_BASIS_URL = "http://192.168.4.1:8080/api/v1"
TIMEOUT_S = 5.0


class TestFehler(Exception):
    """Signalisiert einen harten Abbruch des Integrationstests."""


def _assert_bedingung(bedingung: bool, nachricht: str) -> None:
    """Bricht den Testlauf bei verletzter Bedingung mit klarer Meldung ab."""
    if not bedingung:
        raise TestFehler(nachricht)


def _json_antwort(response: requests.Response) -> Dict[str, Any]:
    """Liefert das JSON-Objekt einer HTTP-Antwort oder bricht bei Typfehler ab."""
    try:
        daten = response.json()
    except ValueError as exc:
        raise TestFehler("Antwort ist kein gueltiges JSON") from exc
    _assert_bedingung(isinstance(daten, dict), "Antwort-JSON ist kein Objekt")
    return daten


def _sende_get(basis_url: str, pfad: str) -> requests.Response:
    """Fuehrt einen GET-Request mit festem Timeout aus."""
    return requests.get(basis_url + pfad, timeout=TIMEOUT_S)


def _sende_put(basis_url: str, pfad: str, payload: Dict[str, Any]) -> requests.Response:
    """Fuehrt einen PUT-Request mit JSON-Payload und festem Timeout aus."""
    return requests.put(basis_url + pfad, json=payload, timeout=TIMEOUT_S)


def teste_health(basis_url: str) -> None:
    """TEST 1: Prueft den Health-Endpunkt auf HTTP 200 und ok == true."""
    print("TEST 1: Health pruefen")
    antwort = _sende_get(basis_url, "/health")
    _assert_bedingung(antwort.status_code == 200, "Health-Statuscode ist nicht 200")
    daten = _json_antwort(antwort)
    _assert_bedingung(daten.get("ok") is True, "Health ok ist nicht true")


def teste_temperaturpfad(basis_url: str) -> int:
    """TEST 2: Setzt Temperatur und validiert die End-to-End-Rueckgabe."""
    print("TEST 2: Temperatur setzen")
    payload = {"channel": 1, "temperature_c": 25.0}
    antwort = _sende_put(basis_url, "/sensors/temperature", payload)
    _assert_bedingung(antwort.status_code == 200, "Temperatur-Statuscode ist nicht 200")
    daten = _json_antwort(antwort)
    _assert_bedingung(daten.get("ok") is True, "Temperaturantwort ok ist nicht true")
    _assert_bedingung(daten.get("channel") == 1, "Temperaturantwort channel ist ungueltig")
    _assert_bedingung(daten.get("temperature_c") == 25.0, "Temperaturantwort temperature_c ist ungueltig")
    ntc_code = daten.get("ntc_code")
    _assert_bedingung(isinstance(ntc_code, int), "Temperaturantwort ntc_code ist nicht int")
    return ntc_code


def teste_status_nach_temperatur(basis_url: str, erwarteter_ntc_code: int) -> None:
    """TEST 3: Prueft, ob /status den zuletzt gesetzten Temperaturwert konsistent zeigt."""
    print("TEST 3: Status pruefen")
    antwort = _sende_get(basis_url, "/status")
    _assert_bedingung(antwort.status_code == 200, "Status-Statuscode ist nicht 200")
    daten = _json_antwort(antwort)
    _assert_bedingung(daten.get("ok") is True, "Statusantwort ok ist nicht true")
    _assert_bedingung(daten.get("channel") == 1, "Status channel ist nicht 1")
    _assert_bedingung(daten.get("temperature_c") == 25.0, "Status temperature_c ist nicht 25.0")
    _assert_bedingung(daten.get("ntc_code") == erwarteter_ntc_code, "Status ntc_code weicht ab")


def teste_druckpfad(basis_url: str) -> float:
    """TEST 4: Setzt Druck und validiert den normierten PWM-Duty-Rueckgabewert."""
    print("TEST 4: Druck setzen")
    payload = {"pressure_pa": 1200.0}
    antwort = _sende_put(basis_url, "/sensors/pressure", payload)
    _assert_bedingung(antwort.status_code == 200, "Druck-Statuscode ist nicht 200")
    daten = _json_antwort(antwort)
    _assert_bedingung(daten.get("ok") is True, "Druckantwort ok ist nicht true")
    pwm_duty = daten.get("pwm_duty")
    _assert_bedingung(isinstance(pwm_duty, float), "Druckantwort pwm_duty ist nicht float")
    _assert_bedingung(0.0 <= pwm_duty <= 1.0, "Druckantwort pwm_duty liegt nicht in 0.0..1.0")
    return pwm_duty


def teste_fehlerfall_temperatur(basis_url: str) -> None:
    """TEST 5: Prueft den Validierungsfehler bei ungueltigem Temperaturtyp."""
    print("TEST 5: Fehlerfall testen")
    payload = {"temperature_c": "abc"}
    antwort = _sende_put(basis_url, "/sensors/temperature", payload)
    _assert_bedingung(antwort.status_code == 400, "Fehlerfall-Statuscode ist nicht 400")
    daten = _json_antwort(antwort)
    _assert_bedingung(daten.get("ok") is False, "Fehlerfall ok ist nicht false")


def dokumentiere_persistenztest() -> None:
    """TEST 6: Dokumentiert den manuellen Persistenzablauf mit Neustart."""
    print("TEST 6: Persistenztest (manuell dokumentiert)")
    print("Hinweis: Nach TEST 4 System neu starten, dann /api/v1/status erneut abrufen und letztes_pwm_duty pruefen.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Integrationstest fuer ESP32 Waschsim REST-API")
    parser.add_argument("--basis-url", default=DEFAULT_BASIS_URL, help="Basis-URL inkl. /api/v1")
    return parser.parse_args()


def main() -> int:
    """Fuehrt alle Integrationsschritte in fester Reihenfolge aus."""
    args = _parse_args()
    basis_url = args.basis_url.rstrip("/")

    if requests is None:
        print("TEST FEHLGESCHLAGEN: requests ist nicht installiert. Bitte 'pip install requests' ausfuehren.")
        return 1

    try:
        teste_health(basis_url)
        ntc_code = teste_temperaturpfad(basis_url)
        teste_status_nach_temperatur(basis_url, ntc_code)
        _ = teste_druckpfad(basis_url)
        teste_fehlerfall_temperatur(basis_url)
        dokumentiere_persistenztest()
    except requests.RequestException as exc:
        print("TEST FEHLGESCHLAGEN: Netzwerk-/HTTP-Fehler: {}".format(exc))
        return 1
    except TestFehler as exc:
        print("TEST FEHLGESCHLAGEN: {}".format(exc))
        return 1

    print("ALLE TESTS ERFOLGREICH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
