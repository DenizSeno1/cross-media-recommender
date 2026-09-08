"""Retrieval spine — HyDE -> bi-encoder -> (opsiyonel) rerank -> medya filtresi -> top-k.

Konsolide (Gun 12-15): gun3_4 (ara/index_kur), gun10_11 (HyDE/rerank),
gun8_9 (birlesik cross-media index). gunN dosyalarindan import YOK — paket biricik.

MIMARI KURAL (dunku id cehennemi + Faz 3 dersi): getir() KAYDIN KENDISINI dondurur.
Liste retrieval'dan gelir (id/baslik/link elde). LLM sadece aciklama yazar; onun
metnini parse edip id'ye geri eslemek YOK.

Sessiz hata sinifi (fazin 1 numaralı temasi): cache provenance guard'i (bkz. _index)
ve HyDE pusulasini gorunur kilan __main__ ciktisi.
"""

import hashlib
import json
import time

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

import config
import llm
import profil
import veri

# GPU varsa kullan. 4GB VRAM e5+reranker'i fp32'de birlikte tutamiyor -> fp16 ile
# ikisi de sigar (~2.2GB). CPU'da rerank ~30dk, GPU'da ~40sn (Gun 12-15 olcumu).
CIHAZ = "cuda" if torch.cuda.is_available() else "cpu"

# --- lazy singleton'lar: tekrar tekrar getir() cagrisinda model/index bir kez yuklensin ---
_model = None
_reranker = None
_V = None
_corpus = None
_belgeler = None
# NOT: profil BILEREK global degil (B1b, 2026-09-05). Indeks surece aittir — agir,
# paylasimli, kullanicidan bagimsiz. Profil KULLANICI OTURUMUNA aittir. Modul-duzeyi
# bir global ikisini ayni kapsamda tutuyordu: Streamlit tek surecte donuyor, o yuzden
# demoyu acan HERKES ilk yuklenen listenin zevkini aliyordu — sessizce.
_gruplar = None         # {AniList id: grup_no} — relations dosyasina bagli, profilden BAGIMSIZ
_medya_maske = None     # {"anime": bool dizi, ...} — "bu kayit o medyada DEGIL" maskesi


def _hazirla():
    """Model + birlesik index + corpus + belge metinleri — hepsi bir kez, sonra bellekte."""
    global _model, _V, _corpus, _belgeler
    if _model is None:
        _model = SentenceTransformer(config.BI_MODEL, device=CIHAZ)
        if CIHAZ == "cuda":
            _model = _model.half()          # fp16: reranker ile birlikte 4GB'a sigsin
    if _corpus is None:
        _corpus = veri.corpus_yukle()
        # Demo paketinde sinopsis yok -> belge() cagrilamaz; vektorler zaten hazir.
        _belgeler = [] if config.DEMO else [veri.belge(m) for m in _corpus]
    if _V is None:
        _V = _demo_index(len(_corpus)) if config.DEMO else _index(_belgeler, _model)
    return _model, _V, _corpus, _belgeler


def _medya_maskeleri(corpus):
    """{medya: (7807,) bool} — True = bu kayit o medyada DEGIL (yani maskelenecek).
    Bir kez kurulur; her getir() cagrisinda 7807'lik liste comprehension'i tekrarlamayalim."""
    global _medya_maske
    if _medya_maske is None:
        turler = {m["media"] for m in corpus}
        _medya_maske = {t: np.array([m["media"] != t for m in corpus]) for t in turler}
    return _medya_maske


