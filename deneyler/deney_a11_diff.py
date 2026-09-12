"""A11 — SORGU BAZLI karsilastirma: cipasiz vs cipali, yan yana.

deney_a11.py toplu sayi veriyordu ("+2 sorgu") ama HANGI iki sorgu oldugunu
gostermiyordu. Gurultu mu oruntu mu sorusunun cevabi orada: oynayan sorgular
birbirine benziyorsa mekanizma var, rastgeleyse gurultu.

Karsilastirmanin KENDISI eval.karsilastir'da (isaret testi + Delta-sira). Burada
sadece izgara noktasi seciliyor. Onceki surumde bu dosyanin KENDI `siralar()`'i
vardi ve kota/tekillestir'i elle sabitliyordu; eval.siralar ise getir()'in
varsayilanlarina guveniyordu. Iki kopya, ayni soruyu iki farkli hatta olcuyordu —
config.SERI_TEKILLESTIR degistigi gun ikisi sessizce ayrisirdi. Olcu tek yerde durur.

Kullanim:  python deneyler/deney_a11_diff.py [cipa]     (varsayilan 0.25)
"""
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # deneyler/ -> repo koku

import eval as ev

CIPA = float(sys.argv[1]) if len(sys.argv) > 1 else 0.25
N = 1


if __name__ == "__main__":
    ev.gold_dogrula()
    ev.karsilastir(f"cipasiz (0.00), n={N}", {"hyde_n": N, "cipa": 0.0},
                   f"cipali ({CIPA:.2f}), n={N}", {"hyde_n": N, "cipa": CIPA})
