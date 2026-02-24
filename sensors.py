"""Fachliche Sensorlogik ohne Hardwarezugriffe.

Dieses Modul enthaelt ausschliesslich deterministische Berechnungen,
Eingabevalidierung und optionale Uebergabe an einen Ausgabetreiber.
"""

import math


class NtcSensor:
    """NTC-Modell mit fester Kennlinie, Interpolation und Extrapolation.

    Zweck:
        Wandelt Temperaturwerte in Widerstand und anschließend in einen
        8-Bit-Code um, ohne direkt auf Hardware zuzugreifen.
    """

    KENNLINIE_NTC = [
        (0.0, 38000.0),
        (5.0, 29700.0),
        (10.0, 23400.0),
        (15.0, 18600.0),
        (20.0, 14900.0),
        (25.0, 12000.0),
        (30.0, 9730.0),
        (35.0, 7960.0),
        (40.0, 6550.0),
        (45.0, 5420.0),
        (50.0, 4520.0),
        (55.0, 3780.0),
        (60.0, 3190.0),
        (65.0, 2700.0),
        (70.0, 2290.0),
        (75.0, 1960.0),
        (80.0, 1680.0),
        (85.0, 1450.0),
        (90.0, 1250.0),
        (95.0, 1150.0),
        (100.0, 1090.0),
    ]
    LSB_OHM = 250.0
    CODE_MIN = 0
    CODE_MAX = 255

    def __init__(self, output_treiber=None):
        """Initialisiert den Sensor mit optionalem Ausgabetreiber.

        Parameter:
            output_treiber: Optionale Instanz eines OutputDriver.

        Rueckgabewert:
            None.

        Seiteneffekte:
            Speichert eine Referenz fuer die optionale Ausgabe.
        """
        self.output_treiber = output_treiber

    def verarbeite_temperatur(self, temperatur_c):
        """Verarbeitet eine Temperatur als float und liefert den NTC-Code.

        Parameter:
            temperatur_c (float): Temperatur in Grad Celsius.

        Rueckgabewert:
            int: Quantisierter NTC-Code im Bereich 0 bis 255.

        Seiteneffekte:
            Delegiert optional an OutputDriver.setze_ntc_code().
        """
        widerstand_ohm = self.berechne_widerstand_ohm(temperatur_c)
        code = self.quantisierung_ohm_zu_code(widerstand_ohm)

        if self.output_treiber is not None:
            self.output_treiber.setze_ntc_code(code)

        return code

    def verarbeite_temperaturwert(self, temperatur_c):
        """Alias für verarbeite_temperatur() zur Kompatibilität.

        Parameter:
            temperatur_c (float): Temperatur in Grad Celsius.

        Rueckgabewert:
            int: Quantisierter NTC-Code.

        Seiteneffekte:
            Siehe verarbeite_temperatur().
        """
        return self.verarbeite_temperatur(temperatur_c)

    def berechne_widerstand_ohm(self, temperatur_c):
        """Berechnet den NTC-Widerstand per linearer Interpolation.

        Parameter:
            temperatur_c (float): Temperatur in Grad Celsius.

        Rueckgabewert:
            float: Interpolierter oder extrapolierter Widerstand in Ohm.

        Seiteneffekte:
            Keine.
        """
        temperatur_c = self._validiere_float_wert(temperatur_c, "temperatur_c")

        kennlinie = self.KENNLINIE_NTC

        if temperatur_c <= kennlinie[0][0]:
            return self._lineare_interpolation(temperatur_c, kennlinie[0], kennlinie[1])

        if temperatur_c >= kennlinie[-1][0]:
            return self._lineare_interpolation(temperatur_c, kennlinie[-2], kennlinie[-1])

        for index in range(len(kennlinie) - 1):
            stuetzstelle_a = kennlinie[index]
            stuetzstelle_b = kennlinie[index + 1]
            if stuetzstelle_a[0] <= temperatur_c <= stuetzstelle_b[0]:
                return self._lineare_interpolation(
                    temperatur_c,
                    stuetzstelle_a,
                    stuetzstelle_b,
                )

        raise ValueError("interner Fehler: keine gueltige Kennliniensegmentzuordnung")

    def quantisierung_ohm_zu_code(self, widerstand_ohm):
        """Quantisiert den Widerstand mit 250-Ohm-LSB auf 8 Bit.

        Parameter:
            widerstand_ohm (float): Physikalischer Widerstand in Ohm.

        Rueckgabewert:
            int: NTC-Code im Bereich 0 bis 255.

        Seiteneffekte:
            Keine.
        """
        widerstand_ohm = self._validiere_float_wert(widerstand_ohm, "widerstand_ohm")
        if widerstand_ohm < 0.0:
            code = self.CODE_MIN
        else:
            code = int(math.ceil(widerstand_ohm / self.LSB_OHM))

        if code < self.CODE_MIN:
            return self.CODE_MIN
        if code > self.CODE_MAX:
            return self.CODE_MAX
        return code

    @staticmethod
    def _lineare_interpolation(x_wert, punkt_a, punkt_b):
        """Interpoliert oder extrapoliert linear zwischen zwei Stuetzstellen.

        Parameter:
            x_wert (float): Zielwert auf der x-Achse.
            punkt_a (tuple): Erste Stuetzstelle (x, y).
            punkt_b (tuple): Zweite Stuetzstelle (x, y).

        Rueckgabewert:
            float: Interpolierter y-Wert.

        Seiteneffekte:
            Keine.
        """
        x_a, y_a = punkt_a
        x_b, y_b = punkt_b

        if x_b == x_a:
            raise ValueError("ungueltige Kennlinie: identische x-Stuetzstellen")

        steigung = (y_b - y_a) / (x_b - x_a)
        return y_a + steigung * (x_wert - x_a)

    @staticmethod
    def _validiere_float_wert(wert, name):
        """Validiert physikalische Eingaben strikt als float.

        Parameter:
            wert (float): Zu pruefender physikalischer Wert.
            name (str): Feldname fuer Fehlermeldungen.

        Rueckgabewert:
            float: Unveraenderter, gueltiger float-Wert.

        Seiteneffekte:
            Keine.
        """
        if isinstance(wert, bool) or not isinstance(wert, float):
            raise ValueError("{} muss float sein".format(name))
        return wert


