# main.py
# Minimaler Systemtest ohne REST


from sensors import NtcSensor
from output_driver import OutputDriver
from hardware import HardwareAbstraktion


def main():

    hardware = HardwareAbstraktion()
    output_driver = OutputDriver(hardware)
    ntc = NtcSensor(output_driver)

    # Testwert
    # temperatur_test = 45
    ntc.verarbeite_temperatur() # var. von REST in Klammer


if __name__ == "__main__":
    main()