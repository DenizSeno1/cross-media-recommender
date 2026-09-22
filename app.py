"""Streamlit gozlem UI — INCE ve ISLEVSEL (cila DEGIL, o en son).

Neden simdi: recall@k retrieval'i olcuyor, "iyi oneri mi"yi olcmuyor. O soruyu
KULLANARAK gozlemliyoruz. oneri() yapisal dict donuyor -> burasi sadece render
eder; motor arkada degisse de (rerank/medya/hyde) dict sekli sabit, UI kirilmaz.

Kosmak:  streamlit run faz4/faz4_gun12_15/app.py
"""

import hashlib
import inspect
import io
import time

import streamlit as st

import config
import dongu
import llm
import oneri
import retrieval
import veri

st.set_page_config(page_title="Capraz-Medya Onerici", page_icon="🎬", layout="centered")


@st.cache_resource(show_spinner="Model + index isitiliyor (ilk acilista birkac dk)...")
def isit():
    """Agir init (e5 + 12104 index) bir kez; Streamlit her etkilesimde script'i
    bastan kosar, cache_resource ile model/index yeniden yuklenmez."""
    retrieval._hazirla()
    return True


isit()

st.title("🎬 Capraz-Medya Onerici")
st.caption("Anime · film · kitap — icerik-tabanli HyDE retrieval. Gozlem arayuzu.")

if config.DEMO:
    st.info(
        "**Demo modu.** Vektorler onceden hesaplanmis (7807 kayit; paket 2026-09-06'da, "
        "kitap kaynagi Open Library'ye tasinmadan once uretildi) ve "
        "hazir yuklendi; sinopsis METNI bu pakette yok — ucuncu tarafa ait. Sonuclar "
        "gercek sistemle ayni, cunku vektorler ayni. Rerank kapali (CPU'da dakikalar "
        "suruyor), yani kalite olculen tavanin altinda. Kaynak ve olcumler README'de.",
        icon="🧪",
    )

# --- profil: OTURUMA ait, surece degil (B1b, 2026-09-05) ---
# Eskiden retrieval'da modul-duzeyi bir globaldi ve sabit bir XML yolundan okuyordu:
# Streamlit tek surecte doner, o yuzden demoyu acan HERKES ayni (Deniz'in) zevkini
# aliyordu ve bunu goren yoktu. Dogru kapsam: indeks surece ait (agir, paylasimli,
# kullanicidan bagimsiz), profil TARAYICI OTURUMUNA ait.
# st.session_state tam olarak oturum kapsami; dosya hash'i ile anahtarliyoruz ki
# ayni dosya her etkilesimde yeniden K-means'e sokulmasin (script bastan kosuyor).
def profil_al(yuklenen):
    if yuklenen is None:
        st.session_state.pop("profil", None)
        st.session_state.pop("profil_hash", None)
        return None
    ham = yuklenen.getvalue()
    h = hashlib.sha1(ham).hexdigest()[:16]
    if st.session_state.get("profil_hash") != h:
        with st.spinner("Liste okunuyor, zevk adalari cikariliyor..."):
            try:
                st.session_state["profil"] = retrieval.profil_kur(io.BytesIO(ham))
            except Exception as e:
                # `type=["xml"]` sadece UZANTIYI suzuyor, icerik hakkinda hicbir sey
                # soylemiyor: kirpilmis export ET.ParseError, series_animedb_id'si eksik
                # dugum int(None) -> TypeError atiyor. Kisisellestirme OPSIYONEL bir
                # katman -> hatali yukleme yuklemeyi dusurur, sayfayi degil.
                st.error(f"Liste okunamadi ({type(e).__name__}) — kisisellestirme kapali. "
                         "MyAnimeList > Profile > Export ile alinan XML'i yukle.")
                st.session_state.pop("profil", None)
                st.session_state.pop("profil_hash", None)
                return None
        st.session_state["profil_hash"] = h
    return st.session_state["profil"]


