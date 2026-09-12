"""Gold set yazarken kimlik bulma yardimcisi — Faz 5 Gun 3-4.

NEDEN VAR: gold vakasinin hedefi corpus'ta YOKSA o sorguda recall asla >0 olamaz
ve bu sessizdir — metrik duser, sen retrieval'i suclarsin. eval.gold_dogrula()
bunu yakaliyor ama ancak sen 20 vaka yazdiktan SONRA. Bu script once sormanizi
sagliyor: "bu eser corpus'ta var mi, id'si ne?"

DIKKAT — bu bir arama motoru DEGIL, sozluk araci. Corpus'u BASLIKTAN tariyor.
Gold yazarken sirasi onemli:
    1) once sorguyu AKLINDAN yaz (eseri bildigin icin, aciklamasina bakmadan)
    2) sonra burayla id'yi bul
Ters sirada calisirsan — once kaydi okuyup sonra sorguyu ona gore yazarsan —
sorguyu kaydin kendi kelimeleriyle yazma egilimine girersin ve olcu kolaylasir.
Retrieval'in isini kendin yapmis olursun; sayi yukselir, urun iyilesmez.

Kullanim:
    python deneyler/gold_ara.py monster              # tum medyalarda basliktan ara
    python deneyler/gold_ara.py --medya kitap crow    # sadece kitap
    python deneyler/gold_ara.py --sayim               # corpus dagilimi
"""

import collections
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # deneyler/ -> repo koku

import veri

# eval.ALTIN_SET hangi id'yi bekliyor: anime idMal, film TMDB id, kitap OL eser anahtari.
# veri._kimlik ile ayni kural — orasi degisirse burasi da degismeli.
ID_ALANI = {"anime": "idMal"}


def _kimlik(kayit: dict) -> tuple:
    alan = ID_ALANI.get(kayit["media"], "id")
    return (kayit["media"], kayit[alan])


def ara(desen: str, medya: str | None = None, limit: int = 25) -> list[dict]:
    """Basliginda `desen` gecen kayitlari doner (buyuk/kucuk harf duyarsiz)."""
    desen = desen.casefold()
    bulunan = []
    for kayit in veri.corpus_yukle():
        if medya and kayit["media"] != medya:
            continue
        if desen in veri.baslik(kayit).casefold():
            bulunan.append(kayit)
            if len(bulunan) >= limit:
                break
    return bulunan


def sayim() -> None:
    say = collections.Counter(k["media"] for k in veri.corpus_yukle())
    toplam = sum(say.values())
    print(f"corpus: {toplam} kayit")
    for m, n in say.most_common():
        print(f"  {m:6} {n:6}  ({n/toplam:.0%})")


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--sayim" in argv:
        sayim()
        raise SystemExit

    medya = None
    if "--medya" in argv:
        i = argv.index("--medya")
        medya = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    desen = " ".join(argv)
    if not desen:
        raise SystemExit(__doc__)

    bulunan = ara(desen, medya)
    if not bulunan:
        print(f"'{desen}' basligiyla eslesen kayit YOK"
              f"{f' ({medya})' if medya else ''}. Corpus'ta olmayan bir esere gold yazma.")
        raise SystemExit(1)

    for kayit in bulunan:
        m, kimlik = _kimlik(kayit)
        print(f'  ("{m}", {kimlik!r}),'.ljust(42)
              + f'# {veri.baslik(kayit)}  [{veri.link(kayit)}]')
    print(f"\n{len(bulunan)} kayit. Yukaridaki satiri ALTIN_SET'e oldugu gibi yapistirabilirsin.")
