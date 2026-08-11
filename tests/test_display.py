"""CPython-Importtest fuer die reine Darstellungslogik."""


def test_display_importiert_ohne_hardware():
    import display
    assert display.DISPLAY_BREITE == 128
    assert display.DISPLAY_HOEHE == 64
    assert display.DisplayHelper.max_chars() == 16
