"""Hardwarefreier physikalischer Kern fuer MicroPython/ESP32.

Modellannahmen, KEINE verifizierten PWM-908-Herstellerdaten:
    Liegender Zylinder: Innendurchmesser 600 mm, Innenlaenge 400 mm.
    3 l effektive Materialverdraengung bei voll gefuelltem Zylinder,
    gleichmaessig ueber dessen Querschnitt verteilt (konstante Porositaet).
    Die perforierte Trommel ist wasserdurchlaessig. Ihre angegebenen 73 l
    werden weder als Behaeltervolumen noch als Verdraengung verwendet.
    Zulauf 10 l/min bei 15 Grad C, Ablauf 20 l/min, Heizung 5000 W,
    Umgebung 20 Grad C, Verlustleitwert 8 W/K, Behaelterkapazitaet 10000 J/K,
    Druckanschluss am Zylinderboden. Alle diese Werte sind vorlaeufig.

Vereinfachungen:
    Wasser und thermisch wirksame Einbauten haben dieselbe Temperatur.
    Keine eigene Heizungszeitkonstante, Waescheaufnahme, Sumpf-/Rohrvolumina,
    Schaumbildung, Verdampfung oder temperaturabhaengigen Stoffwerte.
    Stoffwerte: Wasser 1 kg/l, c_p = 4180 J/(kg K), g = 9.81 m/s^2.
    Ein voller Behaelter laesst ueberschuessigen Zulauf als idealen Ueberlauf
    mit Mischtemperatur ablaufen. Das beschreibt keine reale Ueberlaufleitung.
    Bei leerem Behaelter wird Heizleistung ignoriert, auch ohne reale
    Verriegelung. Die endliche Behaelterkapazitaet speichert Restwaerme;
    'temperatur_c' ist dann die Temperatur dieser Einbauten. Zulauf kann
    diese Restwaerme aufnehmen, auch bei gleichzeitig trocken laufender Pumpe.
    0..100 Grad C begrenzen das Modell passend zum vorhandenen NTC-Bereich.
    An den Temperaturgrenzen wird Restenergie verworfen, kein Sieden/Gefrieren
    modelliert. 'temperatur_begrenzt' zeigt dies fuer den letzten Aufruf an.

Spaetere Integration (hier keine Imports anderer Firmwaremodule):
    main.py: Instanz neben den Sensoren erzeugen; eigene uasyncio-Task etwa
    alle 100 ms. dt = ticks_diff(jetzt, vorher) / 1000.0; Zeitmarke auch nach
    abgelehnten Aufrufen fortschreiben. Keine unbekannten Zeitraeume nachholen.
    Eingangszustaende gelten waehrend dt als konstant; Flanken innerhalb
    eines Intervalls lassen sich aus einem einzelnen Snapshot nicht ableiten.
    hardware.py: bestaetigte Getter ist_friwa_aktiv(), ist_heizung_aktiv(),
    ist_abwasserpumpe_aktiv() als ventil, heizung, pumpe uebergeben. None nicht
    mit bool() in AUS umwandeln. Active-Low und Entprellung bleiben dort.
    sensors.py: temperatur_c an NtcSensor.verarbeite_temperatur() und druck_pa
    an PressureSensor.verarbeite_druck_pa() geben; keine Kennlinien duplizieren.
    Der physikalische Druck kann 2452 Pa ueberschreiten: spaeter explizit
    Fehler-/Saettigungsstrategie fuer den Sensorausgang festlegen. Der Kern
    kappt die physikalische Wasserhoehe nicht auf den PWM-Messbereich.
    Achtung: aktuelle Sensor-Setter speichern geaenderte Werte in config.json.
    Vor 10-Hz-Ausgabe Laufzeitwerte von Flash-Persistenz entkoppeln!
    rest.py: lese_zustand() spaeter unter 'simulation' bereitstellen; Zuordnung
    temperatur_c -> temperature_c, druck_pa -> pressure_pa im Integrationscode.
    Manuelle REST-Vorgaben und Automatik brauchen eine eindeutige Prioritaet.
    display.py kann weiter die ausgegebenen Sensorwerte darstellen.

Ein Sensor-Initialsignal (z.B. 90 mmWS) initialisiert keinen Wasserstand.
Der Anfangszustand ist unabhaengig davon leer. Keine I/O, Zeitquelle oder Task.
"""