def _seri_gruplari():
    '''Franchise gruplari — relations dosyasindan. KULLANICI PROFILINDEN BAGIMSIZ.

    Ayri tutulmasinin sebebi: seri tekillestirme ve medya kotasi kisisellestirme degil,
    SUNUM KURALI. Profili olmayan kullanici da ayni listede 3 One Piece kaydi gormemeli.
    Ikisini tek bayraga baglamak mimari hataydi (2026-09-04 review).'''
    global _gruplar
    if _gruplar is None:
        _gruplar = profil.seri_gruplari(profil.iliskiler_yukle())
        if not _gruplar:
            print("UYARI: anime_relations.jsonl yok -> seri tekillestirme DEVRE DISI. "
                  "Kurmak icin: python cek_anilist_relations.py")
    return _gruplar


def profil_kur(xml_kaynak=None):
    """MAL listesinden profil paketi kur: (zevk_adalari, izlenen_seri_maskesi).

    SAF fonksiyon — hicbir global yazmiyor. Cagiran sonucu SAHIPLENIR ve `getir`'e
    `profil_paketi=` ile verir; boylece profilin kapsamini cagiran belirler
    (Streamlit'te st.session_state = tarayici oturumu, CLI'da yerel degisken).

    xml_kaynak: yol ya da dosya-benzeri nesne (Streamlit uploader). None ise
        config.XML_LISTE. Liste yoksa ya da cekirdek yetersizse (None, None) doner —
        kisisellestirme opsiyonel bir KATMAN, urun onsuz da calismali.

    Maliyet: K-means + maske. Sorgu basina degil, LISTE basina bir kez cagrilmali."""
    model, V, corpus, _ = _hazirla()
    liste = profil.liste_yukle(xml_kaynak)
    if not liste:
        print("kullanici listesi yok -> kisisellestirme kapali")
        return (None, None)
    idmal_satir = {m["idMal"]: i for i, m in enumerate(corpus) if m["media"] == "anime"}
    satirlar = [idmal_satir[i] for i in profil.cekirdek_idler(liste, set(idmal_satir))]
    if len(satirlar) < max(profil.MIN_CEKIRDEK, config.K_ADA):
        print(f"cekirdek yetersiz ({len(satirlar)}) -> kisisellestirme kapali")
        return (None, None)
    adalar = profil.zevk_adalari(V, satirlar, config.K_ADA)
    maske = profil.izlenen_seri_maskesi(corpus, profil.izlenen_idler(liste), _seri_gruplari())
    print(f"profil: {len(satirlar)} cekirdek, {config.K_ADA} zevk adasi, "
          f"{int(maske.sum())} kayit elendi (izlenen seriler)")
    return (adalar, maske)


def _demo_index(n_kayit: int):
    """Hazir vektorleri yukle (demo paketi). _index'in icerik-hash guard'i BYPASS EDILMIYOR:
    demo modunda belge metni zaten yok, onun yerine demo/provenance.json vektorlerin hangi
    modelden, hangi kaynaktan ve hangi belge hash'inden uretildigini ACIKCA kaydediyor.
    Burada dogrulanan sey satir sayisi hizasi — corpus ile V ayni sirada olmak zorunda."""
    import json
    V = np.load(config.DEMO_DIZIN / "V.npy").astype(np.float32)
    prov = json.loads((config.DEMO_DIZIN / "provenance.json").read_text(encoding="utf-8"))
    if V.shape[0] != n_kayit:
        raise RuntimeError(f"demo paketi bozuk: V {V.shape[0]} satir, corpus {n_kayit} kayit")
    if prov["model"] != config.BI_MODEL:
        raise RuntimeError(f"demo vektorleri {prov['model']} ile uretilmis, "
                           f"config.BI_MODEL = {config.BI_MODEL}")
    print(f"demo index: {V.shape} (uretim {prov['uretim']}, imza {prov['kaynak_belge_hash']})")
    return V


