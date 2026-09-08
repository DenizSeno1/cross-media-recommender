"""Mini proje ayarlari — tek yerden. Magic number koda gomulmez.

Flag'ler OLCULEREK karar verildi (Gun 10-11): degistirirken sebebini bil.
"""

import os
from pathlib import Path

KOK = Path(__file__).resolve().parent              # repo koku
VERI = KOK / "data"                                # dondurulmus corpus (repoda yok, scripts/ ile cekilir)
CACHE = KOK / "cache"
HYDE_CACHE = CACHE / "hyde"                        # olcum modunda dondurulmus sahte belgeler

# --- dondurulmus corpus dosyalari ---
ANIME_JSONL = VERI / "anime_anilist.jsonl"
FILM_JSONL = VERI / "movies_tmdb.jsonl"
KITAP_JSONL = VERI / "books_google.jsonl"
XML_LISTE = VERI / "animelist.xml"                 # kullanici MAL listesi (profil icin)
MAL_SYNOPSIS_JSONL = VERI / "mal_synopsis.jsonl"   # A7 deneyi: anime aciklamasinin alternatif kaynagi

# Anime aciklamasi nereden gelsin: "mal" (varsayilan) | "anilist".
# OLCULDU (2026-09-03, A7, tek degisken, donmus HyDE pusulasi, 23 sorgu):
#   recall@5  0.261 -> 0.435   |  MRR 0.235 -> 0.349   (+4 sorgu, gurultu tabani 1-2 sorgu)
# Ayni deney 2026-09-02'de KONTROLSUZ kosulmus ve "fark yok" denmisti — yanlisti.
# Surucu verbosity DEGIL: Madoka'nin MAL metni KISA (1337->684 krk) ama sirasi >50->20 cikti.
# Calisan hipotez: register uyumu — HyDE "arka kapak uslubunda Ingilizce sinopsis" uretiyor,
# MAL sinopsisleri tam o uslupta yazili; AniList tanitim diline kaciyor.
# Bedava degil: Steins;Gate 11->>50, Kobayashi 6->>50, Haikyuu 1->6 geriledi.
# Kapsam: MAL synopsis 4835/4880 kayitta var; eksikte veri.belge() AniList'e duser.
ANIME_KAYNAK = "mal"

# --- demo modu ---
# HF Spaces'te tam corpus YOK (sinopsis metni ucuncu tarafa ait) ve 2 vCPU'da 7807 dokumani
# her acilista gommek dakikalar surer. Demo paketi hazir vektor + telifsiz meta tasiyor.
# Elle acmak: DEMO_MODU=1. Otomatik: demo/ varsa ve tam corpus yoksa.
DEMO_DIZIN = KOK / "demo"
DEMO = (os.environ.get("DEMO_MODU", "").lower() in ("1", "true", "yes")
        or ((DEMO_DIZIN / "V.npy").exists() and not (VERI / "anime_anilist.jsonl").exists()))

# --- modeller ---
BI_MODEL = "intfloat/multilingual-e5-large"        # bi-encoder retrieval
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"           # cross-encoder rerank

# --- retrieval parametreleri ---
TOP_K = 5                                          # kullaniciya kac oneri
ADAY = 50                                          # HyDE aday havuzu (rerank girdisi)

# --- kisisellestirme (Gun 12-15, 2026-09-04) ---
PROFIL_AKTIF = True      # SADECE app.py'deki "Kisisellestirmeyi kullan" kutusunun varsayilani.
                         # B1b (09-05): retrieval artik bu bayragi OKUMUYOR — profil ya
                         # `getir(profil_paketi=...)` ile verilir ya verilmez. Gizli
                         # varsayilan dosya yok, "kimin profili" sorusu cagirana ait.
PROFIL_AGIRLIGI = 0.2    # harmanda profilin payi (0=sadece sorgu, 1=sadece profil)
                         # 0.6 -> 0.2 (2026-09-05, izle.py ile uc deger yan yana kosuldu).
                         # 0.6 GOZLEMLE secilmisti (medya dagilimina bakilarak) ve icerikli
                         # bir sorguda oneriyi IYILESTIRIP iyilestirmedigi hic olculmemisti:
                         # eval kisisellestirme KAPALI kosuyor, holdout ise SORGUSUZ yolu
                         # olcuyor -> "sorgu + profil" yolu olcunun disinda kalmisti.
                         #   agirlik  aci    ilk-5 medyasi        1. sira
                         #   0.0      0°     anime+kitap+film     Garden of Remembrance
                         #   0.2      6.8°   anime x3+kitap+film  Garden of Remembrance
                         #   0.3     10.4°   anime x4+kitap       Shin no Nakama...
                         #   0.6     21.2°   anime x5             (dogru tepe LISTEDEN DUSTU)
                         # Sorgu: "olum ve yas uzerine sakin fantastik yolculuk".
                         # 0.6'da pusula sorguyu TERK EDIYOR (maskesiz tepe KonoSuba oluyor).
                         # 0.2 tasarimin iddia ettigi seyi yapiyor: 09-04'un "6 derece, INCE
                         # AYAR" gerekcesi aslinda bu agirliga denk geliyormus, 0.6'ya degil.
                         # Ayrica capraz medyayi kota zorlamasina gerek kalmadan koruyor.
                         # ⚠️ Kanit GOZLE BAKMA (tek sorgu, tek profil), olcum degil — ama
                         # 0.6'nin arkasinda da olcum yoktu ve desen monoton.
