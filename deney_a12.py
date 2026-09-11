"""A12 — tur alaninin agirligi: belge() metninden TURLER cikarilirsa ne olur?

Gerekce: gomulen metin "baslik. TURLER. ozet". Tur alani metnin ~%5'i, sinopsis %95'i.
Kitap corpus'unu Open Library'ye tasirken "kitaplarin genres alanina ne yazilacak"
tartismasi uzadi — ama o alanin ETKISI hic olculmemisti. Once agirligi olc, sonra
nasil doldurulacagini tartis.

Kosum (iki AYRI surec, cunku config bayragi import aninda okunuyor):
    BELGE_TURLER=1 python deney_a12.py       -> data/a12_turler_acik.json
    BELGE_TURLER=0 python deney_a12.py       -> data/a12_turler_kapali.json
    python deney_a12.py --karsilastir        -> isaret testi + havuz@k farki

hyde_cache=True (eval varsayilani): iki varyant AYNI sahte belgelerle kosar,
tek degisken corpus metni olur.
"""

import argparse
import json

import config
import eval as ev

CIKTI = {True: config.VERI / "a12_turler_acik.json",
         False: config.VERI / "a12_turler_kapali.json"}


def kos():
    yol = CIKTI[config.BELGE_TURLER]
    print(f"BELGE_TURLER={config.BELGE_TURLER} -> {yol.name}")
    siralar = ev.siralar()                       # gold'un kacinci sirada geldigi (k=50)
    olcu = {}
    for k in (5, 10, 50):
        bulunan = sum(1 for s in siralar if s is not None and s <= k)
        # "havuz@k", "recall@k" DEGIL: bu sayi TEK bir getir(k=50) listesinin ilk k'sina
        # bakiyor, urunun getir(k=k) ile dondurdugu listeye degil. Kota k ile olcekleniyor
        # (k=50 -> 30/10/10, k=5 -> 3/1/1), yani iki listenin BILESIMI farkli. Urun sayisi
        # icin ev.isabet_at_k var (A13). A/B icin havuz olcusu daha hassas, ama adi
        # urun olcusunu ima etmemeli. NOT: eski a12_*.json dosyalari "recall@k" anahtarli
        # -> --karsilastir icin iki dosya AYNI surumle uretilmis olmali.
        olcu[f"havuz@{k}"] = bulunan / len(siralar)
    olcu["MRR"] = sum(1 / s for s in siralar if s is not None) / len(siralar)
    yol.write_text(json.dumps({"siralar": siralar, "olcu": olcu}, ensure_ascii=False),
                   encoding="utf-8")
    print(json.dumps(olcu, indent=2))


def karsilastir():
    a = json.loads(CIKTI[True].read_text(encoding="utf-8"))
    b = json.loads(CIKTI[False].read_text(encoding="utf-8"))
    print(f"{'olcu':<12} {'TURLER ACIK':>12} {'KAPALI':>10} {'fark':>9}")
    for k in a["olcu"]:
        d = b["olcu"][k] - a["olcu"][k]
        print(f"{k:<12} {a['olcu'][k]:>12.3f} {b['olcu'][k]:>10.3f} {d:>+9.3f}")
    print()
    print(ev.isaret_testi(a["siralar"], b["siralar"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--karsilastir", action="store_true")
    args = ap.parse_args()
    karsilastir() if args.karsilastir else kos()
