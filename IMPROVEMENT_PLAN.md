# JARVIS v4 – Verbesserungsplan für MacBook Air M2 mit 8 GB

## Zielbild

JARVIS v4 soll sich wie ein fertiger, persönlicher Desktop-Assistent anfühlen:

- dieselbe ruhige JARVIS-Sprecheridentität in Deutsch und Englisch;
- schneller Start und unmittelbare Reaktion auf einem MacBook Air M2 mit 8 GB;
- niedriger Speicherverbrauch ohne dauerhaft geladene KI-Modelle;
- eine klare, elegante Oberfläche mit flüssigen, aber sparsamen Animationen;
- zuverlässige Sprachsteuerung, verständliche Zustände und sichere lokale Daten;
- nachvollziehbare Fehler statt leerer Fenster oder stiller Ausfälle.

Die Optimierungen werden nicht nur nach Gefühl beurteilt. Für Start, Sprache,
Speicher und Bedienung gelten messbare Budgets und Abnahmekriterien.

## 1. Sprachqualität und einheitliche Sprecheridentität

### Problem

Das derzeitige schnelle Voice-Pack verwendet ein kompaktes MOSS-TTS-Nano-Modell
und ein ausschließlich aus englischer JARVIS-Sprache erzeugtes Stimmprofil.
Die Klangfarbe wird dadurch gut übertragen, die deutsche Aussprache und
Prosodie können aber fremd, instabil oder „komisch“ wirken. Sprache und
Sprecheridentität werden in den Audiotokens nicht vollständig getrennt.

### Ziel

- Deutsch und Englisch müssen klar dieselbe Person darstellen.
- Deutsch darf keinen hörbaren englischen Akzent bekommen.
- Kurze Systemantworten dürfen nicht hektisch, singend oder abgehackt klingen.
- Beide Sprachen müssen ohne Internet funktionieren.
- Das aktive Modell soll deutlich unter dem verfügbaren 8-GB-Speicherbudget
  bleiben und nach Inaktivität vollständig freigegeben werden.

### Umsetzung

1. Das vorhandene englische Profil bleibt die Referenz für englische Ausgabe.
2. Aus derselben englischen JARVIS-Identität wird mit dem hochwertigen
   mehrsprachigen Modell einmalig eine saubere deutsche Zwischenreferenz
   erzeugt.
3. Aus dieser Zwischenreferenz wird ein separates kompaktes deutsches
   MOSS-Profil erstellt.
4. Das Voice-Pack enthält anschließend zwei kleine Profile:
   `profile-en.safetensors` und `profile-de.safetensors`.
5. Die laufende Engine wählt das Profil anhand der Ausgabesprache, ohne das
   Modell neu zu laden.
6. Temperatur, Top-p, Wiederholungsstrafe und Tokenlimit werden getrennt für
   Deutsch und Englisch getestet. Eine Einstellung wird nur übernommen, wenn
   Aussprache, Sprecherähnlichkeit und Laufzeit gemeinsam besser werden.
7. Für häufige kurze Antworten werden stabile Testsätze verwendet:
   Begrüßung, Bestätigung, Kalender, Uhrzeit, Zahlen, Namen und Fehlermeldungen.
8. Jede Kandidatenstimme wird lokal transkribiert. Zusätzlich werden Lautheit,
   Dauer, Stille, Clipping und Sprecherähnlichkeit gegen die englische Referenz
   gemessen.
9. Das alte 7,7-GB-Modell bleibt ein reines Erzeugungswerkzeug und wird nicht
   mit der normalen App geladen.

### Abnahmekriterien

- Englische Testsätze werden lokal wortgenau erkannt.
- Deutsche Testsätze erreichen mindestens 95 % Wortgenauigkeit.
- Kein hörbarer Sprachwechsel innerhalb eines Satzes.
- Keine abgeschnittenen Satzenden und keine endlosen Wiederholungen.
- Nach warmem Start beginnt eine kurze Antwort möglichst innerhalb von 1 s.
- Der Voice-Prozess wird nach 120 s Inaktivität beendet.
- Die deutsche und englische Stimme werden in einem Hörvergleich eindeutig
  derselben Sprecheridentität zugeordnet.

## 2. Startzeit und Reaktionsgeschwindigkeit

### Messung

- Zeit von App-Start bis sichtbarem, bedienbarem Fenster;
- Zeit bis Backend-Gesundheitsprüfung;
- Zeit bis WebSocket-Verbindung;
- erste und warme Textantwort;
- erster und warmer Sprachsatz;
- Zeit zum Laden und Freigeben lokaler Sprachmodelle.