# --- sidebar: motor knoblari (degistir -> gozlemle) ---
with st.sidebar:
    st.header("Profil")
    yuklenen = st.file_uploader("MAL listeni yukle (XML export)", type=["xml"],
                                help="MyAnimeList > Profile > Export. Yuklemezsen "
                                     "kisisellestirme kapali, duz sorgu aramasi calisir.")
    paket = profil_al(yuklenen)
    kisisellestir = st.checkbox("Kisisellestirmeyi kullan", value=config.PROFIL_AKTIF,
                                disabled=paket is None or paket[0] is None,
                                help="Kapatirsan ayni sorgu profilsiz kosar — farki gozlemlemek icin.")
    if paket is None:
        st.caption("Profil yok -> herkes ayni sonucu alir.")
    elif paket[0] is None:
        st.warning("Liste okundu ama cekirdek yetersiz (8+ puanli, corpus'ta olan anime az). "
                   "Kisisellestirme kapali.")
    else:
        st.success(f"{config.K_ADA} zevk adasi kuruldu · "
                   f"{int(paket[1].sum())} kayit elendi (izlenen seriler)")

    st.header("Motor")
    # AJAN MODU (2026-09-22 karari): varsayilan ajansiz + rerank; ajan GORUNUR bir anahtar.
    # Ajan acikken medya / k / rerank kontrolleri KILITLI: ajan olculdugu haliyle kosar
    # (medyayi kendisi secer, "en iyi 5", rerank = getir()'in varsayilani). Kontrolleri
    # ajana iletmek prompt'u degistirir -> 41/60 artik o ajanin sayisi olmaz.
    ajan_modu = st.toggle("Ajan modu (deneysel)", value=False,
                          help="Olculdu: 33/60 -> 41/60 (11/3, p=0.057 — kanitli degil), "
                               "medyan bekleme 20 sn -> 69 sn, ~5 LLM cagrisi.")
    medya_sec = st.selectbox("Medya", ["hepsi", "anime", "film", "kitap"], index=0,
                             disabled=ajan_modu,
                             help="Cross-media: 'anime' sec -> sadece anime; 'film' -> Monster gibi film")
    k = st.slider("Kac oneri (k)", 1, 10, config.TOP_K, disabled=ajan_modu)
    rerank = st.checkbox("Rerank (cross-encoder)", value=config.RERANK_AKTIF, disabled=ajan_modu,
                         help="Olculdu: isabet@5 23/60 -> 33/60 (p=0.006).")
    cihaz = "GPU" if retrieval.CIHAZ == "cuda" else "CPU"
    if ajan_modu:
        st.caption("Ajan medyayi ve kapsami sorgudan kendisi anlar · 5 oneri · "
                   f"rerank {cihaz}'da her arama turunda.")
    elif rerank:
        st.caption(f"Rerank {cihaz}'da calisiyor"
                   + (" (olculen medyan ~20 sn/sorgu)." if cihaz == "GPU"
                      else " — GPU yok, her sorgu dakikalarca surebilir."))

# --- ana: sorgu formu (form -> her tus vurusunda degil, gonderince kosar) ---
with st.form("sorgu_form"):
    sorgu = st.text_input("Ne izlemek / okumak istersin?",
                          placeholder="bos birak -> sadece listene gore oner")
    gonder = st.form_submit_button("Oner")
    st.caption("Bos birakirsan sorgu YOK: oneri dogrudan zevk adalarindan gelir "
               "(HyDE devre disi, her adadan sirayla bir oneri).")

aktif = paket if (kisisellestir and paket is not None and paket[0] is not None) else None

# B3 daraltma turu: yeniden yazilmis sorguyu bir sonraki kosuya tasir (tek tur, dongu yok).
daraltildi = False
if "zorla_sorgu" in st.session_state:
    sorgu = st.session_state.pop("zorla_sorgu")
    gonder = True
    daraltildi = True

profil_modu = gonder and not sorgu.strip() and aktif is not None

