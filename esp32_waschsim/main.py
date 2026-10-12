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
        while True:
            try:
                self.hardware.aktualisiere_digitale_eingaenge()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                meldung = "Digitale Abtastung fehlgeschlagen: {}: {}".format(
                    type(exc).__name__, exc
                )
                self.hardware.markiere_digitale_eingaenge_unbekannt(meldung)
                if meldung != letzter_fehler:
                    print(meldung)
                letzter_fehler = meldung
            else:
                if letzter_fehler is not None:
                    print("Digitale Abtastung wiederhergestellt")
                letzter_fehler = None
            if hasattr(asyncio, "sleep_ms"):
                await asyncio.sleep_ms(EINGANG_ABTASTINTERVALL_MS)
            else:
                await asyncio.sleep(EINGANG_ABTASTINTERVALL_MS / 1000.0)

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