K_ADA = 10               # K-means zevk adasi sayisi. Tek ortalama bant 0.0068 -> adalar medyan
                         # 0.0322 (5x ayrim gucu). Olculdu 2026-09-04.
SERI_TEKILLESTIR = True  # ayni franchise'tan tek sonuc (AniList relations grafi)

# Medya kotasi — capraz medyayi KOD garanti eder, vektorun insafina birakilmaz.
# OLCULDU (2026-09-04): profil_agirligi 0.0 -> %70/18/12 · 0.3 -> %97/2/1 · 0.6 -> %100/0/0.
# Profil anime verisinden kuruldugu icin harman sorguyu anime bolgesine cekiyor ve capraz
# medya (projenin ayirt edicisi) yok oluyor. Basamak gibi bir egri: agirligi kismak cozmuyor.
# Cozum medya BASINA siralama + kota. Medya filtresi seciliyse kota devre disi.
KOTA = {"anime": 3, "film": 1, "kitap": 1}

# --- flag'ler (olculup karar verildi) ---
HYDE_AKTIF = True      # recall@5 0 -> 0.364, kazandi (Gun 10-11)
HYDE_N_ORNEK = 1       # kac sahte belge uretilip ortalanacak (HyDE makalesinin cok-orneklem hali).
                       # varsayilan 1 = mevcut davranis. PILOT: 5 ile varyans azaltma denemesi.
HYDE_CIPA = 0.0        # A11: pusula ortalamasina HAM SORGU vektorunu de kat (HyDE makalesinin
                       # yaptigi, bizim atladigimiz adim). 0.0 = cipa yok (09-04'e kadarki hal),
                       # 1.0 = sadece ham sorgu (recall@5 = 0, Gun 10-11). Makale esit agirlikli
                       # ortalama aliyor -> N sahte belge icin cipa = 1/(N+1).
RERANK_AKTIF = False   # +0.18 recall@5 AMA ~1.5-3 dk/sorgu CPU -> varsayilan KAPALI.
                       # GPU / kucuk reranker / hosted API olursa ac.

# --- LLM (HyDE sahte belge + oneri aciklamasi icin) ---
# Gemini (Google Generative Language API). NVIDIA NIM free tier denendi ve GERI ALINDI
# (Gun 12-15): 82 katalog modelinin 3'u cagrilabildi, o 3'u de reasoning-latency
# (gpt-oss timeout) / rate-limit (minimax 429) yuzunden HyDE is yukunu karsilayamadi.
# Ders: managed API'de listeli != cagrilabilir != pratik kullanilabilir.
LLM_MODEL = "gemini-3.5-flash-lite"  # PILOT (3.6-flash) kazanmadi (top-50: 6/11 -> 4/11), geri alindi
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent"
TEMPERATURE = 0.2       # aciklama yaratici olmasin, getirilen metne bagli kalsin
TIMEOUT = 60            # saniye
MAX_RETRY = 3
BACKOFF_TABAN = 2       # exponential backoff: 2, 4, 8 sn
# Maliyet tablosu — 1M token basina USD. Saglayicinin fiyat sayfasindan DOGRULA.
FIYAT_GIRDI_1M = 0.10
FIYAT_CIKTI_1M = 0.40

# --- link sablonlari (id'den URL) ---
# anime idMal, film tmdb id, kitap google books id kullanir (veri.link() secer)
LINK = {
    "anime": "https://myanimelist.net/anime/{id}",
    "film": "https://www.themoviedb.org/movie/{id}",
    "kitap": "https://books.google.com/books?id={id}",
}

# --- ajan (Faz 5) ---
# Ajanin okudugu ozetin ust siniri. Arama TAM METIN uzerinde yapiliyor; bu kirpma
# yalnizca LLM'in baglamina gireni etkiler, retrieval kalitesini DEGISTIRMEZ.
# 512: corpus'un %47'si kirpilir, %53'u dokunulmadan gecer. 5 sonuc x 10 tur
# ~ 6.4k token — rahat butce. Alaka karari icin sinopsisin ONCULU yeterli.
AJAN_OZET_KRK = 512
