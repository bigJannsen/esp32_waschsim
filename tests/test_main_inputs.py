"""Tests fuer das zentrale, einmalige Polling der digitalen Eingaenge."""

import asyncio
import types

import pytest

import main as main_modul
from main import SystemAnwendung


class _HardwareMitEingaengen:
    def __init__(self):
        self.status_aufrufe = 0

    def lese_status(self):
        self.status_aufrufe += 1
        return {
            "temperature_1_c": 25.0,
            "temperature_2_c": 60.0,
            "pressure_pa": 981.0,
            "heizung_aktiv": True,
            "friwa_aktiv": True,
        }

    def hat_heizungseingang(self):
        return True

    def hat_friwa_eingang(self):
        return True


class _DisplayRecorder:
    def __init__(self):
        self.werte = None
        self.update_aufrufe = 0

    def aktualisiere_basiswerte(self, *werte):
        self.werte = werte

    def update(self):
        self.update_aufrufe += 1


def test_systemaktualisierung_verwendet_gemeinsamen_hardwarestatus():
    hardware = _HardwareMitEingaengen()
    app = SystemAnwendung.__new__(SystemAnwendung)
    app.hardware = hardware
    app.druck_sensor = type(
        "DruckDummy", (), {"berechne_druck_mmws": staticmethod(lambda pa: pa / 9.81)}
    )()
    app.display_manager = _DisplayRecorder()

    app._aktualisiere_basisdaten()

    assert hardware.status_aufrufe == 1
    assert app.display_manager.werte == (25.0, 60.0, 981.0, 100.0, True, True)
    assert app.display_manager.update_aufrufe == 1


@pytest.mark.parametrize("micropython", [False, True])
def test_abtasttask_laeuft_ohne_oled_im_20_ms_takt(monkeypatch, micropython):
    ablauf = []

    async def sleep(dauer):
        ablauf.append(("sleep", dauer))
        await asyncio.sleep(0)

    fake_asyncio = types.SimpleNamespace()
    if micropython:
        fake_asyncio.sleep_ms = sleep
    else:
        fake_asyncio.sleep = sleep
    monkeypatch.setattr(main_modul, "asyncio", fake_asyncio)
    app = SystemAnwendung.__new__(SystemAnwendung)
    app.display_manager = None
    app.hardware = types.SimpleNamespace(
        aktualisiere_digitale_eingaenge=lambda: ablauf.append(("abtasten", None))
    )

    async def pruefen():
        task = asyncio.create_task(app.digitale_eingaenge_task())
        while len(ablauf) < 6:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(pruefen())
    erwartete_dauer = 20 if micropython else 0.02
    assert ablauf == [("abtasten", None), ("sleep", erwartete_dauer)] * 3
    assert main_modul.SYSTEM_TASK_INTERVAL_MS == 200


@pytest.mark.parametrize("ausgang", ["normal", "netzwerkfehler", "restfehler", "abbruch"])
def test_sampling_waehrend_wlanstart_und_aufraeumen_beim_ende(ausgang):
    class PollingHardware(_HardwareMitEingaengen):
        def __init__(self, bereit):
            super().__init__()
            self.bereit = bereit
            self.abtastungen = 0
            self.safe_state_aufrufe = 0

        def aktualisiere_digitale_eingaenge(self):
            self.abtastungen += 1
            if self.abtastungen >= 2:
                self.bereit.set()

        def setze_sicheren_zustand(self):
            self.safe_state_aufrufe += 1

    async def pruefen():
        bereit = asyncio.Event()
        hardware = PollingHardware(bereit)
        server_aufrufe = []

        async def starte_netzwerk(mode):
            # Vor Abschluss der WLAN-Verbindung muessen bereits Samples laufen.
            await asyncio.wait_for(bereit.wait(), timeout=1)
            if ausgang == "abbruch":
                raise asyncio.CancelledError()
            return {"ok": ausgang != "netzwerkfehler", "mode": "access_point"}

        async def starte_rest():
            server_aufrufe.append(hardware.abtastungen)
            await asyncio.sleep(0)
            if ausgang == "restfehler":
                raise OSError("REST nicht verfuegbar")

        app = SystemAnwendung(hardware, types.SimpleNamespace(starte=starte_netzwerk))
        app.rest_server = types.SimpleNamespace(_starte_server_async=starte_rest)
        if ausgang == "netzwerkfehler":
            with pytest.raises(RuntimeError, match="Kein REST-faehiger Netzwerkmodus"):
                await app.starte_system()
        elif ausgang == "restfehler":
            with pytest.raises(OSError, match="REST nicht verfuegbar"):
                await app.starte_system()
        elif ausgang == "abbruch":
            with pytest.raises(asyncio.CancelledError):
                await app.starte_system()
        else:
            await app.starte_system()
        assert hardware.abtastungen >= 2
        assert hardware.safe_state_aufrufe == (1 if ausgang == "netzwerkfehler" else 0)
        assert bool(server_aufrufe) is (ausgang in ("normal", "restfehler"))
        assert app._netzwerk_start_laeuft is False
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(pruefen())