if gonder and (sorgu.strip() or profil_modu):
    llm.sayac.sifirla()          # C3: asagidaki maliyet BU sorgunun, kumulatif degil
    medya = None if medya_sec == "hepsi" else medya_sec
    # Bos sorgu + profil = SORGUSUZ yol (B5). Icerigi olmayan bir sorguyu HyDE'a
    # vermek onu yoktan bir olay orgusu uydurmaya zorluyordu; icerik listede.
    if profil_modu:
        with st.spinner("Zevk adalarindan seciliyor (LLM cagrisi: sadece aciklama)..."):
            sonuc = oneri.oneri_profilden(aktif, k=k, medya=medya)
        st.info("Sorgusuz mod: oneriler dogrudan zevk adalarindan, her adadan sirayla.")
    elif ajan_modu:
        if aktif is not None:
            st.warning("Ajan modu kisisellestirmeyi henuz kullanmiyor — MAL profilin bu "
                       "sorguya uygulanmadi (Faz 6).")
        try:
            with st.spinner("Ajan calisiyor: arama turlari + secim (olculen medyan ~1 dk)..."):
                basla = time.perf_counter()
                ham = dongu.dongu(sorgu)
                ajan_sn = time.perf_counter() - basla   # kullanicinin GERCEK beklemesi
        except Exception as h:       # 09-18: PROHIBITED_CONTENT tam bu yoldan geldi
            st.error(f"Ajan cevap uretemedi ({type(h).__name__}: {h}). Ajan modunu "
                     "kapatip ayni sorguyu dene.")
            st.stop()
        cevap = ham["cevap"] or ("Ajan tur sinirina dayandi ve secim yapmadi; "
                                 "ilk gorulen kayitlar gosteriliyor.")
        sonuc = {"sorgu": sorgu, "oneriler": ham["oneriler"], "aciklama": cevap,
                 "turlar": ham["turlar"], "durma_sebebi": ham["durma_sebebi"],
                 "sure_sn": ajan_sn}
    else:
        with st.spinner("HyDE -> retrieval -> aciklama..."):
            sonuc = oneri.oneri(sorgu, k=k, medya=medya, rerank=rerank, profil_paketi=aktif)

    # AKTIF sorguyu bas. Daraltmadan sonra ustteki kutu ESKI metni gosteriyor: Streamlit
    # widget'i kendi degerini oturumda tutuyor, `sorgu` degiskenini degistirmek onu
    # degistirmiyor. Kutuyu zorlamak yerine sonucu ureten sorguyu ayrica yaziyoruz —
    # burasi bir GOZLEM arayuzu ve gozlenecek sey tam da bu: LLM olumsuzlamayi
    # ("romantik olmasin") hangi OLUMLU tarife cevirdi. (09-05 elle test)
    if not profil_modu:
        etiket = "Daraltilmis sorgu (LLM yeniden yazdi)" if daraltildi else "Aktif sorgu"
        st.caption(f"{etiket}: {sonuc['sorgu']}")

    ajan_sonucu = "turlar" in sonuc
    if ajan_sonucu:
        # Ajanin araci getir()'e rerank GECMIYOR -> olcek getir()'in KENDI varsayilani.
        # Checkbox'a ya da config'e bakmak yanlis olurdu: varsayilan import anında
        # baglaniyor (09-18, rerank_dogrula ile ayni gerekce).
        ajan_rerank = inspect.signature(retrieval.getir).parameters["rerank"].default

    st.subheader("Oneriler")
    for r in sonuc["oneriler"]:
        # C9: skorun HANGI olcek oldugunu yaz. rerank acikken _skor cross-encoder
        # skoru (0.0X bandi), kapaliyken kosinus (0.9 bandi). Ayni ismi tasiyan iki
        # ayri olcek, disaridan bakan "sistem bozuk" diye okuyor (09-05, dis inceleme).
        if ajan_sonucu:
            # Ajanin kayitlari araclar._getir_kirp bicimli: baslik/tur/link hazir.
            olcek = "rerank" if ajan_rerank else "kosinus"
            baslik, link, medya_adi = r["baslik"], r["link"], r["tur"]
        else:
            olcek = "rerank" if (rerank and not profil_modu) else "kosinus"
            baslik, link, medya_adi = veri.baslik(r), veri.link(r), r["media"]
        ada = f"  ·  ada `{r['_ada']}`" if "_ada" in r else ""
        st.markdown(
            f"**[{baslik}]({link})**  ·  `{medya_adi}`  ·  "
            f"{olcek} `{r['_skor']:.3f}`{ada}"
        )
    if not sonuc["oneriler"]:
        st.info("Bu medya filtresinde sonuc havuzda cikmadi — filtreyi genislet.")

    st.subheader("Neden bu liste?")
    st.write(sonuc["aciklama"])
    st.caption(f"LLM: {llm.sayac.ozet()}")

    # Ajan ne yapti — GORUNUR olsun diye (karar: sure, tur, her turun aramasi, LLM cagrisi).
    if ajan_sonucu:
        turlar = sonuc["turlar"]
        aramalar = [t for t in turlar if t["arac"]]
        # Sure DUVAR SAATI: turlarin sure_sn toplami degil — cevap turunun LLM cagrisi da
        # kullanicinin beklemesi (kor review 09-22, hata 1).
        st.caption(f"Ajan: {len(aramalar)} arama · {len(turlar)} tur · {sonuc['sure_sn']:.1f} sn · "
                   f"durma: {sonuc['durma_sebebi']} · {llm.sayac.cagri} LLM cagrisi")
        with st.expander("Ajanin turlari"):
            # Arac cagiran turlar, POZISYONA gore degil: hard_cap yolunda son tur da
            # bir aramadir (kor review 09-22, hata 2).
            for t in aramalar:
                a = t["args"]
                ne = ("TEKRAR — calistirilmadi" if t.get("tekrar")
                      else f"{len(t.get('getirilen_idx', []))} kayit")
                st.markdown(f"**tur {t['no']}** · `{t['arac']}`(sorgu=\"{a.get('sorgu', '')}\", "
                            f"medya={a.get('medya', 'hepsi')}) → {ne} · {t['sure_sn']:.1f} sn")
                st.caption(f"dusunce: {t['dusunce']}")

    # Daraltilacak sorguyu OTURUMA yaz (form asagida, bu blogun DISINDA).
    if profil_modu:
        st.session_state.pop("son_sorgu", None)   # sorgusuz mod -> daraltacak sorgu yok
    else:
        st.session_state["son_sorgu"] = sorgu
