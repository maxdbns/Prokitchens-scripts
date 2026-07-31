// À coller dans Google Sheets : Extensions → Apps Script → coller → Enregistrer.
// Puis : Horloge (Déclencheurs) → Ajouter un déclencheur → syncBiensToSite /
// événement "Minuteur" → intervalle "Toutes les 15 minutes".
// Remplace SECRET par la valeur de PROFOODS_SHEETS_SECRET configurée dans Vercel.
// Remplace ALERT_EMAIL par l'adresse qui doit recevoir les alertes d'échec.

const ENDPOINT = "https://prokitchens-three.vercel.app/api/profoods/biens/sync";
const SECRET = "CHANGE_MOI";
const ALERT_EMAIL = "CHANGE_MOI@cloudkitchens.com";

function toCsv_(values) {
  return values
    .map((row) =>
      row
        .map((v) => {
          const s = String(v == null ? "" : v);
          return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        })
        .join(",")
    )
    .join("\n");
}

function syncBiensToSite() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  const values = sheet.getDataRange().getDisplayValues();
  let res;
  try {
    res = UrlFetchApp.fetch(ENDPOINT, {
      method: "post",
      contentType: "application/json",
      headers: { Authorization: "Bearer " + SECRET },
      payload: JSON.stringify({ csv: toCsv_(values) }),
      muteHttpExceptions: true,
    });
  } catch (e) {
    alertFailure_("Exception Apps Script", String(e));
    throw e;
  }
  const code = res.getResponseCode();
  const body = res.getContentText();
  Logger.log(code + " " + body);
  if (code !== 200) {
    alertFailure_("HTTP " + code, body);
    throw new Error("Sync biens échouée : HTTP " + code);
  }
  // Écrit le statut de la dernière sync dans une cellule d'un onglet "Sync Log"
  // (créé à la volée) pour que l'équipe voie que ça tourne sans ouvrir Apps Script.
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const log = ss.getSheetByName("Sync Log") || ss.insertSheet("Sync Log");
  log.getRange("A1:B1").setValues([["Dernière sync", new Date()]]);
  try {
    const parsed = JSON.parse(body);
    log.getRange("A2:B2").setValues([[
      "Biens synchronisés",
      parsed.upserted != null ? parsed.upserted : "?",
    ]]);
  } catch (e) {
    Logger.log("Réponse non-JSON : " + body);
  }
}

function alertFailure_(title, detail) {
  if (!ALERT_EMAIL || ALERT_EMAIL.indexOf("@") < 0) return;
  MailApp.sendEmail(
    ALERT_EMAIL,
    "[ProFoods] Échec de la sync Google Sheets → site",
    title + "\n\n" + detail.slice(0, 1500) +
      "\n\nVérifier : 1) le déclencheur Apps Script (Horloge), 2) que SECRET correspond à PROFOODS_SHEETS_SECRET dans Vercel, 3) les logs du site."
  );
}
