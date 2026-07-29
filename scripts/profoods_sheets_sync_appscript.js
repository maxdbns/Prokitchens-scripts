// À coller dans Google Sheets : Extensions → Apps Script → coller → Enregistrer
// Puis : Horloge (Déclencheurs) → Ajouter un déclencheur → syncBiensToSite /
// événement "Minuteur" → intervalle "Toutes les 15 minutes".
// Remplace la valeur de SECRET par celle configurée côté site (PROFOODS_SHEETS_SECRET).

const ENDPOINT = "https://prokitchens-three.vercel.app/api/profoods/biens/sync";
const SECRET = "CHANGE_MOI";

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
  const res = UrlFetchApp.fetch(ENDPOINT, {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + SECRET },
    payload: JSON.stringify({ csv: toCsv_(values) }),
    muteHttpExceptions: true,
  });
  Logger.log(res.getResponseCode() + " " + res.getContentText());
}
