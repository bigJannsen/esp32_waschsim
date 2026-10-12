"""Fehlersperre, Speicherfehler und Fehler innerhalb des Taskfehlerpfads."""

import asyncio
import json
import types

import pytest

import main as main_modul
from main import SystemAnwendung
from tests.test_digital_inputs import EINGAENGE, abtasten, aufbau, uhr


def anwendung(aufbau):
    pin, clock = aufbau
    from hardware import HardwareAbstraktion

    for _, gpio, _, _, _ in EINGAENGE:
        pin.werte[gpio] = 0
    hardware = HardwareAbstraktion()
    abtasten(hardware, clock, 0, 200)
    assert all(hardware.lese_status()[name + "_aktiv"] is True
               for name, _, _, _, _ in EINGAENGE)
    clock.zeit_ms = 220
    return SystemAnwendung(hardware, types.SimpleNamespace()), clock


def pruefe_gesperrte_rest_antwort(app, code):
    async def request():
        reader = asyncio.StreamReader()
        reader.feed_data(b"GET /api/v1/status HTTP/1.1\r\n\r\n")
        reader.feed_eof()
        status, payload = await app.rest_server._verarbeite_http_anfrage(reader)
        assert status == 200
        return app.rest_server._baue_http_antwort(status, payload)

    antwort = asyncio.run(request())
    daten = json.loads(antwort.split(b"\r\n\r\n", 1)[1])["hardware"]
    for name, _, methode, _, _ in EINGAENGE:
        assert getattr(app.hardware, methode)() is None
        assert daten[name + "_aktiv"] is None
    assert daten["eingangs_fehler"]["abtasttask"] == code


@pytest.mark.parametrize("fehlerklasse", [MemoryError, RuntimeError])
def test_abtastfehler_benutzt_vorbereitete_diagnose_ohne_exception_formatierung(
        aufbau, monkeypatch, fehlerklasse):
    app, _ = anwendung(aufbau)

    class NichtFormatierbarerFehler(fehlerklasse):
        def __str__(self):
            raise AssertionError("Fehlerobjekt darf im Taskpfad nicht formatiert werden")

    fehler = NichtFormatierbarerFehler()
    snapshots = []

    def scheitern():
        raise fehler

    async def sleep_ms(dauer):
        assert dauer == 20
        snapshots.append(app.hardware.lese_status())
        raise asyncio.CancelledError()

    app.hardware.aktualisiere_digitale_eingaenge = scheitern
    monkeypatch.setattr(main_modul, "asyncio", types.SimpleNamespace(
        CancelledError=asyncio.CancelledError, sleep_ms=sleep_ms,
    ))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app.digitale_eingaenge_task())
    code = (main_modul.ABTAST_SPEICHERFEHLER if fehlerklasse is MemoryError
            else main_modul.ABTASTFEHLER)
    assert snapshots[0]["eingangs_fehler"]["abtasttask"] is code
    assert all(snapshots[0][name + "_aktiv"] is None for name, _, _, _, _ in EINGAENGE)


