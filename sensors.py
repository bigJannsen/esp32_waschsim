"""Fachliche Sensorlogik ohne Hardwarezugriffe.

Dieses Modul stellt ausschließlich physikalische Modell-Schnittstellen bereit.
Die Ausgabe erfolgt über den OutputDriver.
"""


class NtcSensor:
    """Skelett fuer das NTC-Modell mit Interpolation und Extrapolation."""

    LSB_OHM = 250
    MAX_CODE_8_BIT = 255

    def __init__(self, output_treiber):
        """Speichert den OutputDriver als nachgelagerte Schnittstelle."""
        self.output_treiber = output_treiber
        self.ntc_kennlinie = self._erzeuge_ntc_kennlinie()

    def _erzeuge_ntc_kennlinie(self):
        """Liefert die tabellarische NTC-Basiskennlinie fuer weitere Berechnungen."""
        return [
            (0.0, 38000.0),
            (25.0, 12000.0),
            (50.0, 4520.0),
            (75.0, 1960.0),
            (100.0, 1090.0),
        ]

    def verarbeite_temperaturwert(self, temperatur_c):
        """Verarbeitet Temperatur und uebergibt den 8-Bit-Code an den OutputDriver."""
        widerstand_ohm = self.berechne_widerstand_ohm(temperatur_c)
        quantisierter_code = self.quantisierung_ohm_zu_code(widerstand_ohm)
        self.output_treiber.setze_ntc_code(quantisierter_code)

    def berechne_widerstand_ohm(self, temperatur_c):
        """Berechnet den NTC-Widerstand via Interpolation/Extrapolation.

        TODO: Finale mathematische Umsetzung gemaess Kennlinie ergaenzen.
        """
        _ = temperatur_c
        return 0.0

    def quantisierung_ohm_zu_code(self, widerstand_ohm):
        """Quantisiert den Widerstand in 250-Ohm-Schritten auf 8 Bit.

        TODO: Finale Quantisierungslogik mit Grenzwertbehandlung ergaenzen.
        """
        _ = widerstand_ohm
        return 0


class DruckSensorPwm:
    """Skelett fuer das PWM-Drucksensormodell 2066.05xx."""

    DRUCK_MIN_PA = 0.0
    DRUCK_MAX_PA = 2452.0
    PWM_MIN_NORM = 0.233
    PWM_MAX_NORM = 0.900

    def __init__(self, output_treiber):
        """Speichert den OutputDriver als nachgelagerte Schnittstelle."""
        self.output_treiber = output_treiber

    def verarbeite_druckwert_pa(self, druck_pa):
        """Verarbeitet Druck und uebergibt den normierten PWM-Wert."""
        pwm_normiert = self.berechne_pwm_normiert(druck_pa)
        self.output_treiber.setze_druck_pwm_normiert(pwm_normiert)

    def berechne_pwm_normiert(self, druck_pa):
        """Berechnet den PWM-Wert als Normierung im Bereich 0.0 bis 1.0.

        TODO: Finale lineare Kennlinienabbildung zwischen 23.3% und 90% ergaenzen.
        """
        _ = druck_pa
        return 0.0
