"""Zeit-, Hardware- und HTTP-Pruefungen der drei entprellten Relaiskontakte."""

import asyncio
import json
import sys
import types

import pytest

import hardware as hardware_modul
from hardware import EingangsEntprellung, HardwareAbstraktion, _RealBackend
from rest import RestServer
from sensors import NtcSensor, PressureSensor


EINGAENGE = [
    ("heizung", 27, "ist_heizung_aktiv", "hat_heizungseingang", "HEIZUNG_GPIO"),
    ("friwa", 26, "ist_friwa_aktiv", "hat_friwa_eingang", "FRIWA_GPIO"),
    ("abwasserpumpe", 33, "ist_abwasserpumpe_aktiv", "hat_abwasserpumpeneingang",
     "ABWASSERPUMPE_GPIO"),
]


class FakeTicks:
    """Kleine Tickperiode macht echte ticks_diff-Ueberlaeufe reproduzierbar."""

    PERIODE = 1024

    def __init__(self):
        self.zeit_ms = 0

    def ticks_ms(self):
        return self.zeit_ms % self.PERIODE

    def ticks_diff(self, neuer, aelter):
        halbe_periode = self.PERIODE // 2
        return (neuer - aelter + halbe_periode) % self.PERIODE - halbe_periode


@pytest.fixture
def uhr(monkeypatch):
    uhr = FakeTicks()
    monkeypatch.setattr(hardware_modul, "ticks_ms", uhr.ticks_ms)
    monkeypatch.setattr(hardware_modul, "ticks_diff", uhr.ticks_diff)
    return uhr


@pytest.fixture
def aufbau(monkeypatch, tmp_path, uhr):
    class FakePin:
        IN, OUT, PULL_UP = 0, 1, 2
        werte = {}
        initialisierungsfehler = set()
        lesefehler = set()
        lesungen = []

        def __init__(self, gpio, mode=None, pull=None):
            self.gpio = gpio
            if gpio in self.initialisierungsfehler:
                raise OSError("Pin nicht initialisierbar")

        def value(self, wert=None):
            if wert is not None:
                self.werte[self.gpio] = wert
                return
            self.lesungen.append(self.gpio)
            if self.gpio in self.lesefehler:
                raise OSError("Pin nicht lesbar")
            return self.werte.get(self.gpio, 1)

    machine = types.SimpleNamespace(
        Pin=FakePin,
        SPI=lambda *args, **kwargs: types.SimpleNamespace(write=lambda daten: None),
        PWM=lambda pin: types.SimpleNamespace(freq=lambda wert: None,
                                             duty_u16=lambda wert: None),
    )
    monkeypatch.setitem(sys.modules, "machine", machine)
    monkeypatch.chdir(tmp_path)
    return FakePin, uhr


def abtasten(hardware, uhr, von_ms, bis_ms):
    for zeit_ms in range(von_ms, bis_ms + 1, 20):
        uhr.zeit_ms = zeit_ms
        hardware.aktualisiere_digitale_eingaenge()


@pytest.mark.parametrize("aktiv", [False, True])
def test_dauerzustand_erst_nach_200_ms_gueltig(uhr, aktiv):
    entprellung = EingangsEntprellung()
    for zeit_ms in range(0, 200, 20):
        assert entprellung.aktualisiere(aktiv, zeit_ms) is None
    assert entprellung.aktualisiere(aktiv, 199) is None
    assert entprellung.aktualisiere(aktiv, 200) is aktiv
    assert entprellung.aktualisiere(aktiv, 220) is aktiv


@pytest.mark.parametrize("eingang", EINGAENGE)
@pytest.mark.parametrize("anfangs_aktiv", [False, True])
def test_100_ms_impuls_auf_beiden_flanken_ignoriert(aufbau, eingang, anfangs_aktiv):
    pin, uhr = aufbau
    _, gpio, methode, _, _ = eingang
    pin.werte[gpio] = 0 if anfangs_aktiv else 1
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    assert getattr(hardware, methode)() is anfangs_aktiv
    pin.werte[gpio] = 1 if anfangs_aktiv else 0
    abtasten(hardware, uhr, 220, 300)
    assert getattr(hardware, methode)() is anfangs_aktiv
    pin.werte[gpio] = 0 if anfangs_aktiv else 1  # Impulsende nach genau 100 ms.
    abtasten(hardware, uhr, 320, 520)
    assert getattr(hardware, methode)() is anfangs_aktiv


