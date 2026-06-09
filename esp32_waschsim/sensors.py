"""Sensorlogik und Kennwertverarbeitung"""


# Allg. Sensorbasis


class SensorBasis:
    """gemeinsame Sensorbasis"""

    def __init__(self, hardware=None):
        """Hardware Referenz setzen"""
        self.hardware = hardware
        self._pruefe_implementierung()

    def _pruefe_implementierung(self):
        """optional in Unterklassen"""
        return None

    @staticmethod
    def _validiere_float_wert(wert, name):
        """float pruefen"""
        if isinstance(wert, bool) or not isinstance(wert, float):
            raise ValueError("{} muss float sein".format(name))

        return wert

    @classmethod
    def _validiere_float_bereich(cls, wert, name, minimum, maximum):
        """float Bereich pruefen"""
        wert = cls._validiere_float_wert(wert, name)

        if wert < minimum or wert > maximum:
            raise ValueError(
                "{} ausserhalb Bereich {} bis {}".format(
                    name,
                    minimum,
                    maximum,
                )
            )

        return wert

    @staticmethod
    def _pruefe_pflichtattribute(klasse, attribute):
        """Pflichtwerte pruefen"""
        for attribut in attribute:
            if getattr(klasse, attribut) is None:
                raise NotImplementedError(
                    "{} fehlt in der Unterklasse".format(attribut)
                )


# NTC-Sensor Basis


class NtcSensorBasis(SensorBasis):
    """Basis fuer NTC Kennlinien"""

    KENNLINIE_NTC = None
    DIGIPOT_MAX_RESISTANCE = None
    DIGIPOT_CODE_MIN = None
    DIGIPOT_CODE_MAX = None
    DIGIPOT_CODE_INVERTIERT = None

    def _pruefe_implementierung(self):
        """NTC Kennwerte pruefen"""
        self._pruefe_pflichtattribute(
            self.__class__,
            [
                "KENNLINIE_NTC",
                "DIGIPOT_MAX_RESISTANCE",
                "DIGIPOT_CODE_MIN",
                "DIGIPOT_CODE_MAX",
                "DIGIPOT_CODE_INVERTIERT",
            ],
        )
        self._pruefe_kennlinie()

    def _pruefe_kennlinie(self):
        """Kennlinie pruefen"""
        kennlinie = self.KENNLINIE_NTC

        if not isinstance(kennlinie, list) or len(kennlinie) < 2:
            raise ValueError("KENNLINIE_NTC braucht mindestens zwei Punkte")

        letzter_temperaturwert = None

        for punkt in kennlinie:
            if not isinstance(punkt, tuple) or len(punkt) != 2:
                raise ValueError("KENNLINIE_NTC braucht Tupel mit zwei Werten")

            temperatur_c, widerstand_ohm = punkt

            self._validiere_float_wert(temperatur_c, "temperatur_c")
            self._validiere_float_wert(widerstand_ohm, "widerstand_ohm")

            if letzter_temperaturwert is not None and temperatur_c <= letzter_temperaturwert:
                raise ValueError("KENNLINIE_NTC muss aufsteigend sein")

            letzter_temperaturwert = temperatur_c

    def verarbeite_temperatur(self, temperatur_c):
        """Temperatur in Digipot Code"""
        widerstand_ohm = self.berechne_widerstand_ohm(temperatur_c)
        ntc_code = self.quantisierung_ohm_zu_code(widerstand_ohm)
        self.schreibe_ntc_code(ntc_code)

        return ntc_code

    def berechne_widerstand_ohm(self, temperatur_c):
        """Temperatur in Widerstand"""
        temperatur_c = self._validiere_float_wert(temperatur_c, "temperatur_c")
        kennlinie = self.KENNLINIE_NTC

        if temperatur_c <= kennlinie[0][0]:
            return self._lineare_interpolation(
                temperatur_c,
                kennlinie[0],
                kennlinie[1],
            )

        if temperatur_c >= kennlinie[-1][0]:
            return self._lineare_interpolation(
                temperatur_c,
                kennlinie[-2],
                kennlinie[-1],
            )

        for index in range(len(kennlinie) - 1):
            punkt_a = kennlinie[index]
            punkt_b = kennlinie[index + 1]

            if punkt_a[0] <= temperatur_c <= punkt_b[0]:
                return self._lineare_interpolation(
                    temperatur_c,
                    punkt_a,
                    punkt_b,
                )

        raise ValueError("keine passende Kennlinie gefunden")

    def quantisierung_ohm_zu_code(self, widerstand_ohm):
        """Widerstand in Digipot Code"""
        widerstand_ohm = self._validiere_float_wert(
            widerstand_ohm,
            "widerstand_ohm",
        )

        code = int(
            round(
                (widerstand_ohm / self.DIGIPOT_MAX_RESISTANCE)
                * self.DIGIPOT_CODE_MAX
            )
        )

        code = self._begrenze_digipot_code(code)

        if self.DIGIPOT_CODE_INVERTIERT:
            code = self.DIGIPOT_CODE_MAX - code

        return code

    def schreibe_ntc_code(self, ntc_code):
        """NTC Code ausgeben"""
        if self.hardware is not None:
            self.hardware.setze_ntc_code(ntc_code)

    def _begrenze_digipot_code(self, code):
        """Digipot Code begrenzen"""
        if code < self.DIGIPOT_CODE_MIN:
            return self.DIGIPOT_CODE_MIN

        if code > self.DIGIPOT_CODE_MAX:
            return self.DIGIPOT_CODE_MAX

        return code

    @staticmethod
    def _lineare_interpolation(x_wert, punkt_a, punkt_b):
        """linear zwischen zwei Punkten"""
        x_a, y_a = punkt_a
        x_b, y_b = punkt_b

        if x_b == x_a:
            raise ValueError("doppelte Temperaturstuetzstelle")

        return y_a + ((y_b - y_a) / (x_b - x_a)) * (x_wert - x_a)


