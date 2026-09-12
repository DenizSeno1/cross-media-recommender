"""A11 — HyDE cipasi: pusula ortalamasina ham sorgu vektorunu katmanin etkisi.

Tek surecte kosar: model ve index bir kez yuklenir, 10 konfig ayni corpus'ta olculur.
urun=False: asagidaki ozet tablosu yalnizca recall/MRR basiyor, [URUN] yolu (isabet@k)
her sorguya 2 getir() daha ekliyordu -> 10 konfig icin 230 yerine 690 cagri, hepsi cope.
LLM cagrisi YOK — sahte belgeler cache/hyde/ icinde donmus (23 sorgu x n=1,5).

Kullanim:  python deney_a11.py
"""
import eval as ev

# Deniz'in kor tahmini (2026-09-05, kosmadan once): cipa 0'a YAKIN bir yerde tepe
# yapar ve 0.435'i GECER. Gerekcesi: ham sorgu tek basina 0 veriyor, o yuzden
# pusulayi tasimamali, sadece duzeltmeli.
# 09-03'ten devreden tahmin: cipayla n=5, n=1'i gecer.

IZGARA = [
    (1, 0.00), (1, 0.05), (1, 0.10), (1, 0.17), (1, 0.25), (1, 0.33), (1, 0.50),
    (5, 0.00), (5, 0.17), (5, 0.33),
]
GURULTU = 0.043   # 09-03'te olculdu: bunun altindaki fark okunmaz
KUANTUM = 1 / 23  # = 0.0435. 23 sorguda TEK bir sorgunun yer degistirmesi bu kadar
                  # oynatiyor -> gurultu tabaniyla ayni buyuklukte. Ilk surumde esik
                  # "abs(d) > 0.043" idi ve +0.043'u (tek sorgu) OKUNUR diye isaretledi:
                  # float artigi yuzunden 0.04348 > 0.043. Olcum aleti kendi hatasini
                  # uretti (09-04'te eval --kaynak varsayilaniyla ayni aile). Esik simdi
                  # IKI kuantum: en az iki sorgu yer degistirmeden "okunur" demiyoruz.

if __name__ == "__main__":
    ev.gold_dogrula()
    satirlar = []
    for n, c in IZGARA:
        print(f"\n{'='*70}\n  n={n}  cipa={c}\n{'='*70}")
        s = ev.degerlendir(hyde_n=n, cipa=c, hyde_cache=True, urun=False)
        satirlar.append((n, c, s))

    print(f"\n\n{'='*70}\n  A11 OZET   (gurultu tabani +-{GURULTU}, 23 sorgu)\n{'='*70}")
    print(f"{'n':>3} {'cipa':>6} | {'r@5':>6} {'r@10':>6} {'r@50':>6} {'MRR':>6} | {'r@5 fark':>9}")
    # Taban SADECE gercekten cipa=0 kosulmus satirdan gelir. Onceki hal placeholder olarak
    # satirlar[0]'i (n=1, cipa=0) her n'e koyuyordu: IZGARA'dan bir (n, 0.00) satiri
    # dusurulunce o n sessizce BASKA bir n'in tabaniyla kiyaslaniyor, farklar ve
    # OKUNUR/~gurultu etiketleri yanlis cikiyordu. Simdi eksik taban KeyError verir —
    # gurultuyu ayirmak icin yazilmis betik kendi olcum hatasini gizlememeli.
    taban = {n: s for n, c, s in satirlar if c == 0.0}
    for n, c, s in satirlar:
        d = s["recall@5"] - taban[n]["recall@5"]
        isaret = "" if c == 0.0 else ("  OKUNUR" if abs(d) >= 2 * KUANTUM - 1e-9
                                      else f"  ~gurultu ({round(abs(d) / KUANTUM)} sorgu)")
        print(f"{n:>3} {c:>6.2f} | {s['recall@5']:>6.3f} {s['recall@10']:>6.3f} "
              f"{s['recall@50']:>6.3f} {s['MRR']:>6.3f} | {d:>+9.3f}{isaret}")
