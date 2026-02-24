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
        self.ntc_sensor = NtcSensor()
        self.druck_sensor = PressureSensor()
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            pressure_sensor=self.druck_sensor,
            output_driver=self.output_treiber,
            hardware=self.hardware,
        )

    def initialisiere_system(self):
        """Initialisiert Hardware und Display ohne WLAN-Konfiguration."""
        self.hardware.initialisiere_hardware()
        self.hardware.initialisiere_display()

    def starte_system(self):
        """Startet den REST-Server."""
        self.rest_server.starte_server()


def main():
    """Startet die Firmware."""
    anwendung = SystemAnwendung()
    anwendung.initialisiere_system()
    anwendung.starte_system()


if __name__ == "__main__":
    main()