@pytest.mark.parametrize("phase", ["invalidierung", "diagnose", "erholungsdiagnose", "warten"])
@pytest.mark.parametrize("fehlerklasse", [MemoryError, OSError])
def test_fehler_im_fehlerpfad_oder_warten_bricht_sichtbar_und_gesperrt_ab(
        aufbau, monkeypatch, phase, fehlerklasse):
    app, clock = anwendung(aufbau)
    original_abtastung = app.hardware.aktualisiere_digitale_eingaenge
    aufrufe = [0]
    fehler = fehlerklasse("injizierter Fehler")
    code = {
        "invalidierung": main_modul.ABTAST_INVALIDIERUNGSFEHLER,
        "diagnose": main_modul.ABTAST_DIAGNOSEFEHLER,
        "erholungsdiagnose": main_modul.ABTAST_DIAGNOSEFEHLER,
        "warten": main_modul.ABTAST_WARTEFEHLER,
    }[phase]

    def scheitern(*args):
        raise fehler

    def abtastung():
        aufrufe[0] += 1
        if phase != "warten" and aufrufe[0] == 1:
            raise RuntimeError("Abtastaufruf fehlgeschlagen")
        original_abtastung()

    def diagnose(meldung):
        if phase == "diagnose" or meldung == main_modul.ABTASTUNG_WIEDERHERGESTELLT:
            raise fehler

    async def sleep_ms(dauer):
        assert dauer == 20
        if phase == "warten":
            raise fehler
        clock.zeit_ms += 20
        await asyncio.sleep(0)

    with monkeypatch.context() as patch:
        patch.setattr(app.hardware, "aktualisiere_digitale_eingaenge", abtastung)
        if phase == "invalidierung":
            # Reset kann scheitern, bevor irgendein alter Zustand verworfen wurde.
            patch.setattr(app.hardware, "markiere_digitale_eingaenge_unbekannt", scheitern)
        if phase in ("diagnose", "erholungsdiagnose"):
            patch.setattr(main_modul, "print", diagnose, raising=False)
        patch.setattr(main_modul, "asyncio", types.SimpleNamespace(
            CancelledError=asyncio.CancelledError, sleep_ms=sleep_ms,
        ))
        with pytest.raises(fehlerklasse) as raised:
            asyncio.run(app.digitale_eingaenge_task())
        assert raised.value is fehler  # Kein stilles Verschlucken des Folgefehlers.
        pruefe_gesperrte_rest_antwort(app, code)
    # Kontrollierte Wiederherstellung: Sperre erst nach Reset loesen, volle 200 ms.
    start_ms = clock.zeit_ms + 20
    abtasten(app.hardware, clock, start_ms, start_ms + 180)
    assert all(app.hardware.lese_status()[name + "_aktiv"] is None
               for name, _, _, _, _ in EINGAENGE)
    abtasten(app.hardware, clock, start_ms + 200, start_ms + 200)
    assert all(app.hardware.lese_status()[name + "_aktiv"] is True
               for name, _, _, _, _ in EINGAENGE)


@pytest.mark.parametrize("gpio", [27, 26, 33])
def test_memory_error_beim_gpio_lesen_sperrt_alle_eingaenge(aufbau, monkeypatch, gpio):
    app, _ = anwendung(aufbau)
    pin, _ = aufbau
    original_value = pin.value
    snapshots = []

    def value(self, wert=None):
        if self.gpio == gpio and wert is None:
            raise MemoryError()
        return original_value(self, wert)

    async def sleep_ms(dauer):
        snapshots.append(app.hardware.lese_status())
        raise asyncio.CancelledError()

    monkeypatch.setattr(pin, "value", value)
    monkeypatch.setattr(main_modul, "asyncio", types.SimpleNamespace(
        CancelledError=asyncio.CancelledError, sleep_ms=sleep_ms,
    ))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app.digitale_eingaenge_task())
    assert snapshots[0]["eingangs_fehler"]["abtasttask"] == main_modul.ABTAST_SPEICHERFEHLER
    assert all(snapshots[0][name + "_aktiv"] is None for name, _, _, _, _ in EINGAENGE)


def test_teilweise_invalidierung_kann_keinen_alten_zustand_freigeben(aufbau, monkeypatch):
    app, _ = anwendung(aufbau)
    entprellungen = app.hardware._backend._entprellte_eingaenge

    def teilweise():
        entprellungen[0].zuruecksetzen()
        raise MemoryError()

    monkeypatch.setattr(app.hardware._backend, "markiere_digitale_eingaenge_unbekannt", teilweise)
    with pytest.raises(MemoryError):
        app.hardware.markiere_digitale_eingaenge_unbekannt(main_modul.ABTAST_SPEICHERFEHLER)
    assert entprellungen[1].zustand is True  # Noch vorhandene Cachewerte bleiben maskiert.
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTAST_SPEICHERFEHLER)
    with pytest.raises(MemoryError):
        app.hardware.aktualisiere_digitale_eingaenge()
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTAST_SPEICHERFEHLER)


def test_task_abbruch_sperrt_zuvor_bestaetigte_zustaende(aufbau, monkeypatch):
    app, _ = anwendung(aufbau)

    async def sleep_ms(dauer):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main_modul, "asyncio", types.SimpleNamespace(
        CancelledError=asyncio.CancelledError, sleep_ms=sleep_ms,
    ))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(app.digitale_eingaenge_task())
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTASTTASK_BEENDET)


