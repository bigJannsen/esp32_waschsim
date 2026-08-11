"""Orchestrierung der ESP-Waschsim-Firmware."""

try:
    import uasyncio as asyncio
except ImportError:  # pragma: no cover - lokaler CPython-Kompatibilitaetspfad
    import asyncio

from display import DisplayManager
from hardware import HardwareAbstraktion
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
            heizung = self.hardware.ist_heizung_aktiv()
        pressure_pa = status.get("pressure_pa", 0.0)
        self.display_manager.aktualisiere_basiswerte(
            status.get("temperature_1_c", 0.0),
            status.get("temperature_2_c", 0.0),
            pressure_pa,
            self.druck_sensor.berechne_druck_mmws(pressure_pa),
            heizung,
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
        if self.display_manager is not None and NETWORK_MODE == "auto":
            self.display_manager.wlan_connecting()

        self._netzwerk_start_laeuft = True
        if self.display_manager is not None:
            asyncio.create_task(self._display_waehrend_netzwerkstart())

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

        asyncio.create_task(self.system_task())
        await self.rest_server._starte_server_async()


async def _main_async():
    anwendung = SystemAnwendung()
    anwendung.initialisiere_hardware()
    await anwendung.starte_system()


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
