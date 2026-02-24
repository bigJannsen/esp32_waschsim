"""Einstiegspunkt der ESP32-Firmware."""

from hardware import HardwareAbstraktion
from output_driver import OutputDriver
from rest import RestServer
from sensors import NtcSensor, PressureSensor


class SystemAnwendung:
    """Verdrahtet die Firmware-Schichten deterministisch."""

    def __init__(self):
        """Initialisiert Hardware, OutputDriver, Sensoren und REST-Server."""
        self.hardware = HardwareAbstraktion()
        self.output_treiber = OutputDriver(self.hardware)
        self.ntc_sensor = NtcSensor(self.output_treiber)
        self.druck_sensor = PressureSensor(self.output_treiber)
        self.rest_server = RestServer(self.ntc_sensor, self.druck_sensor)

    def initialisiere_system(self):
        """Initialisiert Hardware, AP-WLAN und Display."""
        self.hardware.initialisiere_hardware()
        self.hardware.konfiguriere_wlan_ap(ssid="miele", passwort="10000000")
        self.hardware.initialisiere_display()

    def starte_system(self):
        """Startet den REST-Server."""
        self.rest_server.starte_server()


def main():
    """Startet die Firmware im AP-Betrieb."""
    anwendung = SystemAnwendung()
    anwendung.initialisiere_system()
    anwendung.starte_system()


if __name__ == "__main__":
    main()