def _index(belgeler, model):
    """Birlesik index'i cache'ten yukle, yoksa kur ve yaz (config.CACHE, paketin kendi cache'i).

    Provenance guard: cache adi belgelerin ICERIK hash'ini tasir — belge() metni degisince
    dosya adi degisir, eski vektorler sessizce okunamaz (fazin 1 numarali temasi)."""
    config.CACHE.mkdir(exist_ok=True)
    # Cache adi = model + BELGELERIN ICERIK HASH'i. Satir sayisi yetmiyordu: belge() metni
    # degisip sayi ayni kalabilir (A7'de tam bu oldu, MAL metni ayni 7807 kayda yazildi) ->
    # eski vektorler sessizce okunur, "fark yok" denir. Hash'te bu imkansiz; ayrica iki
    # varyantin cache'i yan yana durur, gecis bedava.
    imza = hashlib.sha1(chr(10).join(belgeler).encode("utf-8")).hexdigest()[:10]
    yol = config.CACHE / f"V_{config.BI_MODEL.split('/')[-1]}_{imza}.npy"
    if yol.exists():
        V = np.load(yol)
        print(f"index cache'ten: {yol.name} {V.shape}")
        return V
    print(f"index kuruluyor ({len(belgeler)} belge, e5-large, CPU'da birkac dk)...")
    V = model.encode(["passage: " + b for b in belgeler],
                     normalize_embeddings=True, show_progress_bar=True)
    np.save(yol, V)
    print(f"index yazildi: {yol.name} {V.shape}")
    return V


# Modul sabiti: prompt'un KENDISI cache anahtarina giriyor (asagi bak). Metni degistirirsen
# hash degisir, eski sahte belgeler otomatik gecersiz olur — elle surum numarasi tutmak yok.
HYDE_PROMPT = (
    "You help a semantic search engine for anime, movies and books. Given a user's "
    "request (written in Turkish), write a SHORT English plot synopsis (2-4 sentences, "
    "back-cover style) of a hypothetical work that would perfectly match the request. "
    "Write ONLY the synopsis in English, no preamble, no title.\n\n"
    "Request: {sorgu}"
)


def _hyde_cache_yolu(sorgu: str, n: int):
    """Cache anahtari = (prompt metni, n, sorgu) uclusunun hash'i.

    Prompt'u anahtara KOYMAK zorunlu: prompt degisince uretilen sahte belge de degisir,
    ama dosya adi degismezse eval ESKI pusulayla olcer ve 'fark yok' der — fazin 1 numarali
    temasi (sessiz hata), _index cache guard'iyla ayni aile."""
    ham = f"{HYDE_PROMPT}|{n}|{sorgu}".encode("utf-8")
    return config.HYDE_CACHE / f"{hashlib.sha1(ham).hexdigest()[:16]}.json"


def _hyde_belge(sorgu: str) -> str:
    """Sorgudan sahte INGILIZCE sinopsis (pusula belge). Dil+register ucurumunu kapatir:
    sorgu Turkce+elestirmen dili, corpus Ingilizce+arka-kapak dili."""
    prompt = HYDE_PROMPT.format(sorgu=sorgu)
    return llm.cagir([{"role": "user", "parts": [{"text": prompt}]}]).strip()


