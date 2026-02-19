"""Einstiegspunkt der ESP32-Firmware.

Dieses Modul enthält ausschließlich die Systemverdrahtung der Schichten:
REST -> Sensorlogik -> OutputDriver -> HardwareAbstraktion.
"""

from hardware import HardwareAbstraktion
from output_driver import OutputDriver
from rest import RestServer
from sensors import DruckSensorPwm, NtcSensor


class SystemAnwendung:
    """Koordiniert die Initialisierung aller Firmware-Komponenten.

    Hinweis:
    - Keine fachlichen Berechnungen in dieser Klasse.
    - Keine direkten GPIO/PWM-Zugriffe in dieser Klasse.
    """

    def __init__(self):
        """Erzeugt alle Komponenten und verbindet deren Schnittstellen."""
        self.hardware_abstraktion = HardwareAbstraktion()
        self.output_treiber = OutputDriver(self.hardware_abstraktion)
        self.ntc_sensor = NtcSensor(self.output_treiber)
        self.druck_sensor_pwm = DruckSensorPwm(self.output_treiber)
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            druck_sensor_pwm=self.druck_sensor_pwm,
        )

    def initialisiere_system(self):
        """Führt die vorbereitende Initialisierung des Gesamtsystems aus."""
        self.hardware_abstraktion.initialisiere_hardware()
        self.hardware_abstraktion.konfiguriere_wlan_ap(
            ssid="miele",
            passwort="10000000",
        )
        self.hardware_abstraktion.initialisiere_display()

    def starte_system(self):
        """Startet den REST-Betrieb nach abgeschlossener Initialisierung."""
        self.rest_server.starte_server()


def main():
    """Startfunktion für den sequenziellen, single-threaded Ablauf."""
    anwendung = SystemAnwendung()
    anwendung.initialisiere_system()
    anwendung.starte_system()


if __name__ == "__main__":
    main()
