# Netzwerk: Bestand und manueller ESP32-Smoke-Test

## Charakterisierung des bewaehrten AP-Pfads vor der Auslagerung

Der vor dieser Aenderung in `main.py` enthaltene und auf ESP32-Hardware bereits
erprobte Pfad hatte folgende Eigenschaften:

- Interface: `network.WLAN(network.AP_IF)`, einmal im Konstruktor erzeugt.
- Aktivierung: zuerst `active(True)`, danach AP-Konfiguration.
- Authmode: zuerst `network.AUTH_WPA2_PSK`, ersatzweise
  `network.AUTH_WPA_WPA2_PSK`, andernfalls Konfiguration ohne `authmode`.
- ESSID: `miele`.
- Passwort: `10000000`.
- IP-Ermittlung: `ifconfig()` und erstes Element der Rueckgabe.
- Warteverhalten: maximal 20 Polls auf `active()` mit jeweils 50 ms
  `uasyncio.sleep_ms`; keine Endlosschleife.
- Exception-Verhalten: beliebige Exception fuehrte zum sicheren
  Hardwarezustand und wurde als Fehler beim WLAN-AP-Start weitergereicht.
- REST-Start: `_starte_server_async()` wurde ausschliesslich nach erfolgreicher
  Rueckkehr des AP-Starts aufgerufen.

Der neue `legacy_ap`-Standardpfad behaelt insbesondere die Reihenfolge
`active(True)`, `config(...)`, begrenztes Polling und `ifconfig()` bei. Die
Netzwerkparameter sind nun zentral in `network_manager.py` definiert.

## Manueller Smoke-Test auf realer ESP32-Zielhardware

## Digitaleingänge: Entprellung und Pumpenkontakt

Diese Prüfungen erfordern reale Zielhardware und wurden durch lokale Mocktests
nicht ersetzt. GPIO27 (Heizung), GPIO26 (FriWa) und GPIO33 (Abwasserpumpe)
ausschließlich über potentialfreie Kontakte gegen GND schalten. Auf der
ESP32-Seite keine 230 V oder Fremdspannung anlegen. Pumpenaktivität bedeutet
elektrische Ansteuerung und belegt keinen Wasserfluss.

1. Mit offenen Kontakten booten. Nach mindestens 200 ms regelmäßiger Abtastung
   müssen alle drei `hardware.*_aktiv`-Felder unter `GET /api/v1/status` `false`
   sein und `eingangs_fehler` leer. Bis zur ersten Stabilisierung ist `null`
   vorgesehen.
2. Jeden Kontakt einzeln mindestens 200 ms schließen und anschließend
   mindestens 200 ms öffnen. Nur das jeweilige Feld darf auf `true` bzw.
   `false` wechseln. Wegen Abtastraster und REST-Latenz kann die Beobachtung
   später erfolgen; sie darf niemals vor Ablauf des Stabilitätsfensters erfolgen.
3. Mit einem potentialfreien Testsignal jeweils 100-ms-EIN- und AUS-Impulse
   erzeugen. Der zuvor bestätigte Zustand darf nicht wechseln. Zeitfenster
   mit geeignetem Messgerät kontrollieren, nicht nach Handgefühl beurteilen.
4. Wiederholtes Prellen unterhalb 200 ms erzeugen; erst nach dem letzten
   beobachteten Wechsel und mindestens 200 ms Stabilität darf der neue Zustand
   erscheinen. Drei Kontakte zeitlich versetzt schalten und Unabhängigkeit prüfen.
5. OLED abstecken, neu starten und dieselben REST-Prüfungen wiederholen.
   Legacy-AP sowie STA-Verbindungsversuch/AP-Fallback prüfen; die Abtastung
   muss auch während des WLAN-Starts laufen.
6. Abtastabstände unter REST-Last, Displayupdates und Persistenzschreibzugriffen
   mit temporärer Messinstrumentierung auf dem Testgerät prüfen. Bei einer
   verzögerten Abtastung mit gleichem Rohpegel muss das laufende Zeitfenster
   erhalten bleiben; nach mindestens 200 ms seit der ersten Beobachtung darf
   der Zustand übernommen werden. Nur ein erkannter Rohsignalwechsel beginnt
   das Zeitfenster neu. Wechsel zwischen Abtastungen bleiben möglicherweise
   unerkannt, auch bei gleichen Pegeln vor und nach einer Verzögerung; eine
   lückenlose physische Stabilität kann damit nicht nachgewiesen werden.