class PressureSensor:
    """Drucksensormodell der Baureihe 2066.05xx mit linearer Duty-Berechnung.

    Zweck:
        Wandelt Druckwerte in einen normierten PWM-Duty-Wert um.
    """

    DRUCK_MIN_PA = 0.0
    DRUCK_MAX_PA = 2452.0
    DUTY_MIN_NORM = 0.233
    DUTY_MAX_NORM = 0.900

    def __init__(self, output_treiber=None):
        """Initialisiert den Sensor mit optionalem Ausgabetreiber.

        Parameter:
            output_treiber: Optionale Instanz eines OutputDriver.

        Rueckgabewert:
            None.

        Seiteneffekte:
            Speichert eine Referenz fuer die optionale Ausgabe.
        """
        self.output_treiber = output_treiber

    def verarbeite_druck_pa(self, druck_pa):
        """Verarbeitet Druck in Pascal und liefert den Duty-Wert.

        Parameter:
            druck_pa (float): Druck in Pascal.

        Rueckgabewert:
            float: Normierter PWM-Duty-Wert.

        Seiteneffekte:
            Delegiert optional an OutputDriver.setze_druck_pwm_normiert().
        """
        duty_norm = self.berechne_duty_norm(druck_pa)

        if self.output_treiber is not None:
            self.output_treiber.setze_druck_pwm_normiert(duty_norm)

        return duty_norm

    def berechne_duty_norm(self, druck_pa):
        """Berechnet den normierten PWM-Duty-Wert gemaess Spezifikation.

        Parameter:
            druck_pa (float): Druck in Pascal.

        Rueckgabewert:
            float: Normierter Duty-Wert zwischen 0.233 und 0.900.

        Seiteneffekte:
            Keine.
        """
        druck_pa = self._validiere_druck_pa(druck_pa)

        anteil = druck_pa / self.DRUCK_MAX_PA
        span = self.DUTY_MAX_NORM - self.DUTY_MIN_NORM
        return self.DUTY_MIN_NORM + anteil * span

    def _validiere_druck_pa(self, druck_pa):
        """Validiert Typ und Wertebereich des Drucks in Pascal.

        Parameter:
            druck_pa (float): Zu validierender Druck.

        Rueckgabewert:
            float: Gepruefter Druckwert.

        Seiteneffekte:
            Keine.
        """
        if isinstance(druck_pa, bool) or not isinstance(druck_pa, float):
            raise ValueError("druck_pa muss float sein")

        if druck_pa < self.DRUCK_MIN_PA or druck_pa > self.DRUCK_MAX_PA:
            raise ValueError("druck_pa ausserhalb des gueltigen Bereichs 0 bis 2452")

        return druck_pa


class DruckSensorPwm(PressureSensor):
    """Abwaertskompatible Klassenbezeichnung fuer bestehende Aufrufer.

    Zweck:
        Erhaelt bestehende Namenskonventionen und erweitert PressureSensor.
    """

    def verarbeite_druckwert_pa(self, druck_pa):
        """Alias für verarbeite_druck_pa() zur Kompatibilität.

        Parameter:
            druck_pa (float): Druck in Pascal.

        Rueckgabewert:
            float: Normierter Duty-Wert.

        Seiteneffekte:
            Siehe verarbeite_druck_pa().
        """
        return self.verarbeite_druck_pa(druck_pa)

    def berechne_pwm_normiert(self, druck_pa):
        """Alias für berechne_duty_norm() zur Kompatibilität.

        Parameter:
            druck_pa (float): Druck in Pascal.

        Rueckgabewert:
            float: Normierter Duty-Wert.

        Seiteneffekte:
            Keine.
        """
        return self.berechne_duty_norm(druck_pa)
