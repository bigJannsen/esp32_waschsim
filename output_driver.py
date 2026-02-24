"""Logische Ausgabeschicht zwischen Sensorlogik und Hardware.

Dieses Modul enthaelt ausschliesslich:
- Validierung von NTC-Codes und PWM-Duty-Werten
- Umwandlung von Codes in 8-Bit-Bitmasken
- Delegation an die Hardware-Abstraktionsschicht
"""


class OutputDriver:
    """Bruecke zwischen berechneten Ausgangswerten und Hardwarezugriffen.

    Zweck:
        Entkoppelt Sensorlogik von Hardwarezugriffen und erhaelt die
        einheitlichen Ausgabeschnittstellen.
    """

    CODE_MIN = 0
    CODE_MAX = 255
    BITMASKE_MIN = 0
    BITMASKE_MAX = 255
    DUTY_MIN_NORM = 0.233
    DUTY_MAX_NORM = 0.900

    def __init__(self, hardware):
        """Speichert die Hardware-Abstraktion als einzige IO-Schnittstelle.

        Parameter:
            hardware: Instanz mit setze_bitmaske() und setze_pwm_duty().

        Rueckgabewert:
            None.

        Seiteneffekte:
            Speichert die Referenz auf die Hardwareabstraktion.
        """
        self.hardware = hardware

    def setze_ntc_code(self, code):
        """Validiert den NTC-Code und delegiert die resultierende Bitmaske.

        Parameter:
            code (int): NTC-Code im Bereich 0 bis 255.

        Rueckgabewert:
            int: Die gesetzte 8-Bit-Bitmaske.

        Seiteneffekte:
            Schreibt den Bitmaskenwert ueber die Hardwareabstraktion.
        """
        code_int = self._validiere_code(code)
        bitmaske = self.code_zu_bitmaske(code_int)
        self._setze_hardware_bitmaske(bitmaske)
        return bitmaske

    def code_zu_bitmaske(self, code):
        """Wandelt einen gueltigen NTC-Code in eine 8-Bit-Bitmaske um.

        Parameter:
            code (int): NTC-Code im Bereich 0 bis 255.

        Rueckgabewert:
            int: 8-Bit-Bitmaske.

        Seiteneffekte:
            Keine.
        """
        code_int = self._validiere_code(code)
        bitmaske = code_int & 0xFF

        if bitmaske < self.BITMASKE_MIN or bitmaske > self.BITMASKE_MAX:
            raise ValueError("bitmaske ausserhalb des gueltigen 8-Bit-Bereichs 0 bis 255")

        return bitmaske

    def setze_pwm_duty(self, duty, strikt=True, clampen=False):
        """Validiert und setzt den normierten PWM-Duty-Wert.

        Parameter:
            duty (float): Normierter Duty-Wert.
            strikt (bool): Bei True gilt der Sensorspezifikationsbereich.
            clampen (bool): Bei True werden Grenzverletzungen begrenzt.

        Rueckgabewert:
            float: Der an die Hardware delegierte Duty-Wert.

        Seiteneffekte:
            Schreibt den Duty-Wert ueber die Hardwareabstraktion.
        """
        duty_normiert = self._validiere_duty_wert(
            duty,
            strikt=strikt,
            clampen=clampen,
        )
        self._setze_hardware_pwm_duty(duty_normiert)
        return duty_normiert

    def setze_druck_pwm_normiert(self, duty_normiert, strikt=True, clampen=False):
        """Alias fuer setze_pwm_duty() zur Kompatibilitaet.

        Parameter:
            duty_normiert (float): Normierter Duty-Wert.
            strikt (bool): Bereichspruefung gemaess Sensorgrenzen.
            clampen (bool): Optionales Begrenzen statt Fehler.

        Rueckgabewert:
            float: Delegierter Duty-Wert.

        Seiteneffekte:
            Siehe setze_pwm_duty().
        """
        return self.setze_pwm_duty(duty_normiert, strikt=strikt, clampen=clampen)

    def _setze_hardware_bitmaske(self, bitmaske):
        """Delegiert eine Bitmaske an kompatible Hardwaremethoden.

        Parameter:
            bitmaske (int): 8-Bit-Bitmaske.

        Rueckgabewert:
            None.

        Seiteneffekte:
            Ruft die Hardwareausgabe auf.
        """
        if hasattr(self.hardware, "setze_bitmaske"):
            self.hardware.setze_bitmaske(bitmaske)
            return

        if hasattr(self.hardware, "setze_ntc_bitmaske"):
            self.hardware.setze_ntc_bitmaske(bitmaske)
            return

        raise AttributeError(
            "hardware-objekt unterstuetzt keine Bitmasken-Ausgabe: "
            "erwartet setze_bitmaske(bitmaske)"
        )

    def _setze_hardware_pwm_duty(self, duty_normiert):
        """Delegiert einen Duty-Wert an kompatible Hardwaremethoden.

        Parameter:
            duty_normiert (float): Normierter Duty-Wert.

        Rueckgabewert:
            None.

        Seiteneffekte:
            Ruft die Hardwareausgabe auf.
        """
        if hasattr(self.hardware, "setze_pwm_duty"):
            self.hardware.setze_pwm_duty(duty_normiert)
            return

        if hasattr(self.hardware, "setze_pwm_druckkanal"):
            self.hardware.setze_pwm_druckkanal(duty_normiert)
            return

        if hasattr(self.hardware, "setze_pwm_duty_normiert"):
            self.hardware.setze_pwm_duty_normiert(duty_normiert)
            return

        raise AttributeError(
            "hardware-objekt unterstuetzt keine PWM-Ausgabe: "
            "erwartet setze_pwm_duty(duty)"
        )

    def _validiere_code(self, code):
        """Validiert NTC-Code als Integer im Bereich 0 bis 255.

        Parameter:
            code (int|float): Ganzzahliger Wert fuer den Ausgabecode.

        Rueckgabewert:
            int: Gepruefter Code.

        Seiteneffekte:
            Keine.
        """
        if isinstance(code, bool):
            raise ValueError("code muss int sein, bool ist nicht zulaessig")

        if isinstance(code, float):
            if not code.is_integer():
                raise ValueError("code als float muss einen ganzzahligen Wert haben")
            code_int = int(code)
        elif isinstance(code, int):
            code_int = code
        else:
            raise ValueError("code muss int oder ganzzahliger float sein")

        if code_int < self.CODE_MIN or code_int > self.CODE_MAX:
            raise ValueError("code ausserhalb des gueltigen Bereichs 0 bis 255")

        return code_int

    def _validiere_duty_wert(self, duty, strikt=True, clampen=False):
        """Validiert normierten PWM-Duty-Wert als physikalischen float.

        Parameter:
            duty (float): Normierter Duty-Wert.
            strikt (bool): Bereich 0.233 bis 0.900 wenn True.
            clampen (bool): Optionales Begrenzen statt Fehler.

        Rueckgabewert:
            float: Gepruefter Duty-Wert.

        Seiteneffekte:
            Keine.
        """
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")

        duty_normiert = duty

        if duty_normiert < 0.0 or duty_normiert > 1.0:
            raise ValueError("duty ausserhalb des normierten Bereichs 0.0 bis 1.0")

        grenze_min = self.DUTY_MIN_NORM if strikt else 0.0
        grenze_max = self.DUTY_MAX_NORM if strikt else 1.0

        if clampen:
            if duty_normiert < grenze_min:
                duty_normiert = grenze_min
            if duty_normiert > grenze_max:
                duty_normiert = grenze_max
            return duty_normiert

        if duty_normiert < grenze_min or duty_normiert > grenze_max:
            if strikt:
                raise ValueError("duty ausserhalb des Sensorbereichs 0.233 bis 0.90")
            raise ValueError("duty ausserhalb des erlaubten Bereichs")

        return duty_normiert