def _hyde_vektor(sorgu: str, model, n: int, cache: bool = False,
                 cipa: float = 0.0) -> tuple[np.ndarray, str]:
    """N sahte belge uret, HER BIRINI AYRI goem, vektorlerin ORTALAMASINI al.

    Neden: tek sahte belge tek bir icat = yuksek varyans (Kusuriya sorgusu iki ayri
    tek-cekimde iki farkli sonuc verdi). N cekilisin ortalamasi, her cekilisin kendine
    ozgu (idiosyncratic) icadini sonduruyor, PAYLASILAN tema sinyalini guclendiriyor.
    HyDE makalesinin (Gao ve ark.) orijinal cok-orneklem tarifi budur.

    Donus: (ortalama_vektor, ilk_sahte_metin) — ikincisi rerank asamasinda lazim
    (cross-encoder tek bir metinle skorlar, N tanesiyle degil)."""
    yol = _hyde_cache_yolu(sorgu, n)
    if cache and yol.exists():                       # OLCUM modu: donmus pusula, tekrarlanabilir
        sahteler = json.loads(yol.read_text(encoding="utf-8"))
    else:                                            # URUN modu: her seferinde taze uydurma
        sahteler = []
        for i in range(n):
            sahteler.append(_hyde_belge(sorgu))
            if i < n - 1:
                # flash-lite free tier 15 RPM = en fazla 4sn'de bir cagri (60/15). 3sn payi
                # tuketiyordu, sorgular ARASI bosluk da olmayinca n=5 kosusu 429'a carpti
                # (2026-09-03, 4. sorguda MAX_RETRY tukendi). 4.5sn: minimumun ustunde marj.
                time.sleep(4.5)
        if cache:
            config.HYDE_CACHE.mkdir(parents=True, exist_ok=True)
            yol.write_text(json.dumps(sahteler, ensure_ascii=False), encoding="utf-8")
    vektorler = [model.encode("query: " + s, normalize_embeddings=True) for s in sahteler]
    ortalama = np.mean(vektorler, axis=0)
    norm = np.linalg.norm(ortalama)
    q = ortalama / norm if norm > 0 else ortalama

    # --- A11 CIPA (2026-09-05) ------------------------------------------------
    # HyDE makalesi (Gao ve ark.) ortalamaya HAM SORGU vektorunu de katiyor; biz
    # atlamistik. Ham sorgu TEK BASINA recall@5 = 0 veriyor (Gun 10-11) — katkisi
    # "yon gostermek" degil, pusulayi GERI CEKMEK: sahte belgenin kendine ozgu
    # uydurmasini gercekten sorulan seye dogru duzeltmek.
    # Kazanc olmasi icin cipa vektorunun sahte belge vektorlerine YAKIN olmasi
    # gerekir (09-04'un kurali: ortalananlar yakinsa gurultu soner, uzaksa sinyal
    # soner). Bu olcum tam olarak o kuralin sinavi.
    #
    # (2026-09-05: ELLE listesindeydi, Deniz'in istegiyle mentor yazdi.)
    # Ham sorgu YUKARIDAKIYLE AYNI bicimde gomuluyor ("query:" onek + normalize):
    # e5 asimetrik bir model, sorgu ve belge farkli rollerde; bicim tutmazsa cipa
    # pusulayi duzeltmez, baska bir mahalleye tasir.
    # Harman profil.harmanla ile — ayni sekil, ikinci kez yazilmiyor.
    if cipa > 0:
        ham = model.encode("query: " + sorgu, normalize_embeddings=True)
        q = profil.harmanla(q, ham, cipa)

    return q, sahteler[0]


def _yeniden_sirala(sorgu_metni, aday_idx, belgeler, reranker, k):
    """Cross-encoder ile adaylari yeniden skorla, azalan sirala, top-k. (gun10_11'den.)"""
    ciftler = [[sorgu_metni, belgeler[i]] for i in aday_idx]
    skorlar = reranker.predict(ciftler, batch_size=16)   # 4GB VRAM'de aktivasyon tasmasin
    eslesme = sorted(zip(aday_idx, (float(s) for s in skorlar)), key=lambda x: x[1], reverse=True)
    return eslesme[:k]