elif gonder:
    st.info("Once bir sorgu yaz — ya da listeni yukleyip bos birak.")

# --- B3: sohbetle daraltma, TEK TUR ---
# `while` yok, ajan dongusu Faz 5. Daraltma sonuclari SUZMUYOR: sorguyu yeniden
# yazip tum hatti bastan kosturuyor (yeni HyDE pusulasi dahil). Sebep, prompt'ta
# da yazili — embedding'ler olumsuzlama yapamaz, "romantik olmasin" vektoru
# "romantik"e yakin cikar; olumsuzlama VEKTORDEN ONCE cozulmeli.
#
# Form SONUC BLOGUNUN DISINDA olmak ZORUNDA (09-05 dis inceleme): Streamlit'te
# st.form_submit_button yalnizca KENDI formunun gonderildigi kosuda True doner.
# "Daralt"a basilan kosuda "Oner"in `gonder`i False oluyor -> form yukaridaki
# `if gonder` blogunun icindeyken o blok komple atlaniyor, govdesi hic kosmuyordu:
# oneri.daralt() cagrilmiyor, zorla_sorgu yazilmiyor, sayfa da bosaliyordu.
# Kapi artik `gonder` degil, oturumdaki son_sorgu.
if "son_sorgu" in st.session_state:
    with st.form("daralt_form"):
        daraltma = st.text_input("Daralt (tek tur)",
                                 placeholder="orn: romantik olmasin · daha kisa olsun")
        if st.form_submit_button("Daralt"):
            if daraltma.strip():
                with st.spinner("Sorgu yeniden yaziliyor..."):
                    yeni = oneri.daralt(st.session_state["son_sorgu"], daraltma)
                st.session_state["zorla_sorgu"] = yeni
                st.rerun()
            else:
                st.info("Daraltma bos — ne istemedigini degil, NE istedigini yaz.")
