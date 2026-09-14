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
    page_title="住所チェック",
    page_icon="🏠",
    layout="centered"
)

st.title("ご契約者住所テスト")

st.caption(
    "「ご契約者のご住所」が、都道府県から記入されているかだけを確認します。"
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
# AI判定
# ==========================================

def check_address_prefecture(images):

    prompt = """
あなたは日本の契約書の「記入漏れチェック」を行います。

今回確認する項目は1つだけです。

【確認対象】

「ご契約者のご住所」

という印刷された項目に対応する、
契約者本人の住所記入欄です。


【このチェックの目的】

住所が実在するか、
住所の内容が正しいかを審査するものではありません。

確認したいのは、

「住所の先頭に、都道府県名が手書きで明示されているか」

だけです。


==================================================
最重要ルール
==================================================

都道府県名そのものを回答する必要はありません。

「何県か」を推測・回答しないでください。

確認するのは、

・住所の先頭に都道府県名の記入が存在する
・住所が市区町村から始まっていて都道府県名が省略されている

のどちらかです。


==================================================
対象欄
==================================================

必ず最初に、印刷された

「ご契約者のご住所」

という項目を探してください。

その項目に対応する住所記入欄だけを確認してください。


次の欄は絶対に使用しないでください。

・関係者情報の「ご住所」
・勤務先の「所在地」
・派遣先や会社の住所
・銀行関連の欄
・その他の住所欄


==================================================
「都道府県あり」の判定
==================================================

住所の先頭部分に、

北海道
○○県
東京都
○○府

のような都道府県名が、
手書き住所の一部として実際に書かれていることを
視覚的に確認できた場合だけ、

prefecture_explicit = true

にしてください。


例えば、

大阪府 ＋ 大阪市 ＋ その後の住所

兵庫県 ＋ 神戸市 ＋ その後の住所

東京都 ＋ 新宿区 ＋ その後の住所

北海道 ＋ 札幌市 ＋ その後の住所

のように、

都道府県 → 市区町村

という順番で手書きされていることが
視覚的に確認できる場合です。


==================================================
「都道府県なし」の判定
==================================================

住所欄が、

○○市
○○区
○○町
○○村

など、市区町村から直接始まっていて、
その前に都道府県名の手書きが存在しない場合は、

prefecture_explicit = false

にしてください。


非常に重要：

市区町村名から都道府県を推測してはいけません。

例えば、

「神戸市」と読めても
「兵庫県が省略されているだけだろう」

と補完してはいけません。

実際に「兵庫県」が書かれていなければ
prefecture_explicit = false です。


==================================================
印刷文字について
==================================================

用紙に最初から印刷されている文字は
住所の記入として扱わないでください。

特に、

「都」
「道」
「府」
「県」

などの印刷文字が近くにあっても、

それだけを根拠に
prefecture_explicit = true

にしてはいけません。

手書き住所の中に都道府県名が存在することが必要です。


==================================================
判定できない場合
==================================================

次の場合だけ uncertain = true にしてください。

・住所欄が写真に写っていない
・文字が小さすぎる
・ピンぼけしている
・住所の先頭部分が切れている
・手書きか印刷か区別できない
・都道府県名があるか視覚的に判断できない

判断できない場合は推測しないでください。


==================================================
出力項目
==================================================

address_field_visible

「ご契約者のご住所」の対象欄を
画像上で確認できるか。


has_entry

その住所欄に手書きの住所が存在するか。


prefecture_explicit

住所の先頭に都道府県名が
手書きで明示されていることを確認できたか。


uncertain

画像から確実に判断できないか。


==================================================
最後の確認
==================================================

prefecture_explicit = true にする前に、

「私は、対象となる契約者住所欄の手書き住所の先頭に、
都道府県名が実際に書かれていることを
画像上で確認できているか？」

を確認してください。

推測なら true にしないでください。
"""

    schema = {
        "name": "address_prefecture_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "address_field_visible": {
                    "type": "boolean"
                },
                "has_entry": {
                    "type": "boolean"
                },
                "prefecture_explicit": {
                    "type": "boolean"
                },
                "uncertain": {
                    "type": "boolean"
                }
            },
            "required": [
                "address_field_visible",
                "has_entry",
                "prefecture_explicit",
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
        "住所をチェック",
        type="primary",
        use_container_width=True
    ):

        with st.spinner("判定中..."):

            try:

                result = check_address_prefecture(
                    images
                )

            except Exception as e:

                st.error(
                    f"判定中にエラーが発生しました：{e}"
                )

                st.stop()


        st.divider()

        st.subheader("判定結果")


        # ==================================
        # 結果
        # ==================================

        if (
            result["uncertain"]
            or not result["address_field_visible"]
        ):

            st.warning(
                "🔍 ご契約者住所：判定できません"
            )

            st.caption(
                "住所の先頭部分がはっきり写るように撮影してください。"
            )


        elif not result["has_entry"]:

            st.error(
                "❌ ご契約者住所：未記入"
            )


        elif result["prefecture_explicit"]:

            st.success(
                "✅ ご契約者住所：都道府県から記入されています"
            )


        else:

            st.error(
                "❌ ご契約者住所：都道府県が省略されています"
            )


        with st.expander("判定データ"):

            st.json(result)
