# output_driver.py
# Übergibt logische Werte an die Hardware-Abstraktion


class OutputDriver:

    def __init__(self, hardware):
        self.hardware = hardware

    def set_code(self, code):

        bitmaske = self.code_zu_bitmaske(code)
        self.hardware.setze_bitmaske(bitmaske)

    def code_zu_bitmaske(self, code):

        # einfache 1:1 Abbildung (8 Bit)
        return code & 0xFF