from math import atan2, exp, log, pi, sqrt


_WASSERKAPAZITAET_J_L_K = 4180.0
_PA_PRO_MMWS = 9.81  # Projektkonvention, rho = 1000 kg/m^3.


class SimulationManager:
    """Zustandssimulation mit konstantem Speicherbedarf und begrenzter Arbeit.

    Parameter sind ausschliesslich beim Erzeugen konfigurierbar. Alle Zahlen
    muessen endlich sein; bool ist kein Zahlenwert. Bereiche sind technische
    Plausibilitaetsgrenzen dieses Modells, keine Maschinenspezifikation:

    Parameter                            Standard       Bereich/Einheit
    zulauf_l_min                         10.0           0..100 l/min
    ablauf_l_min                         20.0           0..100 l/min
    zulauftemperatur_c                   15.0           0..100 Grad C
    heizleistung_w                       5000.0         0..20000 W
    umgebungstemperatur_c                20.0           0..100 Grad C
    waermeverlust_w_k                    8.0            0..100 W/K
    behaelter_waermekapazitaet_j_k        10000.0        100..1000000 J/K
    behaelter_durchmesser_mm              600.0          100..2000 mm
    behaelter_laenge_mm                   400.0          100..2000 mm
    verdraengung_l                       3.0            0..99% Zylindervolumen l
    druckanschluss_hoehe_mm               0.0            0..Durchmesser mm
    max_dt_s                             5.0            0.1..60 s
    start_volumen_l                      0.0            0..Nutzkapazitaet l
    start_temperatur_c                   None           Umgebung, sonst 0..100 C

    aktualisieren() liefert bool, lese_zustand() einen Snapshot. Konfigurations-
    und Resetfehler werfen ValueError; ungueltige Laufzeiteingaenge melden
    False plus fehler, ohne physikalische Aenderungen. Gueltiger Folgeaufruf
    loescht den Fehler. dt=0 ist erlaubt, aendert nur Eingangs-/Diagnosestatus.
    dt>max_dt_s wird komplett abgelehnt, niemals still gekuerzt.
    """

    def __init__(
        self,
        zulauf_l_min=10.0,
        ablauf_l_min=20.0,
        zulauftemperatur_c=15.0,
        heizleistung_w=5000.0,
        umgebungstemperatur_c=20.0,
        waermeverlust_w_k=8.0,
        behaelter_waermekapazitaet_j_k=10000.0,
        behaelter_durchmesser_mm=600.0,
        behaelter_laenge_mm=400.0,
        verdraengung_l=3.0,
        druckanschluss_hoehe_mm=0.0,
        max_dt_s=5.0,
        start_volumen_l=0.0,
        start_temperatur_c=None,
    ):
        self._zulauf_l_s = self._zahl(zulauf_l_min, "zulauf_l_min", 0.0, 100.0) / 60.0
        self._ablauf_l_s = self._zahl(ablauf_l_min, "ablauf_l_min", 0.0, 100.0) / 60.0
        self._zulauftemperatur_c = self._zahl(
            zulauftemperatur_c, "zulauftemperatur_c", 0.0, 100.0
        )
        self._heizleistung_w = self._zahl(heizleistung_w, "heizleistung_w", 0.0, 20000.0)
        self._umgebungstemperatur_c = self._zahl(
            umgebungstemperatur_c, "umgebungstemperatur_c", 0.0, 100.0
        )
        self._verlust_w_k = self._zahl(waermeverlust_w_k, "waermeverlust_w_k", 0.0, 100.0)
        self._behaelterkapazitaet_j_k = self._zahl(
            behaelter_waermekapazitaet_j_k, "behaelter_waermekapazitaet_j_k",
            100.0, 1000000.0,
        )
        self._durchmesser_mm = self._zahl(
            behaelter_durchmesser_mm, "behaelter_durchmesser_mm", 100.0, 2000.0
        )
        laenge_mm = self._zahl(behaelter_laenge_mm, "behaelter_laenge_mm", 100.0, 2000.0)
        zylinder_l = pi * (self._durchmesser_mm * 0.5) ** 2 * laenge_mm / 1000000.0
        verdraengung_l = self._zahl(verdraengung_l, "verdraengung_l", 0.0, zylinder_l)
        self._kapazitaet_l = zylinder_l - verdraengung_l
        # Auch auf Float32 sinnvollen Abstand zu vollstaendiger Verdraengung halten.
        if self._kapazitaet_l < 0.01 * zylinder_l:
            raise ValueError("mindestens 1 Prozent des Zylinders muss Wasserraum bleiben")
        self._druckanschluss_mm = self._zahl(
            druckanschluss_hoehe_mm, "druckanschluss_hoehe_mm", 0.0, self._durchmesser_mm
        )
        self._max_dt_s = self._zahl(max_dt_s, "max_dt_s", 0.1, 60.0)
        self.zuruecksetzen(start_volumen_l, start_temperatur_c)

    @staticmethod
    def _im_bereich(wert, minimum, maximum):
        # Geschlossener Bereichstest lehnt auch NaN und +/-Inf ab, ohne isfinite.
        return (not isinstance(wert, bool) and isinstance(wert, (int, float))
                and minimum <= wert <= maximum)

    @classmethod
    def _zahl(cls, wert, name, minimum, maximum):
        if not cls._im_bereich(wert, minimum, maximum):
            raise ValueError(name + ": ungueltiger Zahlenwert oder Bereich")
        return float(wert)

    def zuruecksetzen(self, wasservolumen_l=0.0, temperatur_c=None):
        """Setzt Wasser/Thermik, Eingaenge auf AUS und Diagnosen zurueck.

        Ohne Temperaturangabe gilt die konfigurierte Umgebungstemperatur.
        Erst beide Werte validieren: ein ungueltiger Reset veraendert nichts.
        """
        volumen = self._zahl(wasservolumen_l, "wasservolumen_l", 0.0, self._kapazitaet_l)
        if temperatur_c is None:
            temperatur_c = self._umgebungstemperatur_c
        temperatur = self._zahl(temperatur_c, "temperatur_c", 0.0, 100.0)
        self._volumen_l = volumen
        self._temperatur_c = temperatur
        self._ventil = False
        self._heizung = False
        self._pumpe = False
        self._fehler = None
        self._ueberlauf_l = 0.0
        self._trockenheizung_ignoriert = False
        self._temperatur_begrenzt = False
        self._letztes_dt_s = 0.0

    def aktualisieren(self, dt, ventil, heizung, pumpe):
        """Berechnet genau dt Sekunden mit drei konstanten bool-Eingaengen.

        Bei Fehler bleiben auch die zuletzt akzeptierten Eingaenge/Diagnosen
        erhalten; nur fehler aendert sich. Keine Rohwerte unbekannter Typen
        speichern: lese_zustand() bleibt JSON-kompatibel.

        V' = q_ein - q_aus. An leer/voll wird der tatsaechliche Ablauf auf
        Zulauf bzw. Pumpenfluss plus Ueberlauf begrenzt. Maximal zwei analytische
        thermische Phasen, keine Zeitschritt-Schleife und keine Wartefunktion.
        """
        if not isinstance(ventil, bool):
            self._fehler = "VENTIL_UNGUELTIG: bool erforderlich"
            return False
        if not isinstance(heizung, bool):
            self._fehler = "HEIZUNG_UNGUELTIG: bool erforderlich"
            return False
        if not isinstance(pumpe, bool):
            self._fehler = "PUMPE_UNGUELTIG: bool erforderlich"
            return False
        if not self._im_bereich(dt, 0.0, self._max_dt_s):
            self._fehler = "DT_UNGUELTIG: endliche Sekunden in 0..max_dt_s erforderlich"
            return False

        dt = float(dt)
        zulauf = self._zulauf_l_s if ventil else 0.0
        ablauf = self._ablauf_l_s if pumpe else 0.0
        netto = zulauf - ablauf
        volumen = self._volumen_l
        endvolumen = volumen + netto * dt
        phase_s = dt
        if endvolumen > self._kapazitaet_l:
            phase_s = (self._kapazitaet_l - volumen) / netto
            endvolumen = self._kapazitaet_l
        elif endvolumen < 0.0:
            phase_s = -volumen / netto
            endvolumen = 0.0
        # Rundung an der Grenze darf keine negative zweite Phase erzeugen.
        phase_s = max(0.0, min(dt, phase_s))
        rest_s = dt - phase_s
        temperatur = self._temperatur_c
        begrenzt = False
        trocken = False

        if phase_s > 0.0:
            nass = volumen > 0.0 or endvolumen > 0.0
            leistung = self._heizleistung_w if heizung and nass else 0.0
            trocken = heizung and not nass
            temperatur = self._temperatur_nach_phase(
                phase_s, volumen, endvolumen, zulauf, leistung, temperatur
            )
            begrenzt = temperatur < 0.0 or temperatur > 100.0
            temperatur = max(0.0, min(100.0, temperatur))

        if rest_s > 0.0:
            nass = endvolumen > 0.0
            leistung = self._heizleistung_w if heizung and nass else 0.0
            trocken = trocken or (heizung and not nass)
            temperatur = self._temperatur_nach_phase(
                rest_s, endvolumen, endvolumen, zulauf, leistung, temperatur
            )
            begrenzt = begrenzt or temperatur < 0.0 or temperatur > 100.0
            temperatur = max(0.0, min(100.0, temperatur))

        self._volumen_l = endvolumen
        self._temperatur_c = temperatur
        self._ventil = ventil
        self._heizung = heizung
        self._pumpe = pumpe
        self._fehler = None
        self._ueberlauf_l = netto * rest_s if netto > 0.0 else 0.0
        self._trockenheizung_ignoriert = trocken
        self._temperatur_begrenzt = begrenzt
        self._letztes_dt_s = dt
        return True

    def _temperatur_nach_phase(self, dt, v0, v1, zulauf, leistung, temperatur):
        """Exakte Loesung der linearen Energiebilanz innerhalb einer Phase.

        C = C_behaelter + c*V; c in J/(l K), Fluesse in l/s.
        d(C*T)/dt = P + c*q_ein*T_ein - c*q_aus*T - UA*(T-T_a).
        Mit C' = c*(q_ein-q_aus) folgt:
        C*T' = P + c*q_ein*(T_ein-T) + UA*(T_a-T).
        Ablauf entzieht also Energie UND Masse mit derselben Mischtemperatur.
        I = Integral(dt/C); B = c*q_ein + UA.
        Delta T = (P+c*q_ein*(T_ein-T0)+UA*(T_a-T0))*I*phi(B*I),
        phi(z) = (1-exp(-z))/z. Kein Quotient durch Wasservolumen.
        """
        c0 = self._behaelterkapazitaet_j_k + _WASSERKAPAZITAET_J_L_K * v0
        x = _WASSERKAPAZITAET_J_L_K * (v1 - v0) / c0
        if abs(x) < 0.001:
            # log(1+x)/x, stetig auch fuer konstanten Fuellstand x=0.
            faktor = 1.0 + x * (-0.5 + x * (1.0 / 3.0 - x * 0.25))
        else:
            # Bei fast vollstaendigem Leeren ist 1+x auf Float32 ungenau.
            c1 = self._behaelterkapazitaet_j_k + _WASSERKAPAZITAET_J_L_K * v1
            faktor = log(c1 / c0) / x
        integral = dt / c0 * faktor
        mischung_w_k = _WASSERKAPAZITAET_J_L_K * zulauf
        b = mischung_w_k + self._verlust_w_k
        quelle_w = (leistung + mischung_w_k * (self._zulauftemperatur_c - temperatur)
                    + self._verlust_w_k * (self._umgebungstemperatur_c - temperatur))
        z = b * integral
        if z < 0.001:
            phi = 1.0 + z * (-0.5 + z * (1.0 / 6.0 - z / 24.0))
            return temperatur + quelle_w * integral * phi
        # Diese Form vermeidet grosse Zwischenprodukte bei sehr kleinem C.
        return temperatur + (quelle_w / b) * (1.0 - exp(-z))

    def _wasserhoehe_mm(self):
        """Invertiert Kreisabschnittsvolumen mit 20 begrenzten Bisektionsschritten.

        Homogene Materialverteilung: V(h) = Nutzkapazitaet*A(h)/(pi*r^2).
        Spiegelung an halber Hoehe vermeidet Ausloeschung am oberen Rand.
        Winkel ueber atan2 statt acos(1-h/r), stabil auch nahe leer.
        Fehler der Bisektion maximal Durchmesser/2^21, zzgl. Float-Rundung
        und Reihennaeherung fuer kleine Winkel.
        Keine Lookup-Tabelle oder dynamische Liste.
        """
        if self._volumen_l <= 0.0:
            return 0.0
        if self._volumen_l >= self._kapazitaet_l:
            return self._durchmesser_mm
        anteil = self._volumen_l / self._kapazitaet_l
        spiegeln = anteil > 0.5
        if spiegeln:
            anteil = 1.0 - anteil
        unten = 0.0
        oben = 1.0  # Normierte Hoehe h/r in der unteren Zylinderhaelfte.
        for _ in range(20):
            y = (unten + oben) * 0.5
            wurzel = sqrt(y * (2.0 - y))
            winkel = atan2(wurzel, 1.0 - y)
            if winkel < 0.1:
                w2 = winkel * winkel
                segment = winkel * w2 * (2.0 / 3.0 + w2 * (-2.0 / 15.0 + w2 * 4.0 / 315.0))
            else:
                segment = winkel - (1.0 - y) * wurzel
            if segment / pi < anteil:
                unten = y
            else:
                oben = y
        hoehe = (unten + oben) * 0.25 * self._durchmesser_mm
        return self._durchmesser_mm - hoehe if spiegeln else hoehe

    def lese_zustand(self, ziel=None):
        """Liefert JSON-faehige Werte; optional vorhandenes dict wiederverwenden.

        Eingaenge und Zusatzdiagnosen gehoeren zum letzten akzeptierten Aufruf,
        fehler zum letzten Versuch. ok=False kennzeichnet einen verworfenen
        Versuch; alter Wasser-/Temperaturzustand bleibt dabei erhalten.
        ueberlauf_l ist nur die Menge des letzten akzeptierten Intervalls.
        druck_mmws ist die Wassersaeule UEBER dem Druckanschluss, kein Offset
        des Sensors; ein trockener Anschluss liefert 0 Pa und 0 mmWS.
        Ein uebergebenes ziel bleibt Eigentum des Aufrufers; fremde Keys bleiben.
        Ohne ziel wird ausschliesslich hier ein neues Snapshot-Dict angelegt.
        """
        if ziel is None:
            ziel = {}
        elif not isinstance(ziel, dict):
            raise ValueError("ziel muss dict oder None sein")
        hoehe = self._wasserhoehe_mm()
        druck_mmws = max(0.0, hoehe - self._druckanschluss_mm)
        ziel["wasservolumen_l"] = self._volumen_l
        ziel["wasserhoehe_mm"] = hoehe
        ziel["druck_mmws"] = druck_mmws
        ziel["druck_pa"] = druck_mmws * _PA_PRO_MMWS
        ziel["temperatur_c"] = self._temperatur_c
        ziel["ventil"] = self._ventil
        ziel["heizung"] = self._heizung
        ziel["pumpe"] = self._pumpe
        ziel["ok"] = self._fehler is None
        ziel["fehler"] = self._fehler
        ziel["kapazitaet_l"] = self._kapazitaet_l
        ziel["leer"] = self._volumen_l <= 0.0
        ziel["voll"] = self._volumen_l >= self._kapazitaet_l
        ziel["ueberlauf_l"] = self._ueberlauf_l
        ziel["trockenheizung_ignoriert"] = self._trockenheizung_ignoriert
        ziel["temperatur_begrenzt"] = self._temperatur_begrenzt
        ziel["letztes_dt_s"] = self._letztes_dt_s
        return ziel