def getir(sorgu: str, k: int = config.TOP_K, medya: str | None = None,
          rerank: bool = config.RERANK_AKTIF, hyde_n: int = config.HYDE_N_ORNEK,
          cipa: float = config.HYDE_CIPA, hyde_cache: bool = False, profil_paketi=None,
          profil_agirligi: float = config.PROFIL_AGIRLIGI,
          kota: bool = True, tekillestir: bool = config.SERI_TEKILLESTIR) -> list[dict]:
    """Sorguya en uygun k kaydi dondurur (KAYDIN KENDISI, skorla birlikte '_skor' alani).

    medya: Belirli bir medya turu filtrelenmek istenirse siralamadan once uygulanir.
    rerank: True ise ADAY havuzu cross-encoder ile yeniden siralanir (yavas, GPU'da ac).
    hyde_n: kac sahte belge uretilip ortalanacak (1=eski davranis, PILOT: 5).
    cipa: pusula ortalamasinda HAM SORGU vektorunun payi (A11). 0=cipa yok,
        1/(N+1)=HyDE makalesinin esit agirlikli hali, 1.0=sadece ham sorgu (recall 0).
    profil_paketi: profil_kur() ciktisi (adalar, izlenen_maske) ya da None.
        None ise kisisellestirme KAPALI — gizli varsayilan dosya YOK, bayrak da yok:
        profil ya verilir ya verilmez (B1b, 09-05). Eskiden `kisisel: bool` idi ve
        profili modul globalinden okuyordu; o tasarim "kimin profili" sorusunu
        cevaplayamiyordu. eval'de her zaman None: altin set "sorgu -> su anime"
        olcuyor, kisisellestirme tanimi geregi hedeften uzaklastirir (bkz. B4).
    profil_agirligi: harmanda profilin payi (0=sadece pusula, 1=sadece profil).
    kota / tekillestir: SUNUM kurallari — kisisellestirmeden BAGIMSIZ, profili olmayan
        kullanicida da gecerli. `kisisel` ile ayni bayraga baglamak mimari hataydi.
    hyde_cache: True ise sahte belge diskten okunur/yazilir -> TEKRARLANABILIR olcum.
        SADECE deney icin. Uründe False kalir: kullanici her sorguda taze pusula alir ve
        o varyans urunun gercek bir ozelligi — dondurursak kendimize yalan soyleriz."""
    model, V, corpus, belgeler = _hazirla()

    # 1) HyDE: sahte belge(ler) pusula -> query prefix ile gom (e5 asimetrik, sorgu rolu 'query:')
    if config.HYDE_AKTIF:
        q, sahte = _hyde_vektor(sorgu, model, hyde_n, cache=hyde_cache, cipa=cipa)
    else:
        q = model.encode("query: " + sorgu, normalize_embeddings=True)
        sahte = sorgu

    # 1b) kisisellestirme: pusulaya EN YAKIN zevk adasini sec, onunla harmanla.
    #     Neden en yakin ada: tek ortalama profil sorguyu baska yere CEKER (30 derece sapma
    #     olculdu); en yakin ada zaten sorgunun mahallesinde, INCE AYAR yapar (6 derece).
    izlenen_maske = None
    if profil_paketi is not None:
        adalar, izlenen_maske = profil_paketi
        if adalar is not None:
            q = profil.harmanla(q, profil.en_yakin_ada(adalar, q), profil_agirligi)

    # 2) bi-encoder: tum corpus'ta skor, top-ADAY havuz
    skorlar = V @ q

    # Iki maske de KIRPMADAN ONCE (dun ogrenilen kural: kirp-sonra-suz bug'i).
    if izlenen_maske is not None:
        skorlar[izlenen_maske] = -np.inf        # izledigin seri ve turevleri aramaya girmez

    if medya is not None:
        skorlar[_medya_maskeleri(corpus)[medya]] = -np.inf

    # Aday havuzu. Medya filtresi YOKSA ve kota devredeyse havuz MEDYA BASINA kurulur:
    # tek siralamada film/kitap ADAY sinirinin cok altinda kaliyor (olculdu: profil_agirligi
    # 0.3'te bile %97 anime), yani "capraz medya" havuza hic giremiyor. Skorlar zaten
    # hesaplandi, medya basina argsort ~bedava. NOT: rerank acikken maliyet medya sayisi
    # kadar artar (3x) — cross-encoder havuzun tamamini skorluyor.
    kotali = medya is None and kota and bool(config.KOTA)
    if kotali:
        aday_idx = []
        for t in config.KOTA:
            s_t = skorlar.copy()
            s_t[_medya_maskeleri(corpus)[t]] = -np.inf
            aday_idx += [int(i) for i in s_t.argsort()[::-1][:config.ADAY] if np.isfinite(s_t[i])]
    else:
        aday_idx = [int(i) for i in skorlar.argsort()[::-1][:config.ADAY]]
        # Medya kayit sayisi ADAY'dan azsa havuza -inf girer; onlar filtrelenmis kayitlar.
        if medya is not None:
            aday_idx = [i for i in aday_idx if np.isfinite(skorlar[i])]

    puan = {i: float(skorlar[i]) for i in aday_idx}

    # 3) opsiyonel rerank — (b) karari: sahte (Ingilizce) ile skorla, TR<->EN ucurumundan kac
    if rerank:
        global _reranker
        if _reranker is None:
            # reranker fp32 GPU'da (rerank_gpu.py'de kanitli 40sn). .half() DENENDI ->
            # transformers position-id yolunda BatchEncoding hatasi verdi, geri alindi.
            # VRAM: e5 fp16 (~1.1GB) + reranker fp32 (~2.3GB) ~3.4GB, 4GB'a sigar.
            _reranker = CrossEncoder(config.RERANK_MODEL, device=CIHAZ)
        yeni = _yeniden_sirala(sahte, aday_idx, belgeler, _reranker, len(aday_idx))
        aday_idx = [i for i, _ in yeni]
        puan = dict(yeni)

    # Havuzu SKORA gore sirala. Kotali modda havuz medya basina kuruldu (her medya kendi
    # icinde sirali ama birlesim degil); rerank kapaliyken liste sirasiz donuyordu.
    aday_idx.sort(key=lambda i: puan[i], reverse=True)

    # 4) SECIM, rerank'ten SONRA: her franchise'in en iyi temsilcisi + medya kotasi.
    #    Maske degil secim dongusu — hangisini atacagini ancak sirayi gezerken bilirsin.
    #    Kademe kurali: daha iyi yargic bakmadan malzeme atma.
    if tekillestir or kotali:
        aday_idx = profil.kota_sec(
            aday_idx, corpus, _seri_gruplari() if tekillestir else {}, k,
            profil.kota_olcekle(config.KOTA, k) if kotali else None)

    # _idx: kaydin corpus/V icindeki satir numarasi. Vektorune ulasmanin tek yolu bu
    # (Faz 5: sinyaller.benzerlik V[_idx] okuyor). id->indeks haritasi kurmak yerine
    # burada tasiniyor: ayni bilgiyi iki yerde tutmak sessizce desenkronize olur.
    return [dict(corpus[i], _idx=i, _skor=puan[i]) for i in aday_idx[:k]]


