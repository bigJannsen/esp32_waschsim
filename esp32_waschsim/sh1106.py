# MicroPython SH1106 OLED driver for 128x64 I2C displays.
# FrameBuffer-compatible interface matching the methods used by DisplayManager.

import framebuf


class SH1106_I2C(framebuf.FrameBuffer):
    """Minimal SH1106 I2C driver for 128x64 monochrome OLEDs."""

    def __init__(self, width, height, i2c, addr=0x3C, rotate=0):
        self.width = width
        self.height = height
        self.pages = height // 8
        self.i2c = i2c
        self.addr = addr
        self.buffer = bytearray(width * self.pages)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._rotate = bool(rotate)
        self.init_display()

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes((0x80, cmd)))

    def init_display(self):
        commands = (
            0xAE,       # display off
            0xD5, 0x80, # display clock
            0xA8, self.height - 1,
            0xD3, 0x00, # display offset
            0x40,       # start line
            0xAD, 0x8B, # DC-DC on
            0xA1 if not self._rotate else 0xA0,
            0xC8 if not self._rotate else 0xC0,
            0xDA, 0x12,
            0x81, 0x7F, # contrast
            0xD9, 0x22,
            0xDB, 0x35,
            0xA4,       # RAM contents
            0xA6,       # normal display
            0xAF,       # display on
        )
        for cmd in commands:
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(0xAE)

    def poweron(self):
        self.write_cmd(0xAF)

    def contrast(self, contrast):
        self.write_cmd(0x81)
        self.write_cmd(contrast & 0xFF)

    def invert(self, invert):
        self.write_cmd(0xA7 if invert else 0xA6)

    def show(self):
        # SH1106 has 132 columns. Typical 128px modules start at column 2.
        column_offset = 2
        for page in range(self.pages):
            self.write_cmd(0xB0 | page)
            self.write_cmd(0x00 | (column_offset & 0x0F))
            self.write_cmd(0x10 | (column_offset >> 4))
            start = self.width * page
            end = start + self.width
            self.i2c.writeto(self.addr, b"\x40" + self.buffer[start:end])
