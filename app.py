
import streamlit as st
from PIL import Image, ImageOps
import numpy as np
import cv2
import pandas as pd

# HEIC対応（入っていれば有効化）
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

st.set_page_config(page_title="契約書チェック", page_icon="✅", layout="wide")

st.title("契約書 記入漏れチェック")
st.caption("スマホ撮影 → 用紙自動補正 → 記入漏れチェック")
st.warning(
    "この試作は提出前の補助チェックです。契約可否や法的判断は行いません。"
    "実データ運用前に会社の承認・情報管理確認が必要です。"
)

TARGET_W = 1536
TARGET_H = 1152

# ここは「正面に補正された契約書」を基準に見る位置
CHECKS = {
    "1枚目（役務事業者控）": {
        "役務提供期間": {"roi": (170, 785, 560, 870), "mode": "blue"},
        "受領サイン": {"roi": (1215, 150, 1400, 205), "mode": "dark"},
        "数量計": {"roi": (775, 570, 845, 800), "mode": "blue"},
    },
    "2枚目（クレジット契約書）": {
        "提供期間等": {"roi": (1000, 235, 1145, 285), "mode": "blue"},
        "特定商取引法42条欄": {"roi": (1170, 150, 1385, 255), "mode": "blue"},
        "フリガナ": {"roi": (150, 115, 420, 165), "mode": "blue"},
        "ヶ月": {"roi": (420, 355, 650, 440), "mode": "blue"},
    },
}

def order_points(pts):
    pts = np.array(pts, dtype="float32")
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    rect[0] = pts[np.argmin(s)]      # top-left
    rect[2] = pts[np.argmax(s)]      # bottom-right
    rect[1] = pts[np.argmin(diff)]   # top-right
    rect[3] = pts[np.argmax(diff)]   # bottom-left
    return rect

def four_point_transform(image_rgb, pts):
    rect = order_points(pts)
    dst = np.array([
        [0, 0],
        [TARGET_W - 1, 0],
        [TARGET_W - 1, TARGET_H - 1],
        [0, TARGET_H - 1],
    ], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image_rgb, M, (TARGET_W, TARGET_H))
    return warped

def detect_document(image_rgb):
    """
    写真内で一番大きい「紙らしい四角形」を探して正面補正する。
    見つからない時は、最大輪郭の回転矩形で補正を試みる。
    """
    h0, w0 = image_rgb.shape[:2]
    scale = 1200 / max(h0, w0)
    if scale < 1:
        small = cv2.resize(image_rgb, (int(w0 * scale), int(h0 * scale)))
    else:
        small = image_rgb.copy()
        scale = 1.0

    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    # 白い紙を拾いやすくする
    edges = cv2.Canny(gray, 45, 140)
    edges = cv2.dilate(edges, np.ones((3,3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    img_area = small.shape[0] * small.shape[1]
    candidate = None

    for c in contours[:30]:
        area = cv2.contourArea(c)
        if area < img_area * 0.08:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2).astype("float32")
            candidate = pts
            break

    if candidate is None and contours:
        # fallback: 最大輪郭を回転矩形にする
        for c in contours[:10]:
            area = cv2.contourArea(c)
            if area >= img_area * 0.08:
                rect = cv2.minAreaRect(c)
                candidate = cv2.boxPoints(rect).astype("float32")
                break

    if candidate is None:
        return None, None

    pts_full = candidate / scale
    warped = four_point_transform(image_rgb, pts_full)

    # 横長の契約書を想定。縦長になった場合は90度回転
    if warped.shape[0] > warped.shape[1]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        warped = cv2.resize(warped, (TARGET_W, TARGET_H))

    return warped, pts_full

def load_image(uploaded):
    img = Image.open(uploaded)
    img = ImageOps.exif_transpose(img).convert("RGB")
    return np.array(img)

def blue_mask(crop_rgb):
    hsv = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2HSV)
    lower = np.array([85, 30, 30])
    upper = np.array([145, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2,2), np.uint8))
    return mask

def dark_handwriting_mask(crop_rgb):
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)

    # 黒系文字
    binary = cv2.threshold(gray, 115, 255, cv2.THRESH_BINARY_INV)[1]
    h, w = binary.shape

    # 罫線を除去
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 3), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 2)))
    hlines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, hk)
    vlines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vk)

    cleaned = cv2.subtract(binary, hlines)
    cleaned = cv2.subtract(cleaned, vlines)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, np.ones((2,2), np.uint8))
    return cleaned

def analyze_roi(rectified_rgb, item, blue_threshold):
    x1, y1, x2, y2 = item["roi"]
    crop = rectified_rgb[y1:y2, x1:x2]
    mode = item["mode"]

    if crop.size == 0:
        return 0.0, False, None, None

    if mode == "blue":
        mask = blue_mask(crop)
        ratio = float((mask > 0).mean())
        detected = ratio >= blue_threshold
    else:
        mask = dark_handwriting_mask(crop)
        ratio = float((mask > 0).mean())
        detected = ratio >= 0.03

    overlay = crop.copy()
    overlay[mask > 0] = (255, 70, 70)
    return ratio, detected, Image.fromarray(crop), Image.fromarray(overlay)