### Verbesserungen

- Das Backend bleibt als entpacktes Verzeichnis gebündelt, damit PyInstaller
  nicht bei jedem Start alles in einen temporären Ordner kopiert.
- UI und Backend starten parallel, solange die UI einen klaren Ladezustand
  anzeigt.
- Whisper und TTS werden nur bei tatsächlicher Verwendung geladen.
- Sprachmodelle werden nach Inaktivität freigegeben.
- Projektkontext, Kalender und optionale Integrationen werden nicht ungefragt
  beim Start geladen.
- Langsame Netzwerkprüfungen bekommen kurze Zeitlimits und blockieren niemals
  das Fenster.
- Wiederholte Initialisierungen werden vermieden; ein bereits warmer lokaler
  Voice-Prozess wird wiederverwendet.
- Große statische Dateien werden nicht in den JavaScript-Hauptbundle gepackt,
  wenn sie separat und verzögert geladen werden können.

### Budgets

- sichtbares Fenster: Ziel unter 2 s;
- lokales Backend bereit: Ziel unter 4 s;
- warme Texteingabe bis Anzeige: UI-Overhead unter 100 ms;
- Leerlauf ohne Sprachmodelle: so nah wie möglich an 300 MB Gesamtspeicher;
- keine dauerhafte hohe CPU- oder GPU-Last im Leerlauf.

## 3. Speicherstrategie für 8 GB RAM

- Nie Whisper, TTS und weitere große Modelle gleichzeitig warm halten, wenn
  sie nicht gebraucht werden.
- Whisper nach Ende des Sprachmodus freigeben.
- TTS nach kurzer Inaktivität freigeben.
- Audioantworten nach Wiedergabe aus dem Speicher entfernen.
- Base64-Audiodaten nur so lange halten, bis der Browser einen abspielbaren
  Blob erstellt hat.
- Lange Gespräche virtuell darstellen, statt unbegrenzt DOM-Elemente zu halten.
- Cache-Größen begrenzen und Diagnosewerte für aktuelle Prozesse anzeigen.
- Bei Speicherdruck Animationen reduzieren und lokale Modelle früher beenden.
- Das 7,7-GB-Mehrsprachenpaket nicht als Standard installieren.

## 4. Oberfläche und visuelle Qualität

- Sämtliche sichtbaren V3-Bezeichnungen auf V4 korrigieren.
- Typografie, Abstände, Kontrast, Karten und Schaltflächen vereinheitlichen.
- Zustände klar unterscheiden: bereit, hört zu, denkt, spricht, offline,
  eingeschränkt und Fehler.
- Die Hauptansicht ruhig halten; technische Details gehören in Diagnose und
  Einstellungen.
- Animationen auf `requestAnimationFrame` begrenzen und bei verdecktem Fenster
  pausieren.
- `prefers-reduced-motion` vollständig respektieren.
- Auf dem M2 eine niedrigere Renderauflösung nutzen, wenn das keinen sichtbaren
  Qualitätsverlust verursacht.
- Shader und Partikeleffekte nach realer GPU-Zeit bewerten.
- Einstellungen auf kleinen Fenstern und bei großer Schrift nutzbar halten.
- Fokus, Tastatursteuerung, Screenreader-Namen und Farbkontrast prüfen.
- Fehlermeldungen immer mit einer konkreten nächsten Handlung verbinden.

## 5. Sprachsteuerung und Mikrofon

- Das Mikrofon ist nach einem normalen App-Start aus, bis der Nutzer es
  ausdrücklich aktiviert.
- Der sichtbare Schalter zeigt den tatsächlichen Zustand, nicht nur den
  gewünschten Zustand.
- Wake-Word, Diktat und Folgefrage werden als getrennte Zustände behandelt.
- Stille oder Hintergrundgeräusche dürfen keine Nachricht absenden.
- Kurze Bestätigungen wie „ja“, „nein“ und „stopp“ bleiben möglich.
- Die lokale Spracherkennung bekommt deutsche Namen und JARVIS-Befehle als
  Kontext, ohne Gesprächsinhalte ins Internet zu senden.
- Nach Fehlern kehrt das System sicher in den Bereitschaftszustand zurück.
- Mikrofon- und TTS-Prozesse werden beim Schließen garantiert beendet.

## 6. Zuverlässigkeit

- Das App-Fenster zeigt während des Backend-Starts eine echte lokale
  Startseite statt einer Browser-Fehlerseite.