def getir_profilden(profil_paketi, k: int = config.TOP_K, medya: str | None = None,
                    kota: bool = True, tekillestir: bool = config.SERI_TEKILLESTIR) -> list[dict]:
    """Sorgu YOK — oneri dogrudan zevk adalarindan gelir. (B5, 2026-09-05)

    Neden ayri bir yol: "bana listeme gore oner" gibi bir istegin ICERIGI sifirdir.
    HyDE onu besleyecek malzeme bulamayinca yoktan bir olay orgusu uyduruyor
    (09-05'te loglandi: "former rivals... catastrophic timeline collapse across
    parallel dimensions" — listeyle ilgisi yok) ve hat o uydurmayi ariyor.
    Icerik sorguda degil LISTEDE; o yuzden burada pusula da listeden geliyor.

    SIFIR LLM cagrisi: ada secimi bir mesafe sorusu, uydurmaya ihtiyac yok.

    Adalar arasi SIRAYLA (round-robin) seciliyor — her adadan sirayla bir aday.
    Tek adadan k tane almak 09-04'un tersi hatasi olurdu: tek ortalama ayrimi
    oldururken, tek ada CESITLILIGI oldurur. Cesitlilik burada bedava geliyor.

    Donus: getir() ile AYNI sekil + '_ada' (hangi zevk adasindan geldigi).
    """
    adalar, izlenen_maske = profil_paketi
    if adalar is None:
        return []
    model, V, corpus, _ = _hazirla()

    skorlar = adalar @ V.T                       # (ada, 7807)
    if izlenen_maske is not None:
        skorlar[:, izlenen_maske] = -np.inf      # izledigin seri ve turevleri disarida
    if medya is not None:
        skorlar[:, _medya_maskeleri(corpus)[medya]] = -np.inf

    kotali = kota and medya is None
    hedef = profil.kota_olcekle(config.KOTA, k) if kotali else None
    gruplar = _seri_gruplari() if tekillestir else {}

    # Havuz KIRPILMIYOR — tum corpus. Ilk surumde k*ada kadar kirpilmisti ve medya
    # kotasi DOLMUYORDU: adalar anime cekirdeginden kuruldugu icin her adanin ilk
    # yuzlercesi anime; film/kitap havuza hic girmiyordu (09-04'te olculen yapisal
    # dagilim sorununun bu yoldaki hali). Kota bir TAVAN, kendi basina slot doldurmaz.
    # Maliyet: 10 x 7807 argsort, milisaniye.
    havuz = len(corpus)
    siralar = [list(np.argsort(-satir)[:havuz]) for satir in skorlar]
    imlec = [0] * len(adalar)

    secilen, secilen_grup, sayac = [], set(), {}
    ada = 0
    while len(secilen) < k and any(i < havuz for i in imlec):
        for _ in range(len(adalar)):             # bos/tikanmis adayi atla, sirayi bozma
            if imlec[ada] < havuz:
                break
            ada = (ada + 1) % len(adalar)
        else:
            break
        i = int(siralar[ada][imlec[ada]])
        imlec[ada] += 1
        m = corpus[i]
        # AD-ALANI: `gruplar` AniList id'siyle anahtarli, film TMDB / kitap Google Books
        # id tasiyor. Guardsiz lookup ad-alanlarini karistiriyordu: 253 film id'si bir
        # AniList id'siyle cakisiyor (Godfather 238, Matrix 603, LOTR 120/121/122) ->
        # film bir ANIME'nin franchise'inda sanilip sessizce eleniyor, capraz medya slotu
        # bosa dusuyordu. kota_sec() ayni korumayi zaten yapiyor, bu yol atlamisti.
        g = gruplar.get(m["id"]) if m["media"] == "anime" else None
        if g is None:
            g = ("tek", i)              # film/kitap ve iliskisiz anime: her biri biricik
        if g in secilen_grup or any(r["_i"] == i for r in secilen):
            continue                             # ayni seri ya da zaten secilmis
        if hedef is not None and sayac.get(m["media"], 0) >= hedef.get(m["media"], 0):
            continue                             # medya kotasi doldu
        secilen.append({"_i": i, "_skor": float(skorlar[ada][i]), "_ada": ada})
        secilen_grup.add(g)
        sayac[m["media"]] = sayac.get(m["media"], 0) + 1
        ada = (ada + 1) % len(adalar)

    return [dict(corpus[r["_i"]], _idx=r["_i"], _skor=r["_skor"], _ada=r["_ada"]) for r in secilen]


if __name__ == "__main__":
    # spine saglama: sorgu gir -> yapisal sonuc al (baslik + medya + link + skor)
    ornek = "ölüm ve yas üzerine sakin fantastik yolculuk"
    print(f"sorgu: {ornek}\n")
    sonuc = getir(ornek)
    for r in sonuc:
        print(f"  {r['_skor']:.3f}  [{r['media']}]  {veri.baslik(r)}")
        print(f"         {veri.link(r)}")
    print(f"\nLLM maliyeti: {llm.sayac.ozet()}")
