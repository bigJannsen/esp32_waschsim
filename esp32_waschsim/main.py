import uasyncio as asyncio

from hardware import HardwareAbstraktion
from network_manager import NETWORK_MODE, NetworkManager
from rest import RestServer
from sensors import NtcSensor, PressureSensor


class SystemAnwendung:
    """Verbindet Hardware, WLAN und REST-Server in deterministischer Reihenfolge."""
    
    def __init__(self):
        """Initialisiert alle Schicht-Komponenten fuer den Laufzeitstart"""
        self.hardware = HardwareAbstraktion()
        self.ntc_sensor = NtcSensor(hardware=self.hardware)
        self.druck_sensor = PressureSensor(hardware=self.hardware)
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            pressure_sensor=self.druck_sensor,
            hardware=self.hardware,
        )
        self.network_manager = NetworkManager()

    def initialisiere_hardware(self):
        """Initialisiert die Hardware inkl. sicherem Startzustand und Display."""
        self.hardware.initialisiere_hardware()
        self.hardware.setze_sicheren_zustand()
        self.hardware.initialisiere_display()

    async def starte_system(self):
        """Startet nach erfolgreichem WLAN-Setup den REST-Server asynchron"""
        netzwerk_status = await self.network_manager.starte(NETWORK_MODE)
        if not netzwerk_status.get("ok"):
            self.hardware.setze_sicheren_zustand()
            print("Netzwerkstart fehlgeschlagen: {}".format(netzwerk_status))
            raise RuntimeError("Kein REST-faehiger Netzwerkmodus")
        await self.rest_server._starte_server_async()


async def _main_async():
    """Führt den kompletten Systemstart in der Ereignisschleife aus"""
    anwendung = SystemAnwendung()
    anwendung.initialisiere_hardware()
    await anwendung.starte_system()


def main():
    """Startet die Firmware mit einem asynchronen Event-Loop."""
    asyncio.run(_main_async())


if __name__ == "__main__": # nach Vgl.operator "__main__" -> sonst startet AP nicht 
    main()
