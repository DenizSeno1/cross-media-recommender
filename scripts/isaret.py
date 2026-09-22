"""Iki yonlu isaret testi — Faz 5 Gun 7, kademe 1 (Deniz elle yazdi, 2026-09-22)."""
import math


def isaret_p(kazanc: int, kayip: int) -> float:
    """İki yönlü işaret testi p değeri."""
    n = kazanc + kayip
    toplam = 2 ** n
    if n == 0:
        return 1.0

    uc = max(kazanc, kayip)
    kuyruk = sum(math.comb(n, i) for i in range(uc, n + 1)) / toplam
    return min(1.0, 2 * kuyruk)
