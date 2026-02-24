"""Hardware-nahe Abstraktionsschicht mit austauschbaren Backends."""


class _MockBackend:
    """Simuliertes Hardware-Backend ohne externe Abhaengigkeiten.

    Verantwortlichkeit:
    - Speichern der zuletzt gesetzten Hardwarewerte fuer Diagnosen.

    Abgrenzung:
    - Keine Sensorphysik, keine Netzwerklogik, keine echte Peripherie.
    """

    def __init__(self):
        """Erzeugt den initialen Mock-Zustand."""
        self.letzte_bitmaske = 0
        self.letztes_pwm_duty = 0.0

    def setze_bitmaske(self, bitmaske):
        """Speichert die Bitmaske im Mock-Zustand."""
        self.letzte_bitmaske = bitmaske

    def setze_pwm_duty(self, duty):
        """Speichert den PWM-Duty im Mock-Zustand."""
        self.letztes_pwm_duty = duty


class _RealBackend:
    """Optionales Hardware-Backend fuer echte Peripherieobjekte.

    Verantwortlichkeit:
    - Delegation an von aussen bereitgestellte Pin-/PWM-Objekte.

    Abgrenzung:
    - Keine Default-Pins und keine hardcodierten Board-Layouts.
    """

    def __init__(self, **konfiguration):
        """Initialisiert das reale Backend mit externer Konfiguration.

        Parameter:
            **konfiguration: Erwartet optional "bitmaske_setzer" und "pwm_setzer".

        Raises:
            ValueError: Wenn ein uebergebenes Setzer-Objekt nicht aufrufbar ist.
        """
        try:
            __import__("machine")
        except ImportError:
            # Keine harte Abhaengigkeit: Reales Backend kann auch mit Mock-Objekten laufen.
            pass

        self._bitmaske_setzer = konfiguration.get("bitmaske_setzer")
        self._pwm_setzer = konfiguration.get("pwm_setzer")

        if self._bitmaske_setzer is not None and not callable(self._bitmaske_setzer):
            raise ValueError("bitmaske_setzer muss aufrufbar sein")
        if self._pwm_setzer is not None and not callable(self._pwm_setzer):
            raise ValueError("pwm_setzer muss aufrufbar sein")

        self.letzte_bitmaske = 0
        self.letztes_pwm_duty = 0.0

    def setze_bitmaske(self, bitmaske):
        """Delegiert die Bitmaske an die konfigurierte reale Ausgabe."""
        if self._bitmaske_setzer is not None:
            self._bitmaske_setzer(bitmaske)
        self.letzte_bitmaske = bitmaske

    def setze_pwm_duty(self, duty):
        """Delegiert den PWM-Duty an die konfigurierte reale Ausgabe."""
        if self._pwm_setzer is not None:
            self._pwm_setzer(duty)
        self.letztes_pwm_duty = duty


class HardwareAbstraktion:
    """Hardware-nahe Abstraktion fuer Aktor-Ausgaben.

    Verantwortlichkeit:
    - Validierung und Weitergabe von Bitmasken- und PWM-Werten.
    - Bereitstellung eines diagnostischen, nebenwirkungsarmen Status.

    Abgrenzung:
    - Keine Sensorphysik, keine Interpolation, keine REST-/JSON- oder Netzwerklogik.
    """

    def __init__(self, backend="mock", **konfiguration):
        """Erzeugt die HardwareAbstraktion mit Mock- oder Real-Backend.

        Parameter:
            backend (str): "mock" fuer simulationsfaehigen Betrieb oder "real" fuer
                explizit konfigurierten Zugriff auf reale Ausgabeobjekte.
            **konfiguration: Backend-spezifische Konfigurationswerte.

        Raises:
            ValueError: Wenn ein ungueltiger Backend-Name angegeben wird.
        """
        if backend == "mock":
            self._backend = _MockBackend()
        elif backend == "real":
            self._backend = _RealBackend(**konfiguration)
        else:
            raise ValueError("backend muss 'mock' oder 'real' sein")

        self._backend_name = backend

    def initialisiere_hardware(self):
        """Kompatibilitaetsmethode ohne Initialisierungsarbeit.

        Rueckgabe:
            None

        Seiteneffekte:
            Keine. Die Methode bleibt fuer bestehende Aufrufer aus frueheren Stufen erhalten.
        """
        return None

    def konfiguriere_wlan_ap(self, ssid, passwort):
        """Kompatibilitaetsmethode fuer fruehere Stufen ohne WLAN-Implementierung.

        Parameter:
            ssid (str): Wird ignoriert.
            passwort (str): Wird ignoriert.

        Rueckgabe:
            None

        Seiteneffekte:
            Keine.
        """
        _ = (ssid, passwort)
        return None

    def initialisiere_display(self):
        """Kompatibilitaetsmethode fuer fruehere Stufen ohne Display-Implementierung.

        Rueckgabe:
            None

        Seiteneffekte:
            Keine.
        """
        return None

    def setze_bitmaske(self, bitmaske):
        """Setzt eine Ausgabebitmaske mit strikt integerbasierter Validierung.

        Parameter:
            bitmaske (int): Wert im Bereich 0 bis 255.

        Rueckgabe:
            None

        Raises:
            ValueError: Wenn Typ oder Wertebereich ungueltig sind.

        Seiteneffekte:
            Aktualisiert den internen Backend-Zustand bzw. delegiert an reale Setzer.
        """
        if isinstance(bitmaske, bool) or not isinstance(bitmaske, int):
            raise ValueError("bitmaske muss int sein")
        if bitmaske < 0 or bitmaske > 255:
            raise ValueError("bitmaske muss im Bereich 0 bis 255 liegen")
        self._backend.setze_bitmaske(bitmaske)

    def setze_pwm_duty(self, duty):
        """Setzt den normierten PWM-Duty-Wert als float.

        Parameter:
            duty (float): Normierter Wert im Bereich 0.0 bis 1.0.

        Rueckgabe:
            None

        Raises:
            ValueError: Wenn Typ oder Wertebereich ungueltig sind.

        Seiteneffekte:
            Aktualisiert den internen Backend-Zustand bzw. delegiert an reale Setzer.
        """
        if isinstance(duty, bool) or not isinstance(duty, float):
            raise ValueError("duty muss float sein")
        if duty < 0.0 or duty > 1.0:
            raise ValueError("duty muss im Bereich 0.0 bis 1.0 liegen")
        self._backend.setze_pwm_duty(duty)

    def lese_status(self):
        """Liefert den diagnostischen Hardwarestatus ohne I/O.

        Rueckgabe:
            dict: Enthalten sind "backend", "letzte_bitmaske" und "letztes_pwm_duty".

        Seiteneffekte:
            Keine.
        """
        return {
            "backend": self._backend_name,
            "letzte_bitmaske": self._backend.letzte_bitmaske,
            "letztes_pwm_duty": self._backend.letztes_pwm_duty,
        }

    def setze_sicheren_zustand(self):
        """Setzt die Ausgaenge deterministisch auf einen sicheren Zustand.

        Rueckgabe:
            None

        Seiteneffekte:
            Setzt Bitmaske auf 0 und PWM-Duty auf 0.0 ueber die oeffentlichen Methoden.
        """
        self.setze_bitmaske(0)
        self.setze_pwm_duty(0.0)
