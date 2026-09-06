"""AniList relations cekici — seri (franchise) tekillestirme icin.

Neden: `izlenen` filtresi idMal esitligiyle calisiyor, ama Haikyuu izleyen birine
"Haikyuu!!: Sainou to Sense" onerilmesi teknik olarak dogru, urun olarak sacma.
Baslik-kok sezgiseli (Gun 5-7 `seri_koku`) yarim cozum: "JoJo (TV)" ile "JoJo (2000)"
farkli kok uretiyor. Dogru cozum kaynaktan gelen ILISKI grafi.

Uretir: faz4/data/anime_relations.jsonl -> {"id": <AniList id>, "idMal": int|null,
        "relations": [{"tip": "SEQUEL", "id": <AniList id>, "idMal": int|null}, ...]}
DONDURULMUS: bir kere cek, diske yaz, bir daha cekme (corpus dondurma kurali).

Resumable: yeniden kosunca cekilmis id'leri atlar (append).
AniList resmi GraphQL, anahtar gerekmiyor. Sayfa basina 50 kayit, ~98 istek.
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ -> repo koku
import config

CIKTI = config.VERI / "anime_relations.jsonl"
URL = "https://graphql.anilist.co"
GRUP = 50            # AniList perPage tavani
BEKLEME = 1.2        # ~50 istek/dk — AniList limiti 90/dk, marjla altinda kal

SORGU = """
query ($ids: [Int]) {
  Page(page: 1, perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      idMal
      relations {
        edges {
          relationType
          node { id idMal type }
        }
      }
    }
  }
}
"""


def cekilmis_idler() -> set:
    """Zaten cekilmis AniList id'leri (resume icin)."""
    if not CIKTI.exists():
        return set()
    return {json.loads(s)["id"]
            for s in CIKTI.read_text(encoding="utf-8").split("\n") if s.strip()}


def cek(ids: list[int]) -> list[dict] | None:
    """Bir grup id icin relations. None = agdan cekilemedi (tekrar denenecek)."""
    for deneme in range(4):
        try:
            r = requests.post(URL, json={"query": SORGU, "variables": {"ids": ids}}, timeout=30)
            if r.status_code == 429:                      # kota -> backoff
                bekle = int(r.headers.get("Retry-After", 2 ** (deneme + 1)))
                print(f"  429, {bekle} sn bekleniyor")
                time.sleep(bekle)
                continue
            r.raise_for_status()
            veri = r.json()
            if "errors" in veri:                          # GraphQL hatasi HTTP 200 dondurur
                print("  GraphQL hatasi:", str(veri["errors"])[:200])
                return None
            return veri["data"]["Page"]["media"]
        except requests.exceptions.RequestException as hata:
            print(f"  ag hatasi ({hata.__class__.__name__}), deneme {deneme + 1}")
            time.sleep(2 ** (deneme + 1))
    return None


def _satir(m: dict) -> dict:
    """API cevabi -> diske yazilacak duz kayit. Sadece ANIME dugumleri tutulur;
    ADAPTATION kenari manga'ya gider, seri filtresi icin anlamsiz."""
    iliskiler = [
        {"tip": e["relationType"], "id": e["node"]["id"], "idMal": e["node"].get("idMal")}
        for e in (m.get("relations") or {}).get("edges", [])
        if e["node"].get("type") == "ANIME"
    ]
    return {"id": m["id"], "idMal": m.get("idMal"), "relations": iliskiler}


if __name__ == "__main__":
    anime = [json.loads(s) for s in
             config.ANIME_JSONL.read_text(encoding="utf-8").split("\n") if s.strip()]
    tum = [a["id"] for a in anime]
    var = cekilmis_idler()
    kalan = [i for i in tum if i not in var]
    gruplar = [kalan[i:i + GRUP] for i in range(0, len(kalan), GRUP)]
    print(f"{len(tum)} anime | {len(var)} cekilmis | kalan {len(kalan)} "
          f"({len(gruplar)} istek, ~{len(gruplar) * BEKLEME / 60:.1f} dk)")

    yazilan = hata = 0
    with CIKTI.open("a", encoding="utf-8") as f:
        for n, grup in enumerate(gruplar, 1):
            sonuc = cek(grup)
            if sonuc is None:
                hata += 1
                continue                                  # yazma -> sonraki kosuda tekrar denenir
            for m in sonuc:
                f.write(json.dumps(_satir(m), ensure_ascii=False) + "\n")
                yazilan += 1
            f.flush()                                     # kesilirse kayip olmasin
            if n % 10 == 0:
                print(f"  {n}/{len(gruplar)} istek | {yazilan} kayit")
            time.sleep(BEKLEME)

    print(f"\nbitti: {yazilan} kayit yazildi, {hata} istek basarisiz "
          f"(tekrar kosunca denenir) -> {CIKTI.name}")
