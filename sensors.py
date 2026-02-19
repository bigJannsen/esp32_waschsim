# sensors.py
# Enthält fachliche Sensormodelle (keine Hardwarezugriffe)

import math


class NtcSensor:

    def __init__(self, output_driver, lsb_ohm=250, max_code=255):
        self.output_driver = output_driver
        self.lsb_ohm = lsb_ohm
        self.max_code = max_code

        self.kennlinie = [
            (0, 38000),
            (5, 29700),
            (10, 23400),
            (15, 18600),
            (20, 14900),
            (25, 12000),
            (30, 9730),
            (35, 7960),
            (40, 6550),
            (45, 5420),
            (50, 4520),
            (55, 3780),
            (60, 3190),
            (65, 2700),
            (70, 2290),
            (75, 1960),
            (80, 1680),
            (85, 1450),
            (90, 1250),
            (95, 1150),
            (100, 1090),
        ]

    def berechne_widerstand_ohm(self, temperatur_c):

        if temperatur_c < self.kennlinie[0][0]:
            t0, r0 = self.kennlinie[0]
            t1, r1 = self.kennlinie[1]

        elif temperatur_c > self.kennlinie[-1][0]:
            t0, r0 = self.kennlinie[-2]
            t1, r1 = self.kennlinie[-1]

        else:
            for i in range(len(self.kennlinie) - 1):
                t0, r0 = self.kennlinie[i]
                t1, r1 = self.kennlinie[i + 1]

                if t0 <= temperatur_c <= t1:
                    break

        anteil = (temperatur_c - t0) / (t1 - t0)
        widerstand_ohm = r0 + anteil * (r1 - r0)

        return widerstand_ohm

    def quantisiere_widerstand(self, widerstand_ohm):

        schritte = math.ceil(widerstand_ohm / self.lsb_ohm)

        if schritte > self.max_code:
            schritte = self.max_code

        if schritte < 0:
            schritte = 0

        return int(schritte)

    def verarbeite_temperatur(self, temperatur_c):

        widerstand_ohm = self.berechne_widerstand_ohm(temperatur_c)
        code = self.quantisiere_widerstand(widerstand_ohm)

        self.output_driver.set_code(code)