def check_document(uploaded, checks, blue_threshold):
    raw = load_image(uploaded)
    rectified, corners = detect_document(raw)

    if rectified is None:
        # 最後のfallback
        rectified = cv2.resize(raw, (TARGET_W, TARGET_H))
        auto_corrected = False
    else:
        auto_corrected = True

    results = []
    for name, item in checks.items():
        ratio, detected, crop, overlay = analyze_roi(rectified, item, blue_threshold)
        results.append({
            "項目": name,
            "判定": "✅ 記入あり" if detected else "❌ 要確認",
            "検出方式": "黒ペン" if item["mode"] == "dark" else "青ペン",
            "検出率": round(ratio * 100, 3),
            "_crop": crop,
            "_overlay": overlay,
        })

    return raw, rectified, auto_corrected, results

def pick_input(label, key_prefix):
    st.markdown(f"### {label}")
    mode = st.radio(
        f"{label}の入力方法",
        ["写真ライブラリ", "今撮影する"],
        horizontal=True,
        key=f"{key_prefix}_mode",
        label_visibility="collapsed",
    )

    if mode == "写真ライブラリ":
        return st.file_uploader(
            "写真を選択",
            type=["jpg", "jpeg", "png", "heic", "heif"],
            key=f"{key_prefix}_file",
        )
    else:
        return st.camera_input(
            "カメラで撮影",
            key=f"{key_prefix}_camera",
        )

with st.sidebar:
    st.header("判定設定")
    threshold_pct = st.slider(
        "青インク検出しきい値（%）",
        0.01, 1.00, 0.12, 0.01,
        help="青ペン欄だけに使います。"
    )
    blue_threshold = threshold_pct / 100
    st.caption("受領サインは黒ペン専用ロジックです。")
    st.divider()
    st.markdown("**今回の改良**")
    st.write("・用紙の四隅を自動検出")
    st.write("・斜め撮影を正面補正")
    st.write("・余白や背景を除外")
    st.write("・写真ライブラリ / カメラ対応")

c1, c2 = st.columns(2)
with c1:
    f1 = pick_input("1枚目", "doc1")
with c2:
    f2 = pick_input("2枚目", "doc2")

if st.button("🔍 自動チェック", type="primary", use_container_width=True):
    if not f1 and not f2:
        st.error("少なくとも1枚選択または撮影してください。")
    else:
        all_rows = []
        blocks = []

        if f1:
            raw, rectified, corrected, res = check_document(
                f1, CHECKS["1枚目（役務事業者控）"], blue_threshold
            )
            blocks.append(("1枚目", raw, rectified, corrected, res))
            for r in res:
                all_rows.append({
                    "書類": "1枚目",
                    "項目": r["項目"],
                    "判定": r["判定"],
                    "方式": r["検出方式"],
                    "検出率(%)": r["検出率"],
                })

        if f2:
            raw, rectified, corrected, res = check_document(
                f2, CHECKS["2枚目（クレジット契約書）"], blue_threshold
            )
            blocks.append(("2枚目", raw, rectified, corrected, res))
            for r in res:
                all_rows.append({
                    "書類": "2枚目",
                    "項目": r["項目"],
                    "判定": r["判定"],
                    "方式": r["検出方式"],
                    "検出率(%)": r["検出率"],
                })

        df = pd.DataFrame(all_rows)
        ng = int(df["判定"].str.contains("要確認").sum())

        if ng == 0:
            st.success("指定したチェック項目はすべて『記入あり』判定です。")
        else:
            st.error(f"要確認が {ng} 項目あります。提出前に確認してください。")

        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("用紙補正結果")
        for name, raw, rectified, corrected, res in blocks:
            with st.expander(f"{name}：補正画像と判定箇所", expanded=True):
                st.caption(
                    "✅ 用紙を自動検出して正面補正しました"
                    if corrected else
                    "⚠️ 用紙の自動検出に失敗したため、画像全体をそのまま使用しました"
                )
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.image(raw, caption="元の写真", use_container_width=True)
                with cc2:
                    st.image(rectified, caption="自動補正後", use_container_width=True)

                st.markdown("#### 判定箇所")
                for r in res:
                    a, b = st.columns([1, 2])
                    with a:
                        st.markdown(f"**{r['項目']}**")
                        st.write(r["判定"])
                        st.caption(
                            f"{r['検出方式']} / 検出率 {r['検出率']}%"
                        )
                    with b:
                        if r["_overlay"] is not None:
                            st.image(
                                r["_overlay"],
                                caption="赤＝記入として検出した部分",
                                use_container_width=True,
                            )

st.divider()
st.markdown("""
### この版で改善したこと
- 契約書が写真の中央にない場合でも、用紙の四隅を探します
- 斜め・台形になった写真を正面向きに補正します
- 黒い背景や大きな余白があっても、契約書だけを切り出してから判定します
- iPhoneから「写真ライブラリ」または「今撮影する」を選べます

### まだ注意が必要なケース
- 用紙の一部が画面外に切れている
- 影が強く、用紙の輪郭が消えている
- 契約書が極端に小さく写っている
- スクリーンショット内に写真アプリUIまで含まれている

その場合は「契約書の四隅が全部写る」「できるだけ真正面から」の写真が最も安定します。
""")
