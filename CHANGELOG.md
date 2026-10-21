# V0.3-Beta4 (0.3.0b4)

- Unterer 7,5-kW-Heizstab mit Stunden-/Minuten-Zahlenrädern, Start, Stopp und Restzeit.
- Unabhängiger Timer, gleichzeitiger Betrieb beider Heizstäbe erlaubt, keine Sperrzeit unten.
- Unterer Heizstab und Beschriftung werden bei bestätigter Rückmeldung grün.
- Einheitliche Spalten für Temperatur, Stellwert und Automatik in allen Gerätezeilen.
- Einheitlichere Zeitfelder und Checkboxen; feste Spalte für Plus ohne Überlappung.
- 82 simulierte Backend-Tests bestanden; Timer-Recovery und Abschaltfehler geprüft.

# V0.3-Beta2 (0.3.0b2)

- PyLoxone-Temperatursensoren mit Einheit „°“ werden als Celsius übernommen.
- Regression mit den gemeldeten Werten 36.5625 und 27.8125 geprüft; 74 Tests bestanden.

# V0.3-Beta1 (0.3.0b1)

- Neuer Brauchwasser Regler mit PyLoxone-Entitäten für Temperaturen und getrennte Relaisrückmeldungen.
- Nur oberer 4-kW-Heizstab wird geregelt. Untere Temperatur und Relaisstatus werden angezeigt; der untere 7,5-kW-Heizstab wird nicht geschaltet.
- Einstellbare Zieltemperatur und absolute Wiedereinschalttemperatur. Sperrzeit ab bestätigtem Ausschalten, auch nach externem Ausschalten; Speicherung über Neustarts.
- Legionellenprogramm nach Wochentagen und Zeit von/bis, ohne vorbelegte Uhrzeit. Hält die obere Zieltemperatur mit derselben Schaltdifferenz, Sperrzeit bleibt vorrangig. Zirkulation während des gesamten Zeitfensters optional.
- Zirkulations-Zeitfenster mit jeweils eigenen ausgeschriebenen Wochentagen Montag–Sonntag, grünes Plus und rotes Minus ab dem zweiten Fenster. Entfernen erst nach Ja/Nein-Bestätigung.
- Ungültige obere Temperatur oder fehlende erforderliche Rückmeldung: Automatik aus, Ausschaltbefehle an oberen Heizstab und Pumpe; kein selbstständiger Wiederanlauf. Schaltbefehle werden auf Loxone-Rückmeldung geprüft.
- Beim Start kein Schaltbefehl, Automatik ausgeschaltet. Vor erster Aktivierung sind gültige Zieltemperatur, Wiedereinschalttemperatur und Sperrzeit zu speichern.
- Gemeinsamer Schiebeschalter auch beim aufgeklappten Miner-Regler.
- Boilerbild ist ausdrücklich für später vorgesehen; Platzhalter links, Einstellungen rechts.
- 74 Backend-Tests und bestehende UI-Verhaltenstests bestanden. Browser-Vorschau prüft Zeitfenster, Entfernen mit Ja/Nein, Formularwerte und mobile 390-Pixel-Ansicht. Keine Schaltbefehle an echte Geräte gesendet; kein HA-Hardwaretest.

# V0.2 (0.2.0) – 15.10.2026

- Der vom Anwender bestätigte funktionierende Stand V0.2-Beta3 wird als stabile Version veröffentlicht.
- Keine funktionalen Änderungen gegenüber Beta3. Versionsnummer und Oberflächenkennung auf den stabilen Stand gesetzt.
- Enthält Miner-Grundwasserregelung und unabhängige Modbus-Lüfterregler mit UDP-Ausgabe an Loxone.
- Geräteanlage über Home Assistant, automatische Übernahme bestehender Beta1-Lüfter, konfigurierbare Spannungsgrenzen und Schnellreaktion.
- Einheitliche einklappbare Geräteansichten, breite Diagramme mit 15-Minuten-/1-/6-/24-Stunden-Auswahl und geordnete Regler-Einstellungen.

# V0.2-Beta3 (0.2.0b3)

- Lüfter-Regler-Einstellungen wie beim Miner: Temperaturgrenzen, Schrittweite, Pause und Messwertgültigkeit zuerst.
- Eigener Abschnitt Schnellreaktion mit Anstieg, größerem Spannungsschritt, Schaltern und Anzeige der letzten Schnellreaktion.
- Spannungsgrenzen und Ausschaltverhalten bleiben als zusätzlicher offener Abschnitt verfügbar.
- Lüftername sowie ESP32- und Loxone-Verbindung in einem separaten, standardmäßig eingeklappten Abschnitt darunter.
- Beide Speichern-Schaltflächen übernehmen alle bearbeiteten Einstellungen des Lüfters. Bestehende Reglerwerte und Verbindungen bleiben erhalten.
- UI-Verhaltenstest und Browser-Vorschau mit simulierten Daten geprüft: Speichern bei eingeklappter Verbindung erhält IP und Mindestspannung. Keine Änderung an Regelalgorithmus oder Modbus.

