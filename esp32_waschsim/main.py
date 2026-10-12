"""Orchestrierung der ESP-Waschsim-Firmware."""

try:
    import uasyncio as asyncio
except ImportError:  # pragma: no cover - lokaler CPython-Kompatibilitaetspfad
    import asyncio

from display import DisplayManager
from hardware import EINGANG_ABTASTINTERVALL_MS, HardwareAbstraktion
from network_manager import NETWORK_MODE, NetworkManager
from rest import RestServer
from sensors import NtcSensor, PressureSensor


SYSTEM_TASK_INTERVAL_MS = 200

# Vorbereitete Werte: im Taskfehlerpfad kein format(), str(exc) oder Dict-Aufbau.
ABTASTFEHLER = "ABTASTFEHLER"
ABTAST_SPEICHERFEHLER = "ABTAST_SPEICHERFEHLER"
ABTAST_INVALIDIERUNGSFEHLER = "ABTAST_INVALIDIERUNGSFEHLER"
ABTAST_DIAGNOSEFEHLER = "ABTAST_DIAGNOSEFEHLER"
ABTAST_WARTEFEHLER = "ABTAST_WARTEFEHLER"
ABTASTTASK_BEENDET = "ABTASTTASK_BEENDET"
ABTASTUNG_WIEDERHERGESTELLT = "Digitale Abtastung wiederhergestellt"


class SystemAnwendung:
    """Erzeugt und verbindet die voneinander getrennten Firmware-Schichten."""

    def __init__(self, hardware=None, network_manager=None):
        self.hardware = hardware or HardwareAbstraktion()
        self.ntc_sensor = NtcSensor(hardware=self.hardware)
        self.druck_sensor = PressureSensor(hardware=self.hardware)
        self.display_manager = None
        self.network_manager = network_manager or NetworkManager()
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            pressure_sensor=self.druck_sensor,
            hardware=self.hardware,
            event_callback=self._ui_event,
        )

    def initialisiere_hardware(self):
        self.hardware.initialisiere_hardware()
        self.hardware.setze_sicheren_zustand()
        try:
            display = self.hardware.initialisiere_display()
            if display is not None:
                self.display_manager = DisplayManager(display)
        except Exception as exc:
            self.display_manager = None
            print("Optionales Display nicht verfuegbar: {}".format(exc))

    def _ui_event(self, event_type, payload):
        if self.display_manager is None:
            return
        if event_type == "temperature_updated":
            self.display_manager.ntc_update(payload)
        elif event_type == "pressure_updated":
            self.display_manager.druck_update(payload)
        elif event_type == "status_requested":
            self.display_manager.statusanzeige(payload)

    def _aktualisiere_basisdaten(self):
        if self.display_manager is None:
            return
        status = self.hardware.lese_status()
        heizung = None
        if self.hardware.hat_heizungseingang():
            heizung = status.get("heizung_aktiv")
        friwa = None
        if self.hardware.hat_friwa_eingang():
            friwa = status.get("friwa_aktiv")
        pressure_pa = status.get("pressure_pa", 0.0)
        self.display_manager.aktualisiere_basiswerte(
            status.get("temperature_1_c", 0.0),
            status.get("temperature_2_c", 0.0),
            pressure_pa,
            self.druck_sensor.berechne_druck_mmws(pressure_pa),
            heizung,
            friwa,
        )
        self.display_manager.update()

    async def system_task(self):
        while True:
            try:
                self._aktualisiere_basisdaten()
            except Exception as exc:
                print("Optionaler Display-Systemtask fehlgeschlagen: {}".format(exc))
            if hasattr(asyncio, "sleep_ms"):
                await asyncio.sleep_ms(SYSTEM_TASK_INTERVAL_MS)
            else:
                await asyncio.sleep(SYSTEM_TASK_INTERVAL_MS / 1000.0)

    async def digitale_eingaenge_task(self):
        """Beobachtet Relaiskontakte unabhaengig von Display und HTTP-Anfragen."""
        letzter_fehler = None
        fehlerphase = ABTASTFEHLER
        try:
            while True:
                fehlerphase = ABTASTFEHLER
                try:
                    self.hardware.aktualisiere_digitale_eingaenge()
                except asyncio.CancelledError:
                    raise
                except MemoryError:
                    meldung = ABTAST_SPEICHERFEHLER
                except Exception:
                    meldung = ABTASTFEHLER
                else:
                    meldung = None

                if meldung is not None:
                    # Bestehenden Slot sperren, bevor auch der Fehlerpfad scheitern kann.
                    self.hardware.eingangs_abtastfehler = meldung
                    fehlerphase = ABTAST_INVALIDIERUNGSFEHLER
                    self.hardware.markiere_digitale_eingaenge_unbekannt(meldung)
                    fehlerphase = ABTAST_DIAGNOSEFEHLER
                    if meldung != letzter_fehler:
                        print(meldung)
                elif letzter_fehler is not None:
                    fehlerphase = ABTAST_DIAGNOSEFEHLER
                    print(ABTASTUNG_WIEDERHERGESTELLT)
                letzter_fehler = meldung
                fehlerphase = ABTAST_WARTEFEHLER
                if hasattr(asyncio, "sleep_ms"):
                    await asyncio.sleep_ms(EINGANG_ABTASTINTERVALL_MS)
                else:
                    await asyncio.sleep(EINGANG_ABTASTINTERVALL_MS / 1000.0)
        except asyncio.CancelledError:
            self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
            raise
        except BaseException:
            # Fehler im Fehlerpfad/Warten: gesperrt abbrechen, niemals still fortsetzen.
            self.hardware.eingangs_abtastfehler = fehlerphase
            raise

    async def _display_waehrend_netzwerkstart(self):
        """Laesst Boot-/WLAN-Anzeige laufen, ohne den Netzwerkstart zu blockieren."""
        while self._netzwerk_start_laeuft:
            if self.display_manager is not None:
                self.display_manager.update()
            if hasattr(asyncio, "sleep_ms"):
                await asyncio.sleep_ms(SYSTEM_TASK_INTERVAL_MS)
            else:
                await asyncio.sleep(SYSTEM_TASK_INTERVAL_MS / 1000.0)

    async def starte_system(self):
        # Auch Speicherfehler beim Erzeugen der Coroutine/Task lassen nichts gueltig.
        self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
        tasks = [asyncio.create_task(self.digitale_eingaenge_task())]
        try:
            if self.display_manager is not None and NETWORK_MODE == "auto":
                self.display_manager.wlan_connecting()

            self._netzwerk_start_laeuft = True
            if self.display_manager is not None:
                tasks.append(asyncio.create_task(self._display_waehrend_netzwerkstart()))

            try:
                netzwerk_status = await self.network_manager.starte(NETWORK_MODE)
            finally:
                self._netzwerk_start_laeuft = False
            if not netzwerk_status.get("ok"):
                self.hardware.setze_sicheren_zustand()
                raise RuntimeError("Kein REST-faehiger Netzwerkmodus")

            if self.display_manager is not None:
                self.display_manager.netzwerk_bereit(
                    netzwerk_status.get("mode") == "access_point"
                )

            tasks.append(asyncio.create_task(self.system_task()))
            await self.rest_server._starte_server_async()
        finally:
            # Gilt auch, wenn eine Task vor ihrer ersten Ausfuehrung abgebrochen wird.
            if self.hardware.eingangs_abtastfehler is None:
                self.hardware.eingangs_abtastfehler = ABTASTTASK_BEENDET
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def _main_async():
    anwendung = SystemAnwendung()
    anwendung.initialisiere_hardware()
    await anwendung.starte_system()


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