7. Auf dem Testgerät kontrolliert einen Pininitialisierungs- bzw. Lesefehler
   injizieren. Betroffener Zustand muss `null` und die Diagnose sichtbar sein;
   andere Kontakte, REST und Sensorausgänge müssen weiter funktionieren.
   Nach erfolgreicher Lesung erneut die volle 200-ms-Stabilisierung prüfen.
   Ein offener oder abgezogener Relaiskontakt wird wegen Pull-up regulär AUS
   und ist keine Erkennung eines Leitungsbruchs.

Zusätzlich bestehende OLED-, NTC-, Druck-/PWM- und Netzwerktests wiederholen.
Ergebnisse und gemessene Verzögerungen protokollieren.

Vor den Tests `NETWORK_MODE = "auto"` nur temporaer auf dem Testgeraet setzen.

## OLED-UI-Smoke-Tests auf realer ESP32-Zielhardware

Der Repository-Default `NETWORK_MODE = "legacy_ap"` bleibt fuer diese Tests unveraendert.

### TEST UI-A – Boot
1. Startscreen (`Miele & Cie.KG`, `ESP-Waschsim`, `GTG/RD`) pruefen.
2. Sichtdauer von ungefaehr 5 Sekunden und anschliessend korrekten Netzwerkzustand pruefen.

### TEST UI-B – Legacy-AP
1. Pruefen, dass der AP weiterhin startet und die AP-Anzeige sichtbar wird.
2. `GET /api/v1/health` ueber den AP auf Erreichbarkeit pruefen.

### TEST UI-C – Temperatur
1. Temperatur per PUT fuer same, separate und beide Einzelkanaele setzen.
2. Korrekte T1-/T2-Werte auf der NTC-Seite und Rueckkehr zur Basis nach 10 Sekunden pruefen.

### TEST UI-D – Druck
1. Druck per PUT setzen und Pa sowie mmWS auf der Druckseite vergleichen.
2. Rueckkehr zur Basis nach 10 Sekunden pruefen.

### TEST UI-E – Status
1. `GET /api/v1/status` abrufen und Statusseite pruefen.
2. Rueckkehr zur Basis nach 15 Sekunden pruefen.

### TEST UI-F – Optionales Display
1. OLED abstecken beziehungsweise seine Initialisierung gezielt fehlschlagen lassen.
2. Pruefen, dass Netzwerk startet und REST einschliesslich `/health` erreichbar bleibt.

Diese Punkte sind ein manueller Plan; in dieser Entwicklungsumgebung wurde keine
ESP32-Hardwarevalidierung von OLED oder Auto-WLAN durchgefuehrt.
Der Repository-Default bleibt bis zum vollstaendigen Hardware-Nachweis
`legacy_ap`.

### Test A - STA erfolgreich

1. Ein bekanntes WLAN erreichbar machen und gueltige STA-Daten konfigurieren.
2. ESP32 booten.
3. Serielle Ausgabe auf erfolgreiche STA-Verbindung pruefen.
4. Ausgegebene IP notieren.
5. `GET http://<STA-IP>:8080/api/v1/health` senden.
6. HTTP 200 und `ok: true` bestaetigen.

### Test B - AP-Fallback

1. STA-SSID absichtlich unerreichbar oder falsch konfigurieren.
2. ESP32 booten und den konfigurierten Timeout abwarten.
3. Pruefen, dass der AP `miele` sichtbar wird.
4. Mit dem AP verbinden und die AP-IP pruefen.
5. `GET http://<AP-IP>:8080/api/v1/health` senden.
6. HTTP 200 und `ok: true` bestaetigen.

### Test C - Neustart

1. AP-Fallback aktiv lassen.
2. ESP32 resetten.
3. Pruefen, ob der AP erneut zuverlaessig erscheint und Health erreichbar ist.

### Test D - Rueckkehr zum funktionierenden WLAN

1. Wieder eine gueltige STA-Konfiguration eintragen.
2. ESP32 resetten.
3. STA-Verbindung, ausgegebene IP und Health-Endpunkt erneut pruefen.

Erst wenn A bis D auf der Zielhardware erfolgreich protokolliert wurden, kann
`auto` als produktiver Default bewertet werden. Lokale Mock-Tests liefern keine
Hardwaregarantie.
