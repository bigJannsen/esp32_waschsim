"""Logische Ausgabeschicht zwischen Sensorlogik und Hardware."""


class OutputDriver:
    """Delegiert validierte Ausgabewerte an die Hardwareabstraktion."""

    CODE_MIN = 0
    CODE_MAX = 255
    DUTY_MIN_NORM = 0.233
    DUTY_MAX_NORM = 0.900

    def __init__(self, hardware):
        """Speichert die Hardwareabstraktion als einzige IO-Schnittstelle."""
        self.hardware = hardware

    def setze_ntc_code(self, code):
        """Validiert einen NTC-Code und setzt die entsprechende Bitmaske."""
        code_int = self._validiere_code(code)
        bitmaske = code_int & 0xFF
        self.hardware.setze_bitmaske(bitmaske)
        return bitmaske

    def setze_pwm_duty(self, duty):
        """Validiert einen Duty-Wert (float) und delegiert an die Hardware."""
        duty_normiert = self._validiere_duty_wert(duty)
        self.hardware.setze_pwm_duty(duty_normiert)
        return duty_normiert

    def _validiere_code(self, code):
        """Validiert NTC-Code als Integer im Bereich 0 bis 255."""
        if isinstance(code, bool) or not isinstance(code, int):
            raise ValueError("code muss int sein")
        if code < self.CODE_MIN or code > self.CODE_MAX:
            raise ValueError("code ausserhalb des gueltigen Bereichs 0 bis 255")
        return code

    def _validiere_duty_wert(self, duty):
        """Validiert normierten PWM-Duty-Wert strikt als float."""
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")
        if duty < self.DUTY_MIN_NORM or duty > self.DUTY_MAX_NORM:
            raise ValueError("duty ausserhalb des Sensorbereichs 0.233 bis 0.90")
        return duty
