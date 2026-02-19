"""Logische Ausgabeschicht zwischen Sensorlogik und Hardware.

Dieses Modul enthaelt ausschließlich:
- Code-zu-Bitmasken-Abbildung
- Übergabe von normierten PWM-Werten
- Delegation an die Hardware-Abstraktion
"""


class OutputDriver:
    """Sammelt Ausgangswerte und delegiert sie an die Hardware-Schicht."""

    CODE_BITBREITE = 8

    def __init__(self, hardware_abstraktion):
        """Speichert die Hardware-Abstraktion als alleinigen IO-Zugang."""
        self.hardware_abstraktion = hardware_abstraktion

    def setze_ntc_code(self, code):
        """Nimmt einen NTC-Code entgegen und uebergibt die Bitmaske."""
        bitmaske = self.code_zu_bitmaske(code)
        self.hardware_abstraktion.setze_ntc_bitmaske(bitmaske)

    def setze_druck_pwm_normiert(self, pwm_normiert):
        """Uebergibt den normierten PWM-Wert an die Hardware-Schicht."""
        self.hardware_abstraktion.setze_pwm_druckkanal(pwm_normiert)

    def code_zu_bitmaske(self, code):
        """Wandelt einen numerischen Code in eine 8-Bit-Bitmaske um.

        TODO: Finale Abbildungsregeln und Validierung ergaenzen.
        """
        _ = code
        return 0
