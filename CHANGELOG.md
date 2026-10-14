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
