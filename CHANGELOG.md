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
