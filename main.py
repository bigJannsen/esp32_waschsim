"""Einstiegspunkt der ESP32-Firmware.

Dieses Modul enthält ausschließlich die Systemverdrahtung der Schichten:
REST -> Sensorlogik -> OutputDriver -> HardwareAbstraktion.
"""

from hardware import HardwareAbstraktion
from output_driver import OutputDriver
from rest import RestServer
from sensors import DruckSensorPwm, NtcSensor


class NetzwerkManager:
    """Verwaltet den Netzwerkstart für AP-Standard und optionales STA.

    Zweck:
        Kapselt die Auswahl und Initialisierung des WLAN-Betriebsmodus,
        ohne fachliche Sensor- oder REST-Logik zu enthalten.
    """

    def __init__(self, hardware_abstraktion):
        """Initialisiert den Manager mit Hardwarezugriff.

        Parameter:
            hardware_abstraktion: Instanz der HardwareAbstraktion.

        Rückgabewert:
            None.

        Seiteneffekte:
            Speichert die Hardware-Referenz für spätere WLAN-Aufrufe.
        """
        self.hardware_abstraktion = hardware_abstraktion

    def starte_ap(self, ssid, passwort):
        """Startet den Access-Point-Modus als Standardbetrieb.

        Parameter:
            ssid (str): Name des Access-Points.
            passwort (str): Passwort des Access-Points.

        Rückgabewert:
            None.

        Seiteneffekte:
            Delegiert die AP-Konfiguration an die Hardwareabstraktion.
        """
        self.hardware_abstraktion.konfiguriere_wlan_ap(ssid=ssid, passwort=passwort)

    def verbinde_sta(self, ssid, passwort):
        """Bereitet den späteren Station-Modus strukturell vor.

        Parameter:
            ssid (str): Ziel-SSID des vorhandenen WLANs.
            passwort (str): Passwort des Ziel-WLANs.

        Rückgabewert:
            None.

        Seiteneffekte:
            Delegiert eine optionale STA-Verbindung, sofern durch die
            Hardwareabstraktion bereitgestellt.
        """
        if hasattr(self.hardware_abstraktion, "konfiguriere_wlan_sta"):
            self.hardware_abstraktion.konfiguriere_wlan_sta(ssid=ssid, passwort=passwort)

    def initialisiere(self, modus="ap", ssid="miele", passwort="10000000"):
        """Initialisiert das Netzwerk abhängig vom gewünschten Modus.

        Parameter:
            modus (str): "ap" für Access-Point, "sta" für Station.
            ssid (str): SSID für AP oder STA.
            passwort (str): Passwort für AP oder STA.

        Rückgabewert:
            None.

        Seiteneffekte:
            Führt WLAN-Aufrufe auf der Hardwareabstraktion aus.
        """
        if modus == "sta":
            self.verbinde_sta(ssid=ssid, passwort=passwort)
            return
        self.starte_ap(ssid=ssid, passwort=passwort)


class SystemAnwendung:
    """Koordiniert die Initialisierung aller Firmware-Komponenten.

    Zweck:
        Verdrahtet Hardware, Ausgabeschicht, Sensorlogik und REST-Schicht,
        ohne Berechnungs- oder Hardwaredetails zu implementieren.
    """

    def __init__(self):
        """Erzeugt alle Komponenten und verbindet deren Schnittstellen.

        Parameter:
            Keine.

        Rückgabewert:
            None.

        Seiteneffekte:
            Erstellt die zentralen Systemobjekte.
        """
        self.hardware_abstraktion = HardwareAbstraktion()
        self.netzwerk_manager = NetzwerkManager(self.hardware_abstraktion)
        self.output_treiber = OutputDriver(self.hardware_abstraktion)
        self.ntc_sensor = NtcSensor(self.output_treiber)
        self.druck_sensor_pwm = DruckSensorPwm(self.output_treiber)
        self.rest_server = RestServer(
            ntc_sensor=self.ntc_sensor,
            druck_sensor_pwm=self.druck_sensor_pwm,
        )

    def initialisiere_system(self):
        """Führt die vorbereitende Initialisierung des Gesamtsystems aus.

        Parameter:
            Keine.

        Rückgabewert:
            None.

        Seiteneffekte:
            Initialisiert Hardwaregrundzustand, WLAN und Display.
        """
        self.hardware_abstraktion.initialisiere_hardware()
        self.netzwerk_manager.initialisiere(modus="ap", ssid="miele", passwort="10000000")
        self.hardware_abstraktion.initialisiere_display()

    def starte_system(self):
        """Startet den REST-Betrieb nach abgeschlossener Initialisierung.

        Parameter:
            Keine.

        Rückgabewert:
            None.

        Seiteneffekte:
            Startet den REST-Server im konfigurierten Laufzeitmodell.
        """
        self.rest_server.starte_server()


async def async_main():
    """Asynchroner Einstiegspunkt zur Vorbereitung von uasyncio.

    Parameter:
        Keine.

    Rückgabewert:
        None.

    Seiteneffekte:
        Initialisiert und startet das Gesamtsystem.
    """
    anwendung = SystemAnwendung()
    anwendung.initialisiere_system()
    anwendung.starte_system()


def main():
    """Synchroner Einstiegspunkt fuer aktuelle Deployments.

    Parameter:
        Keine.

    Rückgabewert:
        None.

    Seiteneffekte:
        Führt dieselbe Initialisierung wie async_main aus.
    """
    anwendung = SystemAnwendung()
    anwendung.initialisiere_system()
    anwendung.starte_system()


if __name__ == "__main__":
    main()
