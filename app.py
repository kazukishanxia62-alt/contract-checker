import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
from openai import OpenAI


st.set_page_config(
    page_title="業種チェック",
    page_icon="✅",
    layout="centered"
)

st.title("業種 選択チェック")
st.caption("「業種」欄の選択肢に手書きの○があるかだけを確認します。")


# ==========================================
# OpenAI
# ==========================================

try:
    client = OpenAI(
        api_key=st.secrets["OPENAI_API_KEY"]
    )
except Exception:
    st.error("OPENAI_API_KEYを確認してください。")
    st.stop()


MODEL = "gpt-5.4-mini"


# ==========================================
# 画像
# ==========================================

def prepare_image(img):

    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    if max(img.size) > 2400:
        img.thumbnail(
            (2400, 2400),
            Image.Resampling.LANCZOS
        )

    return img


def image_to_data_url(img):

    buffer = BytesIO()

    img.save(
        buffer,
        format="JPEG",
        quality=95
    )

    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


# ==========================================
# 業種だけ判定
# ==========================================

def check_industry(images):

    prompt = """
これは日本のクレジット申込書です。

今回確認するのは1項目だけです。


【確認対象】

ご契約者本人の勤務先情報にある
印刷された「業種」欄。


【質問】

「業種」欄の選択肢のどれかに、
手書きの○が付いていますか？


これだけを判定してください。


========================================
手順
========================================

1.

まず印刷された「業種」という文字を探してください。


2.

「業種」という文字のすぐ右側にある、
業種の選択肢が並んでいる範囲を確認してください。


3.

その範囲内の選択肢のどれかに、

青色または黒色のペンなどで付けられた
手書きの○が存在するかだけを確認してください。


4.

手書きの○が1つでも明確に存在する場合、

has_circle = true

にしてください。


5.

業種欄を確認できて、
どの選択肢にも手書きの○が存在しない場合、

has_circle = false

にしてください。


========================================
絶対にしないこと
========================================

どの業種が選択されているかを
読み取る必要はありません。

業種名を回答しないでください。

○の個数も数えないでください。


また、この書類には業種以外にも、

・性別
・雇用形態
・住居
・世帯状況
・続柄
・銀行関連

などに手書きの○があります。


これらは完全に無視してください。


「書類のどこかに○がある」

ではなく、

必ず

「印刷された『業種』に直接対応する
業種選択肢の範囲内に○がある」

ことを確認してください。


========================================
重要
========================================

印刷された文字の丸い部分、

数字の0、

罫線、

印刷された記号、

近くにある別項目の○

は、

業種の○として扱わないでください。


========================================
判定不能
========================================

次の場合だけ uncertain = true にしてください。

・業種欄そのものが写真に写っていない
・業種欄が小さすぎて見えない
・ピンぼけしている
・業種欄が途中で切れている
・手書きの○かどうか視覚的に判断できない


判断できる場合は uncertain = false です。


========================================
出力
========================================

field_visible

= 印刷された「業種」と、
  その選択肢部分を確認できる。


has_circle

= 業種の選択肢のどれかに
  手書きの○が存在する。


uncertain

= 確実に判断できない。


========================================
最終確認
========================================

has_circle = true にする前に、

「その○は本当に
印刷された『業種』の選択肢の中にあるか？」

だけをもう一度確認してください。
"""

    schema = {
        "name": "industry_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "field_visible": {
                    "type": "boolean"
                },
                "has_circle": {
                    "type": "boolean"
                },
                "uncertain": {
                    "type": "boolean"
                }
            },
            "required": [
                "field_visible",
                "has_circle",
                "uncertain"
            ],
            "additionalProperties": False
        }
    }

    content = [
        {
            "type": "text",
            "text": prompt
        }
    ]

    for img in images:

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_to_data_url(img),
                    "detail": "high"
                }
            }
        )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": schema
        }
    )

    return json.loads(
        response.choices[0].message.content
    )


# ==========================================
# 画面
# ==========================================

uploaded_files = st.file_uploader(
    "クレジット申込書の写真を選択",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)


if uploaded_files:

    images = []

    for file in uploaded_files:

        img = Image.open(file)
        img = prepare_image(img)
        images.append(img)

    st.subheader("判定する写真")

    for img in images:

        st.image(
            img,
            use_container_width=True
        )


    if st.button(
        "業種をチェック",
        type="primary",
        use_container_width=True
    ):

        with st.spinner("判定中..."):

            try:
                result = check_industry(images)

            except Exception as e:

                st.error(
                    f"判定中にエラーが発生しました：{e}"
                )
                st.stop()


        st.divider()
        st.subheader("判定結果")


        if (
            result["uncertain"]
            or not result["field_visible"]
        ):

            st.warning(
                "🔍 業種：判定できません"
            )


        elif result["has_circle"]:

            st.success(
                "✅ 業種：選択あり"
            )


        else:

            st.error(
                "❌ 業種：未選択"
            )


        with st.expander("判定データ"):
            st.json(result)