@pytest.mark.parametrize("eingang", EINGAENGE)
@pytest.mark.parametrize("anfangs_aktiv", [False, True])
def test_beide_flanken_ab_exakt_200_ms_uebernommen(aufbau, eingang, anfangs_aktiv):
    pin, uhr = aufbau
    name, gpio, methode, _, _ = eingang
    pin.werte[gpio] = 0 if anfangs_aktiv else 1
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    pin.werte[gpio] = 1 if anfangs_aktiv else 0
    abtasten(hardware, uhr, 220, 400)
    uhr.zeit_ms = 419
    hardware.aktualisiere_digitale_eingaenge()
    assert getattr(hardware, methode)() is anfangs_aktiv
    uhr.zeit_ms = 420
    hardware.aktualisiere_digitale_eingaenge()
    assert getattr(hardware, methode)() is (not anfangs_aktiv)
    assert hardware.lese_status()[name + "_aktiv"] is (not anfangs_aktiv)


def test_wiederholtes_prellen_startet_stabilitaetsfenster_neu(uhr):
    entprellung = EingangsEntprellung()
    for zeit_ms in range(0, 201, 20):
        entprellung.aktualisiere(False, zeit_ms)
    # Mehr als 200 ms seit dem ersten EIN reicht bei wiederholtem Wechsel nicht.
    for zeit_ms in range(220, 521, 20):
        rohzustand = ((zeit_ms - 220) // 80) % 2 == 0
        assert entprellung.aktualisiere(rohzustand, zeit_ms) is False
    for zeit_ms in range(540, 740, 20):
        assert entprellung.aktualisiere(True, zeit_ms) is False
    assert entprellung.aktualisiere(True, 739) is False
    assert entprellung.aktualisiere(True, 740) is True


def test_drei_kontakte_haben_unabhaengige_zeitfenster(aufbau):
    pin, uhr = aufbau
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    for zeit_ms in range(220, 541, 20):
        if zeit_ms == 220:
            pin.werte[27] = 0
        if zeit_ms == 280:
            pin.werte[26] = 0
        if zeit_ms == 340:
            pin.werte[33] = 0
        uhr.zeit_ms = zeit_ms
        hardware.aktualisiere_digitale_eingaenge()
        assert hardware.ist_heizung_aktiv() is (zeit_ms >= 420)
        assert hardware.ist_friwa_aktiv() is (zeit_ms >= 480)
        assert hardware.ist_abwasserpumpe_aktiv() is (zeit_ms >= 540)


@pytest.mark.parametrize("aktiv", [False, True])
def test_ticks_ueberlauf_waehrend_stabilisierung(uhr, aktiv):
    entprellung = EingangsEntprellung()
    for zeit_ms in range(660, 861, 20):
        entprellung.aktualisiere(not aktiv, zeit_ms)
    for zeit_ms in range(900, 1100, 20):
        assert entprellung.aktualisiere(aktiv, zeit_ms % uhr.PERIODE) is (not aktiv)
    assert entprellung.aktualisiere(aktiv, 1099 % uhr.PERIODE) is (not aktiv)
    assert entprellung.aktualisiere(aktiv, 1100 % uhr.PERIODE) is aktiv


@pytest.mark.parametrize("aktiv", [False, True])
@pytest.mark.parametrize("verzoegerung_ms", [41, 199, 200, 300])
def test_verzoegerte_abtastung_setzt_zeitfenster_nicht_zurueck(
        uhr, aktiv, verzoegerung_ms):
    entprellung = EingangsEntprellung()
    assert entprellung.aktualisiere(aktiv, 0) is None
    erwartet = aktiv if verzoegerung_ms >= 200 else None
    assert entprellung.aktualisiere(aktiv, verzoegerung_ms) is erwartet
    assert entprellung.aktualisiere(aktiv, max(200, verzoegerung_ms)) is aktiv


@pytest.mark.parametrize("eingang", EINGAENGE)
@pytest.mark.parametrize("anfangs_aktiv", [False, True])
def test_verzoegerung_verwirft_keinen_laufenden_flankenwechsel(
        aufbau, eingang, anfangs_aktiv):
    pin, uhr = aufbau
    _, gpio, methode, _, _ = eingang
    pin.werte[gpio] = 0 if anfangs_aktiv else 1
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    pin.werte[gpio] = 1 if anfangs_aktiv else 0
    abtasten(hardware, uhr, 220, 320)
    assert getattr(hardware, methode)() is anfangs_aktiv
    # 120 ms Task-Verzoegerung: derselbe Rohpegel bestaetigt die Flanke.
    abtasten(hardware, uhr, 440, 440)
    assert getattr(hardware, methode)() is (not anfangs_aktiv)


@pytest.mark.parametrize("aktiv", [False, True])
def test_erkannter_rohsignalwechsel_nach_verzoegerung_startet_zeitfenster_neu(
        uhr, aktiv):
    entprellung = EingangsEntprellung()
    for zeit_ms in range(0, 201, 20):
        entprellung.aktualisiere(not aktiv, zeit_ms)
    assert entprellung.aktualisiere(aktiv, 220) is (not aktiv)
    assert entprellung.aktualisiere(not aktiv, 440) is (not aktiv)
    # Wieder EIN/AUS erkannt: die Wartezeit zaehlt jetzt ab 460, nicht ab 220.
    assert entprellung.aktualisiere(aktiv, 460) is (not aktiv)
    assert entprellung.aktualisiere(aktiv, 659) is (not aktiv)
    assert entprellung.aktualisiere(aktiv, 660) is aktiv


@pytest.mark.parametrize("aktiv", [False, True])
def test_verzoegerte_abtastung_ueber_ticks_ueberlauf(uhr, aktiv):
    entprellung = EingangsEntprellung()
    assert entprellung.aktualisiere(aktiv, 900) is None
    assert entprellung.aktualisiere(aktiv, 1160 % uhr.PERIODE) is aktiv


@pytest.mark.parametrize("eingang", EINGAENGE)
@pytest.mark.parametrize("fehlerart", ["initialisierung", "deaktiviert"])
def test_fehlender_pin_ist_unbekannt_und_hat_diagnose(aufbau, monkeypatch,
                                                    eingang, fehlerart):
    pin, uhr = aufbau
    name, gpio, methode, vorhanden, konstante = eingang
    if fehlerart == "initialisierung":
        pin.initialisierungsfehler.add(gpio)
    else:
        monkeypatch.setattr(_RealBackend, konstante, None)
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    assert getattr(hardware, vorhanden)() is False
    assert getattr(hardware, methode)() is None
    status = hardware.lese_status()
    assert status[name + "_aktiv"] is None
    assert name in status["eingangs_fehler"]
    for anderer_name, _, andere_methode, _, _ in EINGAENGE:
        if anderer_name != name:
            assert getattr(hardware, andere_methode)() is False


@pytest.mark.parametrize("eingang", EINGAENGE)
@pytest.mark.parametrize("fehlerwert", ["exception", None, 2])
def test_lesefehler_verwirft_zustand_und_erholung_braucht_200_ms(aufbau,
                                                              eingang, fehlerwert):
    pin, uhr = aufbau
    name, gpio, methode, _, _ = eingang
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    if fehlerwert == "exception":
        pin.lesefehler.add(gpio)
    else:
        pin.werte[gpio] = fehlerwert
    abtasten(hardware, uhr, 220, 220)
    assert getattr(hardware, methode)() is None
    assert name in hardware.lese_status()["eingangs_fehler"]
    pin.lesefehler.clear()
    pin.werte[gpio] = 0
    abtasten(hardware, uhr, 240, 420)
    assert getattr(hardware, methode)() is None
    abtasten(hardware, uhr, 440, 440)
    assert getattr(hardware, methode)() is True
    assert name not in hardware.lese_status()["eingangs_fehler"]


def test_status_und_getter_lesen_keine_pins_und_sampling_schreibt_keinen_flash(
        aufbau, tmp_path):
    pin, uhr = aufbau
    hardware = HardwareAbstraktion()
    abtasten(hardware, uhr, 0, 200)
    assert all(pin.lesungen.count(gpio) == 11 for _, gpio, _, _, _ in EINGAENGE)
    pin.lesungen.clear()
    for _, _, methode, _, _ in EINGAENGE:
        assert getattr(hardware, methode)() is False
    status = hardware.lese_status()
    status["eingangs_fehler"]["fremd"] = "keine interne Mutation"
    assert hardware.lese_status()["eingangs_fehler"] == {}
    assert pin.lesungen == []
    assert not (tmp_path / "config.json").exists()


def test_http_status_enthaelt_stabile_pumpe_und_sichtbare_eingangsfehler(aufbau):
    pin, uhr = aufbau
    hardware = HardwareAbstraktion()
    pin.werte[33] = 0
    abtasten(hardware, uhr, 0, 200)
    pin.lesefehler.add(26)
    abtasten(hardware, uhr, 220, 220)
    rest = RestServer(NtcSensor(hardware), PressureSensor(hardware), hardware)

    async def request():
        server = await asyncio.start_server(rest._behandle_client, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(b"GET /api/v1/status HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                return await asyncio.wait_for(reader.read(), timeout=2)
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()

    antwort = asyncio.run(request())
    headers, body = antwort.split(b"\r\n\r\n", 1)
    assert headers.startswith(b"HTTP/1.1 200")
    status = json.loads(body)["hardware"]
    assert status["abwasserpumpe_aktiv"] is True
    assert status["heizung_aktiv"] is False
    assert status["friwa_aktiv"] is None  # JSON null, kein gueltiger AUS-Zustand.
    assert "friwa" in status["eingangs_fehler"]