- Ein fehlgeschlagener erster Verbindungsversuch wird kontrolliert wiederholt.
- Backend-Abstürze werden erkannt und höchstens begrenzt automatisch neu
  gestartet.
- Voice-Pack-Installation bleibt atomar: prüfen, sichern, austauschen,
  starten; bei Fehlern zurückrollen.
- Modell, Engine, Profil und Shaderbibliothek werden über Prüfsummen validiert.
- Alle Netzwerk-, Datei- und Modelloperationen haben Zeitlimits.
- Diagnoseberichte enthalten Versionen und Status, aber keine API-Schlüssel
  oder privaten Gesprächsinhalte.

## 7. Datenschutz und Sicherheit

- API-Schlüssel bleiben im privaten lokalen Speicher beziehungsweise in der
  macOS-Schlüsselbundverschlüsselung.
- Geheimnisse werden dem Backend nur über die geschlossene Standardeingabe
  übergeben, nicht über Kommandozeile oder Prozessumgebung.
- Renderer, Backend und Voice-Engine kommunizieren ausschließlich über
  authentifizierte lokale Verbindungen beziehungsweise private Pipes.
- Voice-Packs werden gegen Pfadmanipulation, Symlinks, Zusatzdateien,
  Größenüberschreitung und falsche Prüfsummen geprüft.
- Externe URLs werden nur über sichere, erlaubte Protokolle geöffnet.
- Kamera, Mikrofon, Bildschirm und Automation werden nie ohne sichtbare
  Nutzeraktion angefordert.

## 8. Datenübernahme und Updates

- V4 bleibt eine eigene App neben V3.
- Einstellungen, Erinnerungen, Gesprächsdaten und lokale Schlüssel werden
  gezielt übernommen.
- Das alte große Voice-Pack wird nicht kopiert.
- Die Übernahme ist einmalig, protokolliert und überschreibt keine neueren
  V4-Daten.
- Release-Dateien tragen klare Versions-, Plattform- und Architekturangaben.
- Vor jedem Release werden App, DMG, ZIP und Voice-Pack mit SHA-256 geprüft.

## 9. Test- und Messmatrix

### Automatisch

- Backend-Unit- und API-Tests;
- Frontend-Logik, Sprachzustände und Produktionsbuild;
- Electron-Sicherheits- und Packaging-Tests;
- Voice-Pack-Manifest, Dateiinventar und Prüfsummen;
- Audioformat, maximale Dauer, Tokenlimits und Fehlerpfade;
- Deutsch/Englisch-Transkription;
- Start- und Stop-Verhalten der lokalen Prozesse.

### Auf echter Hardware

- Kaltstart und Warmstart auf MacBook Air M2;
- Leerlauf für mindestens 10 Minuten;
- zehn deutsche und zehn englische Sprachantworten;
- Wechsel zwischen Deutsch und Englisch ohne Neustart;
- Mikrofon an/aus, Ruhe, Hintergrundgeräusch und kurze Befehle;
- niedriger freier Speicher und App-Wechsel;
- Schlafmodus und Wiederaufnahme;
- Offline-Betrieb ohne Netz;
- beschädigtes oder inkompatibles Voice-Pack;
- Update von V3-Daten auf eine leere V4-Installation.

## 10. Prioritäten

### P0 – vor täglicher Nutzung

- deutsche Stimme an die englische Identität angleichen;
- V4-Branding überall korrigieren;
- Startseite ohne Browser-Fehler;
- Mikrofon standardmäßig aus;
- Voice-Pack und Backend end-to-end prüfen;
- RAM- und Prozessfreigabe bestätigen.

### P1 – unmittelbar danach

- Startzeit messen und verkürzen;
- GPU-sparsame Animation;
- bessere Diagnose- und Fehlermeldungen;
- verlässliche Datenmigration;
- Sprachwechsel ohne Qualitätsverlust.

### P2 – Feinschliff

- zusätzliche UI-Politur und Barrierefreiheit;
- optionale Qualitätsstufe für leistungsstärkere Macs;
- automatische, lokale Qualitätsprüfung neuer Voice-Profile;
- reproduzierbare Release- und Benchmark-Berichte.

## Definition „fertig“

V4 ist erst fertig, wenn die installierte App – nicht nur der Quellcode – auf
dem M2 startet, die übernommenen Daten öffnet, das Mikrofon kontrollierbar ist,
Deutsch und Englisch mit derselben JARVIS-Identität spricht, anschließend alle
lokalen Modelle wieder freigibt und sämtliche automatischen Tests sowie die
Hardwareprüfung besteht.
