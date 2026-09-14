import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
from openai import OpenAI


# ==========================================
# 基本設定
# ==========================================

st.set_page_config(
    page_title="住所フリガナチェック",
    page_icon="✅",
    layout="centered"
)

st.title("住所フリガナ判定テスト")

st.caption(
    "契約書の写真を入れて、「ご住所」に対応するフリガナ欄に"
    "記入があるかだけを判定します。"
)


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
# 画像処理
# ==========================================

def prepare_image(img):

    # iPhone等の写真の向きを補正
    img = ImageOps.exif_transpose(img)

    img = img.convert("RGB")

    # 大きすぎる場合だけ縮小
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
# AI判定
# ==========================================

def check_address_furigana(images):

    prompt = """
あなたは日本の契約書の「記入漏れチェック」を行います。

今回確認する項目は1つだけです。

【確認対象】
「ご住所」に対応するフリガナ記入欄

重要：
この判定では、フリガナの内容を読み取る必要はありません。

確認したいのは、

「ご住所に対応するフリガナ欄に、
手書きの文字が存在するか」

だけです。


【必ず守るルール】

1.
まず契約書内の「ご住所」という印字を探してください。

2.
その「ご住所」に対応している
住所用のフリガナ記入欄だけを確認してください。

3.
フリガナ欄に手書き文字が明確に存在すれば
has_entry = true

4.
対象のフリガナ欄が見えていて、
何も記入されていなければ
has_entry = false

5.
写真が遠い、ぼやけている、対象欄が写っていないなど、
対象のフリガナ欄そのものを確認できない場合は
uncertain = true

6.
フリガナが正しいかどうかは確認しません。

7.
住所との読みが一致しているかも確認しません。

8.
氏名のフリガナは絶対に使わないでください。

9.
住所本文に文字が書かれていても、
フリガナ欄が空欄なら has_entry = false です。

10.
近くにある別の手書き文字を、
フリガナの記入として扱わないでください。

11.
印刷されている文字は「記入あり」に含めません。
手書きで記入された文字だけを確認してください。

12.
画像が横向き・縦向き・上下逆でも、
書類の向きを理解して判定してください。

13.
複数画像がある場合は、
同じ契約書の全体写真やアップ写真として扱い、
最も確認しやすい画像を使ってください。

推測は禁止です。

対象欄を確認できなければ、
無理に「記入あり」「未記入」とせず
uncertain = true にしてください。
"""

    schema = {
        "name": "address_furigana_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "visible": {
                    "type": "boolean"
                },
                "has_entry": {
                    "type": "boolean"
                },
                "uncertain": {
                    "type": "boolean"
                }
            },
            "required": [
                "visible",
                "has_entry",
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
    "契約書の写真を選択",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)


if uploaded_files:

    images = []

    for file in uploaded_files:

        img = Image.open(file)

        img = prepare_image(img)

        images.append(img)

    st.subheader("テスト画像")

    for img in images:

        st.image(
            img,
            use_container_width=True
        )


    if st.button(
        "住所フリガナを判定",
        type="primary",
        use_container_width=True
    ):

        with st.spinner("判定中..."):

            try:

                result = check_address_furigana(
                    images
                )

            except Exception as e:

                st.error(
                    f"判定中にエラーが発生しました：{e}"
                )

                st.stop()


        st.divider()


        # ==================================
        # 結果表示
        # ==================================

        if result["uncertain"] or not result["visible"]:

            st.warning(
                "🔍 ご住所フリガナ：判定できません"
            )

            st.caption(
                "ご住所のフリガナ欄がはっきり写るように、"
                "少し近づいて撮影してください。"
            )


        elif result["has_entry"]:

            st.success(
                "✅ ご住所フリガナ：記入あり"
            )


        else:

            st.error(
                "❌ ご住所フリガナ：未記入"
            )


        with st.expander("判定データ"):

            st.json(result)
