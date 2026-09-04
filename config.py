"""Mini proje ayarlari — tek yerden. Magic number koda gomulmez.

Flag'ler OLCULEREK karar verildi (Gun 10-11): degistirirken sebebini bil.
"""

from pathlib import Path

KOK = Path(__file__).resolve().parents[2]          # yol_haritasi/
VERI = KOK / "faz4" / "data"
CACHE = Path(__file__).parent / "cache"
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

# --- modeller ---
BI_MODEL = "intfloat/multilingual-e5-large"        # bi-encoder retrieval
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"           # cross-encoder rerank

# --- retrieval parametreleri ---
TOP_K = 5                                          # kullaniciya kac oneri
ADAY = 50                                          # HyDE aday havuzu (rerank girdisi)

# --- kisisellestirme (Gun 12-15, 2026-09-04) ---
PROFIL_AKTIF = True      # kullanici listesi varsa profil harmanlanir; yoksa duz sorgu aramasi
PROFIL_AGIRLIGI = 0.6    # harmanda profilin payi (0=sadece sorgu, 1=sadece profil)
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
