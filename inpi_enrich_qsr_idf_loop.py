"""
Wrapper persistant pour l'enrichissement INPI QSR IDF.
Relance le script tous les jours tant qu'il reste des leads.
"""

import subprocess
import time
from datetime import datetime

SCRIPT = "/zpool/one/maxime.debaugnies/inpi_enrich_qsr_idf.py"
LOG_FILE = "/zpool/one/maxime.debaugnies/inpi_enrich_qsr_idf_loop.log"


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def main():
    while True:
        log("Lancement de l'enrichissement INPI QSR IDF")
        result = subprocess.run(["python3", SCRIPT], capture_output=False, text=False)
        log(f"Script terminé avec code {result.returncode}")

        log("Pause de 24h avant prochain lancement")
        time.sleep(86400)


if __name__ == "__main__":
    main()