# V0.2-Beta2 (0.2.0b2)

- Geräteanlage über Einstellungen → Geräte & Dienste → Michi´s Steuerung → Gerät hinzufügen, mit Gerätetyp-Auswahl.
- Vorhandene Beta1-Lüfter werden automatisch in eigene Home-Assistant-Konfigurationseinträge übernommen. Jeder Lüfter speichert seine Einstellungen separat und kann einzeln neu geladen, deaktiviert oder entfernt werden.
- Hinzufügen-Formular aus der Bedienübersicht entfernt.
- Gleiche Spalten für Miner und Lüfter; Schalterbreite gegen Schrumpfen abgesichert, damit der Schaltknopf nicht aus seiner Fläche rutscht.
- Diagramm und darunter offen sichtbare Regler-Einstellungen über die volle Breite bei beiden Gerätetypen.
- Diagrammzeitraum 15 Minuten / 1 Stunde / 6 Stunden / 24 Stunden, jeweils getrennt wählbar. Bis 24 Stunden Messwerte im Arbeitsspeicher seit Start; keine erfundene Vergangenheit und keine Speicherung über Neustarts.
- Breite Zeichenfläche statt festem schmalem Seitenverhältnis; Temperatur- und Stellwertspitzen sowie Messlücken bleiben bei der Datenreduktion erhalten.
- 58 Backend-Prüfungen und bestehende UI-Verhaltenstests bestanden. Browser-Vorschau mit simulierten Daten: gleiche Ausrichtung, Schalter ein/aus, Zeitwahl und 390-Pixel-Ansicht ohne seitlichen Überlauf geprüft. Keine Prüfung in echtem Home Assistant/ESP32/Loxone.

# Änderungen

## V0.2-Beta1 (0.2.0b1)

- Frei benennbare, unabhängige Lüfterbausteine zusätzlich zum Miner-Regler.
- ESP32 DHT22 Klima 1.0.2 via Modbus TCP: Temperatur, Feuchte und Gültigkeit; Abfrage alle 5 Sekunden.
- Einstellbare Spannungsgrenzen (Standard 2–10 V), 27–28 °C und 120 Sekunden Wartezeit.
- Einstellbares Verhalten bei Automatik aus: Mindestspannung, letzter Wert oder 0 V.
- Pro Lüfter eigenes UDP-Ziel, Port und Befehlspräfix; doppelte Ziele mit identischem Präfix werden verhindert.
- Gespeicherte Einstellungen und Stellwerte; nach Neustart Automatik aus, kein automatisches Senden.
- Gewähltes M-Icon als lokale HA-Brandbilder.
- Eigene neue Oberflächenkennung verhindert Wiederverwendung der alten Bedienseite.
- 50 Tests bestanden; Browser-Vorschau mit simulierten Daten geprüft. Test an realem HA/ESP32/Loxone noch ausstehend.

# Änderungen

## 0.1.1

- Technischer Integrationsname, Domain, WebSocket-Befehle und Bedienseitenpfad auf `michis_steuerung` umgestellt.
- Übernahme vorhandener Einstellungen aus der bisherigen Domain ergänzt.
- Der alte Regler wird bei Übernahme deaktiviert; der neue startet mit ausgeschalteter Automatik.
- 38 lokale Controller- und Übernahmetests bestanden.


## Michi´s Steuerung 0.1.0

- Neue gemeinsame Bedienseite unter dem Namen Michi´s Steuerung.
- Ein- und ausklappbarer Miner-Grundwasser-Regler.
- Kompakte Anzeige der höchsten Temperatur und des zuletzt gesendeten Stellwerts mit Automatik-Schalter.
- MQTT-Basispfade, Miner-Namen und Temperaturnamen frei einstellbar.
- Normaler Regelschritt und einstellbare Schnellreaktion bei Temperaturanstieg.
- Einstellungen und zuletzt gesendeter Stellwert werden gespeichert.
- Automatik startet nach einem Neustart ausgeschaltet.

Der neue Versionsbeginn bezieht sich auf die umbenannte Oberfläche. In 0.1.0 war der bisherige interne Name noch vorhanden; ab 0.1.1 wurde er auf michis_steuerung umgestellt.
