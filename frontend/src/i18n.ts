/** Small, dependency-free German/English UI layer. */

export type UiLanguage = "de" | "en";

const GERMAN: Record<string, string> = {
  "Personal intelligence": "Persönliche Intelligenz",
  "Local core": "Lokaler Kern",
  "Connecting…": "Verbindung wird hergestellt…",
  "Connected": "Verbunden",
  "Settings": "Einstellungen",
  "Restart assistant": "Assistent neu starten",
  "Open work mode": "Arbeitsmodus öffnen",
  "JARVIS is online": "JARVIS ist online",
  "Good morning.": "Guten Morgen.",
  "Good afternoon.": "Guten Tag.",
  "Good evening.": "Guten Abend.",
  "Still awake?": "Noch wach?",
  "What would you like to accomplish?": "Was möchten Sie erledigen?",
  "Private desktop session": "Private Desktop-Sitzung",
  "Message JARVIS v4": "Nachricht an JARVIS v4",
  "Ask JARVIS anything…": "Fragen Sie JARVIS alles…",
  "Send message": "Nachricht senden",
  "Voice ready when enabled": "Sprache bereit, sobald aktiviert",
  "send": "senden",
  "new line": "neue Zeile",
  "Enable or disable microphone": "Mikrofon ein- oder ausschalten",
  "Menu": "Menü",
  "Open menu": "Menü öffnen",
  "Conversation": "Unterhaltung",
  "Ready": "Bereit",
  "Ready — type a message or enable the microphone": "Bereit — schreiben oder Mikrofon aktivieren",
  "Waiting for “Hey JARVIS”…": "Warte auf „Hey JARVIS“…",
  "Listening — just keep talking…": "Ich höre zu — sprechen Sie einfach weiter…",
  "Thinking…": "Ich denke nach…",
  "Speaking…": "Ich spreche…",
  "Working…": "Ich arbeite…",
  "Copy": "Kopieren",
  "Copied": "Kopiert",
  "YOU": "SIE",
  "SYSTEM": "SYSTEM",
  "Close settings": "Einstellungen schließen",
  "Step 1 of 4": "Schritt 1 von 4",
  "Choose the intelligence JARVIS should use. You can change this later.": "Wählen Sie die Intelligenz für JARVIS. Das kann später geändert werden.",
  "Settings sections": "Bereiche der Einstellungen",
  "Voice": "Sprache",
  "Access": "Zugriff",
  "You": "Sie",
  "System": "System",
  "Intelligence": "Intelligenz",
  "Choose who powers JARVIS. The recommended settings are filled in for you.": "Wählen Sie den Anbieter für JARVIS. Die empfohlenen Werte sind bereits eingetragen.",
  "Security & key storage": "Sicherheit und Schlüsselspeicher",
  "Key storage": "Schlüsselspeicher",
  "Local file — no OS password": "Lokale Datei — kein Systempasswort",
  "System encryption — most secure": "Systemverschlüsselung — am sichersten",
  "Provider": "Anbieter",
  "Model settings": "Modelleinstellungen",
  "Chat model": "Chatmodell",
  "Research model": "Recherchemodell",
  "Test provider": "Anbieter testen",
  "Save & restart": "Speichern und neu starten",
  "JARVIS automatically understands German and English. Pick a voice and you are done.": "JARVIS versteht Deutsch und Englisch automatisch. Wählen Sie nur noch eine Stimme.",
  "Active output": "Aktive Ausgabe",
  "Checking…": "Wird geprüft…",
  "Recognition engine": "Spracherkennung",
  "Recognition": "Erkennung",
  "On this computer — bundled Whisper (recommended)": "Auf diesem Computer — Whisper Large-v3 (empfohlen)",
  "Automatic fallback chain": "Automatische Ersatzkette",
  "Cloud — OpenAI": "Cloud — OpenAI",
  "Cloud — Fish Audio": "Cloud — Fish Audio",
  "Off — no dictation": "Aus — kein Diktat",
  "“Hey JARVIS” on startup": "„Hey JARVIS“ beim Start",
  "Off — microphone starts only when you press the button (recommended)": "Aus — Mikrofon startet erst per Tastendruck (empfohlen)",
  "On — answer whenever you say “Hey JARVIS”": "An — bei „Hey JARVIS“ antworten",
  "Language — Sprache": "Sprache",
  "Automatic — German & English (recommended)": "Automatisch — Deutsch und Englisch (empfohlen)",
  "Voice conversation not tested": "Sprachunterhaltung noch nicht getestet",
  "Run voice check": "Sprachtest starten",
  "Speak naturally": "Natürlich sprechen",
  "Voice pack and fine-tuning": "Stimmpaket und Feinabstimmung",
  "Local voice": "Lokale Stimme",
  "Orb animation": "Orb-Animation",
  "Test Voice": "Stimme testen",
  "Save": "Speichern",
  "System Health": "Systemzustand",
  "Local service": "Lokaler Dienst",
  "Diagnostics privacy": "Datenschutz der Diagnose",
  "Secret-free": "Ohne Geheimdaten",
  "Connections": "Verbindungen",
  "Email": "E-Mail",
  "Calendar": "Kalender",
  "Apple Notes": "Apple Notizen",
  "Private JARVIS notes": "Private JARVIS-Notizen",
  "stored on this computer": "auf diesem Computer gespeichert",
  "Files": "Dateien",
  "Microphone": "Mikrofon",
  "Allow": "Erlauben",
  "No sign-in": "Keine Anmeldung",
  "Manage": "Verwalten",
  "Connect": "Verbinden",
  "Not connected": "Nicht verbunden",
  "User Preferences": "Persönliche Einstellungen",
  "Interface language": "Sprache der Oberfläche",
  "Automatic (system language)": "Automatisch (Systemsprache)",
  "German": "Deutsch",
  "English": "Englisch",
  "Your Name": "Ihr Name",
  "Your name": "Ihr Name",
  "Honorific": "Anrede",
  "None": "Keine",
  "Calendar Accounts": "Kalenderkonten",
  "Save Preferences": "Einstellungen speichern",
  "Preferences saved.": "Einstellungen gespeichert.",
  "System Info": "Systeminformationen",
  "Memory entries": "Erinnerungen",
  "Tasks": "Aufgaben",
  "Server port": "Server-Port",
  "Uptime": "Laufzeit",
  "Privacy & Reset": "Datenschutz und Zurücksetzen",
  "Next": "Weiter",
  "Refresh status": "Status aktualisieren",
  "Test connections": "Verbindungen testen",
  "Privacy Settings": "Datenschutzeinstellungen",
  "Check & Request": "Prüfen und anfragen",
  "Allow JARVIS once": "JARVIS einmal erlauben",
  "Permission saved": "Berechtigung gespeichert",
  "Background task started.": "Hintergrundaufgabe gestartet.",
  "Background task complete.": "Hintergrundaufgabe abgeschlossen.",
};

