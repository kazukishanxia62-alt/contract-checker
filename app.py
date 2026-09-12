import streamlit as st
from PIL import Image, ImageOps
import numpy as np
import cv2
import pandas as pd

st.set_page_config(page_title="契約書チェック（試作）", page_icon="✅", layout="wide")

st.title("契約書 記入漏れチェック（試作）")
st.caption("営業チェック → 自動チェック → マネージャー最終確認、を想定したMVPです。")
st.warning(
    "この試作は、指定欄に記入があるかを画像処理で判定します。"
    "契約可否や法的判断は行いません。実データ運用前に会社の承認・情報管理確認が必要です。"
)

# 写真は毎回 1536x1152 にそろえてから判定します。
# mode:
#   blue = 青ペンの記入を検出
#   dark = 黒ペンの手書きを検出（印刷罫線をできるだけ除去）
CHECKS = {
    "1枚目（役務事業者控）": {
        "役務提供期間": {
            "roi": (170, 785, 560, 870),
            "mode": "blue",
        },
        "受領サイン": {
            # 「受領サイン→」の右側にある黒ペン署名だけを見る
            "roi": (1215, 150, 1400, 195),
            "mode": "dark",
        },
        "数量計": {
            "roi": (775, 570, 845, 800),
            "mode": "blue",
        },
    },
    "2枚目（クレジット契約書）": {
        "提供期間等": {
            # 「役務提供期間（権利の移転期間）」ではなく、
            # 特定商取引内容欄の「提供期間 20__年__月__日迄」を見る
            "roi": (1000, 235, 1145, 285),
            "mode": "blue",
        },
        "特定商取引法42条欄": {
            "roi": (1170, 150, 1385, 255),
            "mode": "blue",
        },
        "フリガナ": {
            "roi": (150, 115, 420, 165),
            "mode": "blue",
        },
        "ヶ月": {
            "roi": (420, 355, 650, 440),
            "mode": "blue",
        },
    },
}

def normalize_image(img):
    img = ImageOps.exif_transpose(img).convert("RGB")
    return img.resize((1536, 1152))

def get_crop(img, roi):
    x1, y1, x2, y2 = roi
    return np.array(img)[y1:y2, x1:x2]

def blue_mask(crop_rgb):
    hsv = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2HSV)
    lower = np.array([85, 35, 35])
    upper = np.array([145, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)

    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask

def dark_handwriting_mask(crop_rgb):
    """
    黒ペンの署名用。
    暗い画素を抽出した後、長い罫線・枠線をできるだけ除去します。
    """
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)

    # 黒ペン + 黒印刷を抽出
    binary = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY_INV)[1]

    h, w = binary.shape

    # 長い横線・縦線を抽出して除去
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(12, w // 3), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(10, h // 2))
    )

    horizontal_lines = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, horizontal_kernel
    )
    vertical_lines = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, vertical_kernel
    )

    cleaned = cv2.subtract(binary, horizontal_lines)
    cleaned = cv2.subtract(cleaned, vertical_lines)

    # 小さなノイズを除去
    cleaned = cv2.morphologyEx(
        cleaned, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)
    )

    return cleaned

def analyze_roi(img, item, blue_threshold):
    roi = item["roi"]
    mode = item["mode"]

    crop = get_crop(img, roi)
    if crop.size == 0:
        return 0.0, False, None, None, mode

    if mode == "blue":
        mask = blue_mask(crop)
        ratio = float((mask > 0).mean())
        detected = ratio >= blue_threshold
    else:
        mask = dark_handwriting_mask(crop)
        ratio = float((mask > 0).mean())

        # 黒署名は青インク比率とは別基準で判定
        detected = ratio >= 0.03

    overlay = crop.copy()
    detected_pixels = mask > 0

    # 検出した部分を赤く強調
    overlay[detected_pixels] = (255, 80, 80)

    return (
        ratio,
        detected,
        Image.fromarray(crop),
        Image.fromarray(overlay),
        mode,
    )

