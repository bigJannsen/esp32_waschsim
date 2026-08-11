"""Deterministische Mock-Hardware fuer lokale Tests."""


class MockHardware:
    """Mock-Implementierung mit kompatibler Sensor-Schnittstelle."""

    def __init__(self):
        """Initialisiert den reproduzierbaren Testzustand."""
        self.letzter_ntc_code = 0
        self.letzter_ntc_code_kanal_1 = 0
        self.letzter_ntc_code_kanal_2 = 0
        self.letztes_pwm_duty = 0.0
        self.temperature_1_c = 0.0
        self.temperature_2_c = 0.0
        self.pressure_pa = 0.0

    @staticmethod
    def _clamp_code(code):
        if code < 0:
            return 0
        if code > 255:
            return 255
        return code

    def write_digipot(self, channel, code):
        """Speichert den Digipot-Code pro Kanal im Mock-Zustand."""
        if channel not in (1, 2):
            raise ValueError("channel muss 1 oder 2 sein")

        code = self._clamp_code(int(code))
        if channel == 1:
            self.letzter_ntc_code_kanal_1 = code
        else:
            self.letzter_ntc_code_kanal_2 = code
        self.letzter_ntc_code = code

    def _write_code_auf_beide_digipots(self, code):
        """Schreibt denselben NTC-Code auf beide simulierten Digipot-Kanaele."""
        self.write_digipot(1, code)
        self.write_digipot(2, code)
        self.letzter_ntc_code = code

    def write_ntc_code(self, ntc_code):
        """Schreibt denselben NTC-Code auf beide simulierten Digipot-Kanaele."""
        code = self._clamp_code(int(ntc_code))
        self._write_code_auf_beide_digipots(code)

    def setze_ntc_code(self, ntc_code):
        """Kompatibilitaetsmethode fuer Sensor- und Testaufrufe."""
        if isinstance(ntc_code, bool) or not isinstance(ntc_code, int):
            raise ValueError("ntc_code muss int sein")
        if ntc_code < 0 or ntc_code > 255:
            raise ValueError("ntc_code muss im Bereich 0 bis 255 liegen")
        self.write_ntc_code(ntc_code)

    def setze_pwm_duty(self, duty):
        """Speichert den PWM-Duty im Mock-Zustand."""
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")
        if duty < 0.0 or duty > 1.0:
            raise ValueError("duty muss im Bereich 0.0 bis 1.0 liegen")
        self.letztes_pwm_duty = duty

    def setze_ntc_zustand(self, channel, temperatur_c, code):
        """Speichert Fachwert und Code gemeinsam pro ausgewaehltem Kanal."""
        channels = (1, 2) if channel is None else (channel,)
        for kanal in channels:
            self.write_digipot(kanal, code)
            setattr(self, "temperature_{}_c".format(kanal), float(temperatur_c))

    def setze_druck_zustand(self, pressure_pa, duty):
        """Speichert Druck und daraus berechneten Duty gemeinsam."""
        self.pressure_pa = float(pressure_pa)
        self.setze_pwm_duty(float(duty))

    def lese_status(self):
        """Liefert den aktuellen Mock-Status fuer Assertions in Tests."""
        return {
            "backend": "mock",
            "letzter_ntc_code": self.letzter_ntc_code,
            "letzter_ntc_code_kanal_1": self.letzter_ntc_code_kanal_1,
            "letzter_ntc_code_kanal_2": self.letzter_ntc_code_kanal_2,
            "letztes_pwm_duty": self.letztes_pwm_duty,
            "temperature_1_c": self.temperature_1_c,
            "temperature_2_c": self.temperature_2_c,
            "ntc_code_1": self.letzter_ntc_code_kanal_1,
            "ntc_code_2": self.letzter_ntc_code_kanal_2,
            "pressure_pa": self.pressure_pa,
            "pwm_duty": self.letztes_pwm_duty,
            "letzter_status_ok": True,
            "letzter_status_text": "OK",
        }