export function getUiLanguage(): UiLanguage {
  const stored = localStorage.getItem("jarvis_ui_language");
  if (stored === "de" || stored === "en") return stored;
  return /^de(?:-|$)/i.test(navigator.language || "") ? "de" : "en";
}

export function setUiLanguage(value: "auto" | UiLanguage): void {
  if (value === "auto") localStorage.removeItem("jarvis_ui_language");
  else localStorage.setItem("jarvis_ui_language", value);
}

export function tr(english: string): string {
  return getUiLanguage() === "de" ? (GERMAN[english] || english) : english;
}

function translateTextNode(node: Text): void {
  const raw = node.nodeValue || "";
  const trimmed = raw.trim();
  const translated = GERMAN[trimmed];
  if (!translated || translated === trimmed) return;
  node.nodeValue = raw.replace(trimmed, translated);
}

export function translateDom(root: ParentNode = document): void {
  const html = document.documentElement;
  html.lang = getUiLanguage();
  if (getUiLanguage() !== "de") return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) translateTextNode(node as Text);
  root.querySelectorAll<HTMLElement>("[placeholder], [aria-label], [title]").forEach((element) => {
    for (const attribute of ["placeholder", "aria-label", "title"]) {
      const value = element.getAttribute(attribute);
      if (value && GERMAN[value]) element.setAttribute(attribute, GERMAN[value]);
    }
  });
}

export function watchUiLanguage(root: HTMLElement = document.body): MutationObserver | null {
  translateDom(root);
  if (getUiLanguage() !== "de") return null;
  let translating = false;
  const observer = new MutationObserver((records) => {
    if (translating) return;
    translating = true;
    try {
      for (const record of records) {
        if (record.type === "characterData") translateTextNode(record.target as Text);
        for (const node of record.addedNodes) {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node as Text);
          else if (node instanceof HTMLElement) translateDom(node);
        }
      }
    } finally {
      translating = false;
    }
  });
  observer.observe(root, { childList: true, subtree: true, characterData: true });
  return observer;
}
