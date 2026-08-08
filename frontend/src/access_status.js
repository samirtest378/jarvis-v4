/** @type {Readonly<Record<string, {tone:"green"|"red"|"yellow"|"off", label:string, ready:boolean}>>} */
const PRESENTATIONS = Object.freeze({
  granted: { tone: "green", label: "Allowed", ready: true },
  available: { tone: "green", label: "Available", ready: true },
  denied: { tone: "red", label: "Blocked", ready: false },
  restricted: { tone: "red", label: "Restricted by system", ready: false },
  "not-granted": { tone: "red", label: "Not enabled", ready: false },
  limited: { tone: "yellow", label: "Partial access", ready: false },
  "not-determined": { tone: "yellow", label: "Not requested", ready: false },
  managed: { tone: "yellow", label: "Check Windows privacy", ready: false },
  unavailable: { tone: "off", label: "Not available", ready: false },
  unknown: { tone: "off", label: "Not checked", ready: false },
});

/** @param {string} value */
export function accessPresentation(value) {
  return PRESENTATIONS[value] || PRESENTATIONS.unknown;
}

/**
 * Summarize only core permissions that can be meaningfully checked on the
 * current platform. Accessibility remains optional and is not used to make a
 * misleading all-clear claim.
 * @param {string} platform
 * @param {{microphone:string,screen:string,files:string,automation:{calendar:string,mail:string,notes:string}}} status
 */
export function summarizeCoreAccess(platform, status) {
  const values = platform === "darwin"
    ? [status.microphone, status.screen, status.automation.calendar, status.automation.mail, status.automation.notes, status.files]
    : [status.microphone, status.screen, status.files];
  const ready = values.filter((value) => accessPresentation(value).ready).length;
  const attention = values.length - ready;
  return {
    ready,
    total: values.length,
    attention,
    message: attention === 0
      ? "All requested core permissions are available."
      : `${ready} of ${values.length} core permissions ready. ${attention} need attention or an operating-system check.`,
  };
}
