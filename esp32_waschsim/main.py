"""Einstiegspunkt der ESP32-Firmware mit WLAN-AP- und REST-Orchestrierung."""

import network
import uasyncio as asyncio

from hardware import HardwareAbstraktion
from rest import RestServer
from sensors import NtcSensor, PressureSensor


class SystemAnwendung:
    """Verdrahtet Hardware, WLAN und REST-Server in deterministischer Reihenfolge."""

    AP_SSID = "miele"
    AP_PASSWORT = "10000000"

    def __init__(self):
        """Initialisiert alle Schicht-Komponenten fuer den Laufzeitstart."""
        self.hardware = HardwareAbstraktion()
        self.ntc_sensor = NtcSensor(hardware=self.hardware)
        self.druck_sensor = PressureSensor(hardware=self.hardware)
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            pressure_sensor=self.druck_sensor,
            hardware=self.hardware,
        )
        self.ap_wlan = network.WLAN(network.AP_IF)

    def initialisiere_hardware(self):
        """Initialisiert die Hardware inkl. sicherem Startzustand und Display."""
        self.hardware.initialisiere_hardware()
        self.hardware.setze_sicheren_zustand()
        self.hardware.initialisiere_display()

    def _ermittle_ap_authmode(self):
        """Bestimmt den bestverfuegbaren WPA2-Authmode fuer den AP-Betrieb."""
        if hasattr(network, "AUTH_WPA2_PSK"):
            return network.AUTH_WPA2_PSK
        if hasattr(network, "AUTH_WPA_WPA2_PSK"):
            return network.AUTH_WPA_WPA2_PSK
        return None

    async def starte_wlan_ap(self):
        """Startet den WLAN-Access-Point und liefert die AP-IP zurueck."""
        try:
            self.ap_wlan.active(True)

            authmode = self._ermittle_ap_authmode()
            if authmode is None:
                self.ap_wlan.config(essid=self.AP_SSID, password=self.AP_PASSWORT)
            else:
                self.ap_wlan.config(essid=self.AP_SSID, password=self.AP_PASSWORT, authmode=authmode)

            for _ in range(20):
                if self.ap_wlan.active():
                    break
                await asyncio.sleep_ms(50)

            if not self.ap_wlan.active():
                raise RuntimeError("AP wurde nicht aktiv")

            konfiguration = self.ap_wlan.ifconfig()
            ap_ip = konfiguration[0] if isinstance(konfiguration, tuple) else konfiguration[0]
            print("WLAN AP aktiv auf {}".format(ap_ip)) # läuft! 
            return ap_ip
        except Exception as exc:
            self.hardware.setze_sicheren_zustand()
            raise Exception("WLAN-AP konnte nicht gestartet werden: {}".format(exc))

    async def starte_system(self):
        """Startet nach erfolgreichem WLAN-Setup den REST-Server asynchron."""
        await self.starte_wlan_ap()
        await self.rest_server._starte_server_async()


async def _main_async():
    """Fuehrt den kompletten Systemstart in der Ereignisschleife aus."""
    anwendung = SystemAnwendung()
    anwendung.initialisiere_hardware()
    await anwendung.starte_system()


def main():
    """Startet die Firmware mit einem asynchronen Event-Loop."""
    asyncio.run(_main_async())


if __name__ == "__main__": # __name__ zu __main__ wechseln -> sonst startet AP nicht automatisch
    main()