def test_unerwartete_base_exception_wird_weitergereicht_und_sperrt(aufbau, monkeypatch):
    app, _ = anwendung(aufbau)

    class FatalerAbbruch(BaseException):
        pass

    def scheitern():
        raise FatalerAbbruch()

    monkeypatch.setattr(app.hardware, "aktualisiere_digitale_eingaenge", scheitern)
    with pytest.raises(FatalerAbbruch):
        asyncio.run(app.digitale_eingaenge_task())
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTASTFEHLER)


def test_speicherfehler_beim_rest_diagnoseaufbau_meldet_keine_gueltigen_eingaenge(
        aufbau, monkeypatch):
    app, _ = anwendung(aufbau)
    app.hardware.markiere_digitale_eingaenge_unbekannt(main_modul.ABTAST_SPEICHERFEHLER)

    def scheitern():
        raise MemoryError()

    monkeypatch.setattr(app.hardware._backend, "lese_eingangs_fehler", scheitern)

    class Writer:
        def write(self, daten):
            self.daten = daten

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    writer = Writer()

    async def request():
        reader = asyncio.StreamReader()
        reader.feed_data(b"GET /api/v1/status HTTP/1.1\r\n\r\n")
        reader.feed_eof()
        await app.rest_server._behandle_client(reader, writer)

    asyncio.run(request())
    assert writer.daten.startswith(b"HTTP/1.1 500")
    daten = json.loads(writer.daten.split(b"\r\n\r\n", 1)[1])
    assert daten["ok"] is False
    assert daten["error"]["code"] == "INTERNAL_ERROR"
    assert all(getattr(app.hardware, methode)() is None for _, _, methode, _, _ in EINGAENGE)


def test_shutdown_vor_erster_taskausfuehrung_sperrt_eingaenge(aufbau, monkeypatch):
    app, _ = anwendung(aufbau)

    async def netzwerk(mode):
        return {"ok": True, "mode": "access_point"}

    async def rest():
        return  # Kein Yield: die Hintergrundtasks wurden noch nicht ausgefuehrt.

    def abtastung():
        pytest.fail("Abtasttask darf in diesem Ablauf noch nicht laufen")

    app.network_manager = types.SimpleNamespace(starte=netzwerk)
    monkeypatch.setattr(app.rest_server, "_starte_server_async", rest)
    monkeypatch.setattr(app.hardware, "aktualisiere_digitale_eingaenge", abtastung)
    asyncio.run(app.starte_system())
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTASTTASK_BEENDET)


def test_speicherfehler_beim_erzeugen_der_task_laesst_eingaenge_gesperrt(
        aufbau, monkeypatch):
    app, _ = anwendung(aufbau)

    def create_task(coroutine):
        coroutine.close()
        raise MemoryError()

    monkeypatch.setattr(main_modul, "asyncio", types.SimpleNamespace(create_task=create_task))
    with pytest.raises(MemoryError):
        asyncio.run(app.starte_system())
    pruefe_gesperrte_rest_antwort(app, main_modul.ABTASTTASK_BEENDET)


def test_lange_polling_blockade_beweist_keine_physische_stabilitaet(aufbau):
    app, clock = anwendung(aufbau)
    pin, _ = aufbau
    # Pumpe zuletzt EIN; bei 220 wird AUS erstmals beobachtet.
    pin.werte[33] = 1
    app.hardware.aktualisiere_digitale_eingaenge()
    # Nicht abgetastetes EIN/AUS innerhalb einer 300-ms-Blockade bleibt unsichtbar.
    pin.werte[33] = 0
    clock.zeit_ms = 420
    pin.werte[33] = 1
    clock.zeit_ms = 520
    app.hardware.aktualisiere_digitale_eingaenge()
    assert app.hardware.ist_abwasserpumpe_aktiv() is False
    assert app.hardware.lese_status()["eingangs_fehler"] == {}
    # Das ist die gewuenschte Beobachtungslogik, kein Stabilitaetsnachweis fuer GND.
