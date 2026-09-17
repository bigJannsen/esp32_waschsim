# Display compatibility shim for the SH1106 test branch.
#
# hardware.py currently imports SSD1306_I2C directly. On this branch we keep
# hardware.py untouched and map that interface to the SH1106 driver so the
# 1.30-inch I2C OLED can be tested immediately.
#
# This branch is intentionally SH1106-specific. main remains unchanged and
# continues to use the original SSD1306 driver.

from sh1106 import SH1106_I2C


SSD1306_I2C = SH1106_I2C
