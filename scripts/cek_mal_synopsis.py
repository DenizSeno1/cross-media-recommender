"""MAL synopsis cekici — AniList description'i MAL synopsis ile zenginlestirme DENEYI icin.

Neden: reranker probe'u gosterdi ki Frieren'in AniList metni (olay-mekanik) 0.069,
duygusal-acik metin 0.57 skor aliyor. Hipotez: MAL synopsis'i daha zengin/duygusal ->
recall yukselir. Tek degisken olarak olcecegiz (description kaynagi).

Uretir: faz4/data/mal_synopsis.jsonl  ->  {"idMal": int, "synopsis": str|null}  (DONDURULMUS)
Resumable: yeniden kosunca cekilmis idMal'lari atlar (append). Rate-limit'e nazik.
Public alan -> sadece X-MAL-CLIENT-ID header, OAuth yok.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ -> repo koku
import config

load_dotenv(config.KOK / ".env")
CID = os.environ.get("MAL_CLIENT_ID")
if CID is None:
    raise RuntimeError("MAL_CLIENT_ID .env icinde yok")

CIKTI = config.VERI / "mal_synopsis.jsonl"
BASE = "https://api.myanimelist.net/v2/anime/{}"
BEKLEME = 0.4                                       # ~2.5 istek/sn, nazik


def cekilmis_idler() -> set:
    """Zaten cekilmis idMal'lar (resume icin)."""
    if not CIKTI.exists():
        return set()
    return {json.loads(s)["idMal"]
            for s in CIKTI.read_text(encoding="utf-8").split("\n") if s.strip()}


def cek(idmal: int):
    """Tek anime synopsis. None=bos/kaldirilmis, '__HATA__'=agdan cekilemedi (yazma, tekrar dene)."""
    for deneme in range(4):
        try:
            r = requests.get(BASE.format(idmal), params={"fields": "synopsis"},
                             headers={"X-MAL-CLIENT-ID": CID}, timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** (deneme + 1))       # kota -> backoff, tekrar
                continue
            if r.status_code == 404:
                return None                          # anime MAL'da yok/kaldirilmis
            r.raise_for_status()
            return r.json().get("synopsis") or None
        except requests.exceptions.RequestException:
            time.sleep(2 ** (deneme + 1))
    return "__HATA__"


if __name__ == "__main__":
    anime = [json.loads(s) for s in config.ANIME_JSONL.read_text(encoding="utf-8").split("\n") if s.strip()]
    idler = [a["idMal"] for a in anime if a.get("idMal")]
    print(f"{len(anime)} anime, {len(idler)} idMal'li ({len(anime) - len(idler)} idMal'siz atlandi)")

    var = cekilmis_idler()
    kalan = [i for i in idler if i not in var]
    print(f"{len(var)} zaten cekilmis, kalan {len(kalan)} (~{len(kalan) * BEKLEME / 60:.0f} dk)")

    cekilen = hata = bos = 0
    with CIKTI.open("a", encoding="utf-8") as f:
        for idmal in kalan:
            syn = cek(idmal)
            if syn == "__HATA__":
                hata += 1
                continue                             # yazma -> sonraki kosuda tekrar denenir
            if syn is None:
                bos += 1
            f.write(json.dumps({"idMal": idmal, "synopsis": syn}, ensure_ascii=False) + "\n")
            f.flush()                                # incremental: kesilirse kayip olmasin
            cekilen += 1
            time.sleep(BEKLEME)
            if cekilen % 100 == 0:
                print(f"  {cekilen}/{len(kalan)} cekildi (bos synopsis {bos}, ag hatasi {hata})")

    print(f"\nbitti: {cekilen} cekildi, {bos} bos, {hata} ag hatasi (tekrar kosunca denenir)")
