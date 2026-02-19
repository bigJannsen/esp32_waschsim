# hardware.py
# Hardware-Abstraktionsschicht (derzeit nur Testausgabe)


class HardwareAbstraktion:

    def __init__(self):
        print("Hardware initialisiert")

    def setze_bitmaske(self, bitmaske):

        print("Bitmaske gesetzt:", bitmaske)
        print("Binär:", format(bitmaske, "08b"))