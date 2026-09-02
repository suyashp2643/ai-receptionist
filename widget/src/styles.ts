/**
 * All widget styling lives inside the Shadow DOM this string is injected
 * into (see ui.ts) — nothing here can leak onto the host page, and no host
 * page CSS can reach in, because Shadow DOM's style boundary is enforced
 * by the browser itself, not by naming convention.
 */
export function buildStyles(accentColor: string): string {
  const accent = accentColor || "#111111";
  return `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }

    .launcher {
      position: fixed;
      bottom: 20px;
      width: 56px;
      height: 56px;
      border-radius: 999px;
      background: ${accent};
      color: #fff;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(0,0,0,0.25);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      z-index: 2147483000;
    }
    .launcher--right { right: 20px; }
    .launcher--left { left: 20px; }

    .panel {
      position: fixed;
      bottom: 88px;
      width: 360px;
      max-width: calc(100vw - 32px);
      height: 520px;
      max-height: calc(100vh - 120px);
      background: #fff;
      color: #1a1a1a;
      border-radius: 12px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.3);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      z-index: 2147483000;
    }
    .panel--right { right: 20px; }
    .panel--left { left: 20px; }
    .panel[hidden] { display: none; }

    @media (max-width: 480px) {
      .panel {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        bottom: 0;
        right: 0;
        left: 0;
        border-radius: 0;
      }
    }

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      background: ${accent};
      color: #fff;
    }
    .header h1 { font-size: 14px; font-weight: 600; margin: 0; }
    .header-buttons { display: flex; gap: 6px; }
    .icon-button {
      background: transparent;
      border: none;
      color: inherit;
      cursor: pointer;
      font-size: 16px;
      padding: 4px 8px;
      border-radius: 6px;
    }
    .icon-button:hover { background: rgba(255,255,255,0.15); }

    .badge {
      display: inline-block;
      font-size: 10px;
      background: rgba(255,255,255,0.25);
      padding: 2px 6px;
      border-radius: 999px;
      margin-left: 6px;
    }

    .disclosure {
      font-size: 11px;
      color: #666;
      padding: 8px 14px;
      border-bottom: 1px solid #eee;
    }

    .transcript {
      flex: 1;
      overflow-y: auto;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .bubble {
      max-width: 85%;
      padding: 8px 10px;
      border-radius: 10px;
      font-size: 13px;
      line-height: 1.4;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .bubble--user { align-self: flex-end; background: ${accent}; color: #fff; }
    .bubble--assistant { align-self: flex-start; background: #f0f0f0; color: #1a1a1a; }

    .suggested {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 14px 8px;
    }
    .suggested button {
      font-size: 11px;
      border: 1px solid #ddd;
      background: #fff;
      border-radius: 999px;
      padding: 4px 10px;
      cursor: pointer;
    }

    .composer {
      display: flex;
      align-items: flex-end;
      gap: 6px;
      padding: 10px 12px;
      border-top: 1px solid #eee;
    }
    .composer textarea {
      flex: 1;
      resize: none;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 8px;
      font-size: 13px;
      max-height: 80px;
    }
    .send-button, .mic-button, .voice-toggle {
      background: ${accent};
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 13px;
    }
    .mic-button[aria-pressed="true"] { background: #c0392b; }
    .send-button:disabled, .mic-button:disabled { opacity: 0.5; cursor: not-allowed; }

    .actions-row {
      display: flex;
      gap: 6px;
      padding: 0 12px 8px;
      flex-wrap: wrap;
    }
    .actions-row button {
      font-size: 11px;
      border: 1px solid #ddd;
      background: #fff;
      border-radius: 6px;
      padding: 4px 8px;
      cursor: pointer;
    }

    .form-overlay {
      position: absolute;
      inset: 0;
      background: #fff;
      display: flex;
      flex-direction: column;
      padding: 14px;
      gap: 8px;
      overflow-y: auto;
    }
    .form-overlay label { font-size: 12px; display: flex; flex-direction: column; gap: 3px; }
    .form-error { font-size: 12px; color: #a12a2a; margin: 0; }
    .form-error[hidden] { display: none; }
    .form-overlay input, .form-overlay textarea, .form-overlay select {
      border: 1px solid #ddd;
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 13px;
    }
    .form-overlay .consent-row { flex-direction: row; align-items: center; gap: 6px; }
    .form-buttons { display: flex; gap: 8px; margin-top: 8px; }
    .form-buttons button {
      flex: 1;
      padding: 8px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      border: 1px solid #ddd;
      background: #fff;
    }
    .form-buttons .primary { background: ${accent}; color: #fff; border: none; }

    .status-line { font-size: 11px; color: #888; padding: 0 14px 6px; }
    .error-banner {
      margin: 0 14px 8px;
      padding: 8px 10px;
      background: #fdecea;
      color: #a12a2a;
      border-radius: 6px;
      font-size: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .error-banner button { font-size: 11px; }
    .error-banner[hidden] { display: none; }

    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }

    button:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible {
      outline: 2px solid #2684ff;
      outline-offset: 2px;
    }

    @media (prefers-reduced-motion: reduce) {
      * { animation: none !important; transition: none !important; }
    }
  `;
}
