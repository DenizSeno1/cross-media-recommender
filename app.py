"""Streamlit gozlem UI — INCE ve ISLEVSEL (cila DEGIL, o en son).

Neden simdi: recall@k retrieval'i olcuyor, "iyi oneri mi"yi olcmuyor. O soruyu
KULLANARAK gozlemliyoruz. oneri() yapisal dict donuyor -> burasi sadece render
eder; motor arkada degisse de (rerank/medya/hyde) dict sekli sabit, UI kirilmaz.

Kosmak:  streamlit run faz4/faz4_gun12_15/app.py
"""

import hashlib
import io

import streamlit as st

import config
import llm
import oneri
import retrieval
import veri

st.set_page_config(page_title="Capraz-Medya Onerici", page_icon="🎬", layout="centered")


@st.cache_resource(show_spinner="Model + index isitiliyor (ilk acilista birkac dk)...")
def isit():
    """Agir init (e5 + 7807 index) bir kez; Streamlit her etkilesimde script'i
    bastan kosar, cache_resource ile model/index yeniden yuklenmez."""
    retrieval._hazirla()
    return True


isit()

st.title("🎬 Capraz-Medya Onerici")
st.caption("Anime · film · kitap — icerik-tabanli HyDE retrieval. Gozlem arayuzu.")

if config.DEMO:
    st.info(
        "**Demo modu.** Vektorler onceden hesaplanmis (7807 kayit, tam corpus'tan) ve "
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
    medya_sec = st.selectbox("Medya", ["hepsi", "anime", "film", "kitap"], index=0,
                             help="Cross-media: 'anime' sec -> sadece anime; 'film' -> Monster gibi film")
    k = st.slider("Kac oneri (k)", 1, 10, config.TOP_K)
    rerank = st.checkbox("Rerank (cross-encoder)", value=config.RERANK_AKTIF,
                         help="recall@5'i ~2x yapar AMA CPU'da dakikalarca surer / 4GB GPU'da VRAM sikisir. Deneysel.")
    if rerank:
        st.warning("Rerank acik: CPU'da her sorgu dakikalarca surebilir.")

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

    st.subheader("Oneriler")
    for r in sonuc["oneriler"]:
        # C9: skorun HANGI olcek oldugunu yaz. rerank acikken _skor cross-encoder
        # skoru (0.0X bandi), kapaliyken kosinus (0.9 bandi). Ayni ismi tasiyan iki
        # ayri olcek, disaridan bakan "sistem bozuk" diye okuyor (09-05, dis inceleme).
        olcek = "rerank" if (rerank and not profil_modu) else "kosinus"
        ada = f"  ·  ada `{r['_ada']}`" if "_ada" in r else ""
        st.markdown(
            f"**[{veri.baslik(r)}]({veri.link(r)})**  ·  `{r['media']}`  ·  "
            f"{olcek} `{r['_skor']:.3f}`{ada}"
        )
    if not sonuc["oneriler"]:
        st.info("Bu medya filtresinde sonuc havuzda cikmadi — filtreyi genislet.")

    st.subheader("Neden bu liste?")
    st.write(sonuc["aciklama"])
    st.caption(f"LLM: {llm.sayac.ozet()}")

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
