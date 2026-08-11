class FakeSSD1306:
    """Nur fuer Tests: zeichnet Text in einen inspizierbaren Frame."""

    def __init__(self):
        self.lines = []
        self.frames = []

    def fill(self, value):
        self.lines = []

    def text(self, value, x, y):
        self.lines.append((str(value), x, y))

    def show(self):
        self.frames.append(list(self.lines))

    def content(self):
        return "\n".join(line[0] for line in self.lines)
