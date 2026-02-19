"""REST-Kommunikationsschicht der ESP32-Firmware.

Dieses Modul enthält ausschließlich HTTP-bezogene Verarbeitung:
- Routen-Definitionen
- Request-Parsing
- Eingabevalidierung
- strukturierte Antwortobjekte

Es enthält keine Hardwarezugriffe und keine physikalischen Berechnungen.
"""

import json


class RestServer:
    """Skelett eines leichtgewichtigen REST-Servers für MicroPython."""

    def __init__(self, ntc_sensor, druck_sensor_pwm):
        """Speichert Referenzen auf die fachlichen Sensor-Komponenten."""
        self.ntc_sensor = ntc_sensor
        self.druck_sensor_pwm = druck_sensor_pwm
        self.socket_server = None

    def starte_server(self):
        """Startet den HTTP-Server im vorgesehenen AP-Betrieb.

        TODO:
        - socket initialisieren
        - Port binden
        - Request-Schleife sequenziell abarbeiten
        """
        return None

    def verarbeite_http_anfrage(self, rohanfrage):
        """Parst eine HTTP-Anfrage und delegiert an die passende Route."""
        _ = rohanfrage
        return self.erstelle_fehlerantwort(
            status_code=501,
            meldung="Routenverarbeitung ist als Skelett vorbereitet.",
        )

    def route_setze_temperatur(self, temperatur_c):
        """REST-Route zur Übergabe eines Temperaturwerts an den NTC-Sensor."""
        if not self.ist_gueltige_temperatur(temperatur_c):
            return self.erstelle_fehlerantwort(400, "Ungueltiger Temperaturwert.")

        self.ntc_sensor.verarbeite_temperaturwert(temperatur_c)
        return self.erstelle_erfolgsantwort("Temperaturwert angenommen.")

    def route_setze_druck_pa(self, druck_pa):
        """REST-Route zur Übergabe eines Druckwerts an den PWM-Drucksensor."""
        if not self.ist_gueltiger_druck(druck_pa):
            return self.erstelle_fehlerantwort(400, "Ungueltiger Druckwert.")

        self.druck_sensor_pwm.verarbeite_druckwert_pa(druck_pa)
        return self.erstelle_erfolgsantwort("Druckwert angenommen.")

    def ist_gueltige_temperatur(self, temperatur_c):
        """Prueft den Datentyp und das Vorhandensein des Temperaturwerts."""
        return isinstance(temperatur_c, (int, float))

    def ist_gueltiger_druck(self, druck_pa):
        """Prueft den Datentyp und das Vorhandensein des Druckwerts."""
        return isinstance(druck_pa, (int, float))

    def erstelle_erfolgsantwort(self, meldung):
        """Erzeugt ein strukturiertes JSON-Antwortobjekt fuer Erfolg."""
        antwort = {
            "status": "ok",
            "meldung": meldung,
        }
        return 200, json.dumps(antwort)

    def erstelle_fehlerantwort(self, status_code, meldung):
        """Erzeugt ein strukturiertes JSON-Antwortobjekt fuer Fehler."""
        antwort = {
            "status": "fehler",
            "meldung": meldung,
        }
        return status_code, json.dumps(antwort)