# NTC PWM908


class NtcSensor(NtcSensorBasis):
    """Projekt NTC mit MCP4161"""

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

    DIGIPOT_MAX_RESISTANCE = 50000.0
    DIGIPOT_CODE_MIN = 0
    DIGIPOT_CODE_MAX = 255
    DIGIPOT_CODE_INVERTIERT = False


# Drucksensor Logik


class PressureSensorBasis(SensorBasis):
    """Basis für Drucksensor PWM"""

    DRUCK_MIN_PA = None
    DRUCK_MAX_PA = None
    DUTY_MIN_NORM = None
    DUTY_MAX_NORM = None

    def _pruefe_implementierung(self):
        """Druck Kennwerte pruefen"""
        self._pruefe_pflichtattribute(
            self.__class__,
            [
                "DRUCK_MIN_PA",
                "DRUCK_MAX_PA",
                "DUTY_MIN_NORM",
                "DUTY_MAX_NORM",
            ],
        )
        self._pruefe_druckparameter()

    def _pruefe_druckparameter(self):
        """Druck und Duty Grenzen pruefen"""
        if self.DRUCK_MAX_PA <= self.DRUCK_MIN_PA:
            raise ValueError("DRUCK_MAX_PA muss groesser als DRUCK_MIN_PA sein")

        if self.DUTY_MAX_NORM <= self.DUTY_MIN_NORM:
            raise ValueError("DUTY_MAX_NORM muss groesser als DUTY_MIN_NORM sein")

        if self.DUTY_MIN_NORM < 0.0 or self.DUTY_MAX_NORM > 1.0:
            raise ValueError("Duty muss zwischen 0.0 und 1.0 liegen")

    def verarbeite_druck_pa(self, druck_pa):
        """Druck in PWM Duty"""
        duty_norm = self.berechne_duty_norm(druck_pa)
        self.schreibe_pwm_duty(duty_norm)

        return duty_norm

    def berechne_duty_norm(self, druck_pa):
        """Druckwert umrechnen"""
        druck_pa = self._validiere_float_bereich(
            druck_pa,
            "druck_pa",
            self.DRUCK_MIN_PA,
            self.DRUCK_MAX_PA,
        )

        anteil = (druck_pa - self.DRUCK_MIN_PA) / (
            self.DRUCK_MAX_PA - self.DRUCK_MIN_PA
        )
        duty_span = self.DUTY_MAX_NORM - self.DUTY_MIN_NORM

        return self.DUTY_MIN_NORM + anteil * duty_span

    def schreibe_pwm_duty(self, duty_norm):
        """PWM Duty ausgeben"""
        if self.hardware is not None:
            self.hardware.setze_pwm_duty(duty_norm)


# Drucksensor PWM908


class PressureSensor(PressureSensorBasis):
    """Projekt Drucksensor"""

    DRUCK_MIN_PA = 0.0
    DRUCK_MAX_PA = 2452.0
    DUTY_MIN_NORM = 0.233
    DUTY_MAX_NORM = 0.900