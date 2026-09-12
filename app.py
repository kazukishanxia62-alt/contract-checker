
import streamlit as st
from PIL import Image, ImageOps
import numpy as np
import cv2
import pandas as pd

st.set_page_config(page_title="契約書チェック（試作）", page_icon="✅", layout="wide")

st.title("契約書 記入漏れチェック（試作）")
st.caption("営業チェック → 自動チェック → マネージャー最終確認、を想定したMVPです。")
st.warning("この試作は『青い手書き記入が指定欄にあるか』を画像処理で判定します。契約可否や法的判断は行いません。実データ運用前に会社の承認・情報管理確認が必要です。")

# normalized ROI coordinates (x1,y1,x2,y2), based on 1536x1152 example images.
# The app resizes every image to 1536x1152 before checking, so the same form layout can be checked.
DEFAULT_ROIS = {
    "1枚目（役務事業者控）": {
        "役務提供期間": (170, 785, 560, 870),
        "受領サイン": (1110, 135, 1375, 200),
        "数量計": (775, 570, 845, 800),
    },
    "2枚目（クレジット契約書）": {
        "提供期間等": (760, 80, 1110, 220),
        "特定商取引法42条欄": (1170, 150, 1385, 255),
        "フリガナ": (150, 115, 420, 165),
        "ヶ月": (420, 355, 650, 440),
    },
}

def pil_to_bgr(img):
    rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

def normalize_image(img):
    img = ImageOps.exif_transpose(img).convert("RGB")
    return img.resize((1536, 1152))

def blue_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # broad blue/cyan ballpoint range
    lower1 = np.array([85, 35, 35])
    upper1 = np.array([145, 255, 255])
    mask = cv2.inRange(hsv, lower1, upper1)
    # remove tiny isolated noise
    kernel = np.ones((2,2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask

def analyze_roi(img, roi, threshold=0.0012):
    x1,y1,x2,y2 = roi
    crop = np.array(img)[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0, False, None, None
    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    mask = blue_mask(bgr)
    ratio = float((mask > 0).mean())
    detected = ratio >= threshold

    # overlay detected blue in the crop
    overlay = crop.copy()
    blue = mask > 0
    overlay[blue] = (255, 80, 80)  # visible highlight in RGB
    preview = Image.fromarray(overlay)
    return ratio, detected, Image.fromarray(crop), preview

def check_document(label, uploaded, rois, threshold):
    img = Image.open(uploaded)
    img = normalize_image(img)
    results = []
    for name, roi in rois.items():
        ratio, detected, crop, preview = analyze_roi(img, roi, threshold)
        results.append({
            "項目": name,
            "判定": "✅ 記入あり" if detected else "❌ 要確認",
            "青インク比率": round(ratio*100, 3),
            "_crop": crop,
            "_preview": preview,
        })
    return img, results

with st.sidebar:
    st.header("判定設定")
    threshold_pct = st.slider(
        "青インク検出しきい値（%）",
        min_value=0.01, max_value=1.00, value=0.12, step=0.01,
        help="指定欄のうち、青系の画素がこの割合以上なら『記入あり』とします。"
    )
    threshold = threshold_pct / 100
    st.caption("写真の色味やペンによって調整してください。")
    st.divider()
    st.write("対象項目")
    for doc, fields in DEFAULT_ROIS.items():
        st.markdown(f"**{doc}**")
        for f in fields:
            st.write("・" + f)

c1, c2 = st.columns(2)

with c1:
    st.subheader("1枚目")
    f1 = st.file_uploader("役務事業者控をアップロード", type=["jpg","jpeg","png"], key="f1")

with c2:
    st.subheader("2枚目")
    f2 = st.file_uploader("クレジット契約書をアップロード", type=["jpg","jpeg","png"], key="f2")

if st.button("🔍 自動チェック", type="primary", use_container_width=True):
    if not f1 and not f2:
        st.error("少なくとも1枚アップロードしてください。")
    else:
        all_rows = []
        detail_blocks = []
        if f1:
            img1, res1 = check_document("1枚目", f1, DEFAULT_ROIS["1枚目（役務事業者控）"], threshold)
            for r in res1:
                all_rows.append({"書類":"1枚目", "項目":r["項目"], "判定":r["判定"], "青インク比率(%)":r["青インク比率"]})
            detail_blocks.append(("1枚目", img1, res1))
        if f2:
            img2, res2 = check_document("2枚目", f2, DEFAULT_ROIS["2枚目（クレジット契約書）"], threshold)
            for r in res2:
                all_rows.append({"書類":"2枚目", "項目":r["項目"], "判定":r["判定"], "青インク比率(%)":r["青インク比率"]})
            detail_blocks.append(("2枚目", img2, res2))

        df = pd.DataFrame(all_rows)
        ng = int(df["判定"].str.contains("要確認").sum())
        if ng == 0:
            st.success("指定したチェック項目はすべて『記入あり』判定です。マネージャーの最終確認へ進んでください。")
        else:
            st.error(f"要確認が {ng} 項目あります。提出前に確認してください。")

        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("判定箇所の確認")
        for docname, fullimg, results in detail_blocks:
            with st.expander(f"{docname}：チェック箇所を表示", expanded=True):
                for r in results:
                    cc1, cc2 = st.columns([1,2])
                    with cc1:
                        st.markdown(f"**{r['項目']}**")
                        st.write(r["判定"])
                        st.caption(f"青インク比率: {r['青インク比率']}%")
                    with cc2:
                        if r["_preview"] is not None:
                            st.image(r["_preview"], caption="赤く強調された部分＝青系手書きとして検出した画素", use_container_width=True)

st.divider()
st.markdown("""
### この試作の位置づけ
- **得意**：決まった書式・決まった欄の「書き忘れ」検知
- **苦手**：書いた内容が正しいか、日付や金額の意味が正しいかの判断
- 次の段階ではOCRを追加して、**日付一致・金額計算・月数一致**まで確認できます。
""")