def check_document(uploaded, checks, blue_threshold):
    img = normalize_image(Image.open(uploaded))

    results = []
    for name, item in checks.items():
        ratio, detected, crop, preview, mode = analyze_roi(
            img, item, blue_threshold
        )
        results.append(
            {
                "項目": name,
                "判定": "✅ 記入あり" if detected else "❌ 要確認",
                "検出率": round(ratio * 100, 3),
                "方式": "青ペン" if mode == "blue" else "黒ペン",
                "_crop": crop,
                "_preview": preview,
            }
        )

    return img, results

with st.sidebar:
    st.header("判定設定")

    threshold_pct = st.slider(
        "青インク検出しきい値（%）",
        min_value=0.01,
        max_value=1.00,
        value=0.12,
        step=0.01,
        help="青ペンで記入する欄にだけ使うしきい値です。受領サインは黒ペン用の別判定です。",
    )
    blue_threshold = threshold_pct / 100

    st.caption("※ 受領サインは黒ペン専用の判定ロジックを使用します。")

    st.divider()
    st.write("対象項目")

    for doc, fields in CHECKS.items():
        st.markdown(f"**{doc}**")
        for field, item in fields.items():
            pen = "黒" if item["mode"] == "dark" else "青"
            st.write(f"・{field}（{pen}）")

c1, c2 = st.columns(2)

with c1:
    st.subheader("1枚目")
    f1 = st.file_uploader(
        "役務事業者控をアップロード",
        type=["jpg", "jpeg", "png"],
        key="f1",
    )

with c2:
    st.subheader("2枚目")
    f2 = st.file_uploader(
        "クレジット契約書をアップロード",
        type=["jpg", "jpeg", "png"],
        key="f2",
    )

if st.button("🔍 自動チェック", type="primary", use_container_width=True):
    if not f1 and not f2:
        st.error("少なくとも1枚アップロードしてください。")
    else:
        all_rows = []
        detail_blocks = []

        if f1:
            img1, res1 = check_document(
                f1,
                CHECKS["1枚目（役務事業者控）"],
                blue_threshold,
            )
            for r in res1:
                all_rows.append(
                    {
                        "書類": "1枚目",
                        "項目": r["項目"],
                        "判定": r["判定"],
                        "検出方式": r["方式"],
                        "検出率(%)": r["検出率"],
                    }
                )
            detail_blocks.append(("1枚目", img1, res1))

        if f2:
            img2, res2 = check_document(
                f2,
                CHECKS["2枚目（クレジット契約書）"],
                blue_threshold,
            )
            for r in res2:
                all_rows.append(
                    {
                        "書類": "2枚目",
                        "項目": r["項目"],
                        "判定": r["判定"],
                        "検出方式": r["方式"],
                        "検出率(%)": r["検出率"],
                    }
                )
            detail_blocks.append(("2枚目", img2, res2))

        df = pd.DataFrame(all_rows)
        ng = int(df["判定"].str.contains("要確認").sum())

        if ng == 0:
            st.success(
                "指定したチェック項目はすべて『記入あり』判定です。"
                "マネージャーの最終確認へ進んでください。"
            )
        else:
            st.error(
                f"要確認が {ng} 項目あります。提出前に確認してください。"
            )

        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("判定箇所の確認")

        for docname, fullimg, results in detail_blocks:
            with st.expander(
                f"{docname}：チェック箇所を表示",
                expanded=True,
            ):
                for r in results:
                    cc1, cc2 = st.columns([1, 2])

                    with cc1:
                        st.markdown(f"**{r['項目']}**")
                        st.write(r["判定"])
                        st.caption(
                            f"検出方式: {r['方式']} / 検出率: {r['検出率']}%"
                        )

                    with cc2:
                        if r["_preview"] is not None:
                            st.image(
                                r["_preview"],
                                caption="赤く強調された部分＝記入として検出した画素",
                                use_container_width=True,
                            )

st.divider()

st.markdown(
    """
### 今回の修正
- **受領サイン**：青ペン判定から、黒ペン手書き判定に変更
- **提供期間等**：上部の「役務提供期間」ではなく、特定商取引内容欄の「提供期間」を見るように位置を修正
- 青ペン欄と黒ペン欄で、判定方式を分けています

### この試作の位置づけ
- **得意**：決まった書式・決まった欄の「書き忘れ」検知
- **苦手**：書いた内容そのものが正しいかの判断
- 次の段階ではOCRを追加して、**日付一致・金額計算・月数一致**まで確認できます。
"""
)
