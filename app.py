"""Streamlit gozlem UI — INCE ve ISLEVSEL (cila DEGIL, o en son).

Neden simdi: recall@k retrieval'i olcuyor, "iyi oneri mi"yi olcmuyor. O soruyu
KULLANARAK gozlemliyoruz. oneri() yapisal dict donuyor -> burasi sadece render
eder; motor arkada degisse de (rerank/medya/hyde) dict sekli sabit, UI kirilmaz.

Kosmak:  streamlit run faz4/faz4_gun12_15/app.py
"""

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

# --- sidebar: motor knoblari (degistir -> gozlemle) ---
with st.sidebar:
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
                          placeholder="orn: olum ve yas uzerine sakin fantastik yolculuk")
    gonder = st.form_submit_button("Oner")

if gonder and sorgu.strip():
    medya = None if medya_sec == "hepsi" else medya_sec
    with st.spinner("HyDE -> retrieval -> aciklama..."):
        sonuc = oneri.oneri(sorgu, k=k, medya=medya, rerank=rerank)

    st.subheader("Oneriler")
    for r in sonuc["oneriler"]:
        st.markdown(
            f"**[{veri.baslik(r)}]({veri.link(r)})**  ·  `{r['media']}`  ·  skor `{r['_skor']:.3f}`"
        )
    if not sonuc["oneriler"]:
        st.info("Bu medya filtresinde sonuc havuzda cikmadi — filtreyi genislet.")

    st.subheader("Neden bu liste?")
    st.write(sonuc["aciklama"])
    st.caption(f"LLM: {llm.sayac.ozet()}")
elif gonder:
    st.info("Once bir sorgu yaz.")
