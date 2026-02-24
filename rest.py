"""REST-Kommunikationsschicht der ESP32-Firmware."""

import json


class RestServer:
    """Kapselt REST-Routen und HTTP-Antworterzeugung."""

    def __init__(self, ntc_sensor, druck_sensor):
        """Speichert Referenzen auf die Sensorlogik."""
        self.ntc_sensor = ntc_sensor
        self.druck_sensor = druck_sensor
        self.socket_server = None

    def starte_server(self):
        """Startet den REST-Server (Transport ist als Skelett offen)."""
        return None

    def verarbeite_http_anfrage(self, rohanfrage):
        """Parst eine HTTP-Anfrage und liefert eine Standard-Fehlerantwort."""
        _ = rohanfrage
        return self.erstelle_fehlerantwort(501, "Routenverarbeitung ist als Skelett vorbereitet.")

    def route_setze_temperatur(self, temperatur_c):
        """Verarbeitet eine Temperatur als float ueber den NTC-Sensor."""
        if not self.ist_gueltige_temperatur(temperatur_c):
            return self.erstelle_fehlerantwort(400, "Ungueltiger Temperaturwert.")

        self.ntc_sensor.verarbeite_temperatur(temperatur_c)
        return self.erstelle_erfolgsantwort("Temperaturwert angenommen.")

    def route_setze_druck_pa(self, druck_pa):
        """Verarbeitet einen Druckwert als float ueber den Drucksensor."""
        if not self.ist_gueltiger_druck(druck_pa):
            return self.erstelle_fehlerantwort(400, "Ungueltiger Druckwert.")

        self.druck_sensor.verarbeite_druck_pa(druck_pa)
        return self.erstelle_erfolgsantwort("Druckwert angenommen.")

    def ist_gueltige_temperatur(self, temperatur_c):
        """Prueft Temperaturwerte strikt als float."""
        return isinstance(temperatur_c, float)

    def ist_gueltiger_druck(self, druck_pa):
        """Prueft Druckwerte strikt als float."""
        return isinstance(druck_pa, float)

    def erstelle_erfolgsantwort(self, meldung):
        """Erzeugt eine JSON-Erfolgsantwort."""
        return 200, json.dumps({"status": "ok", "meldung": meldung})

    def erstelle_fehlerantwort(self, status_code, meldung):
        """Erzeugt eine JSON-Fehlerantwort."""
        return status_code, json.dumps({"status": "fehler", "meldung": meldung})
