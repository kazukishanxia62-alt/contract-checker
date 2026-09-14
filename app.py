import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
from openai import OpenAI


st.set_page_config(
    page_title="住所テスト",
    page_icon="🏠"
)

st.title("ご契約者住所テスト")

st.write(
    "「ご契約者のご住所」が、都道府県名から記入されているかだけを確認します。"
)


client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

MODEL = "gpt-5.4-mini"


PREFECTURES = [
    "北海道",
    "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都",
    "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県",
    "長野県", "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県",
    "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県",
    "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県",
    "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県",
    "大分県", "宮崎県", "鹿児島県", "沖縄県"
]


def image_to_data_url(img):

    buf = BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=95
    )

    encoded = base64.b64encode(
        buf.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


def address_schema():

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "address_check",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "address_field_visible": {
                        "type": "boolean"
                    },
                    "has_handwriting": {
                        "type": "boolean"
                    },
                    "prefecture_written": {
                        "type": "boolean"
                    },
                    "prefecture": {
                        "type": "string"
                    },
                    "uncertain": {
                        "type": "boolean"
                    }
                },
                "required": [
                    "address_field_visible",
                    "has_handwriting",
                    "prefecture_written",
                    "prefecture",
                    "uncertain"
                ],
                "additionalProperties": False
            }
        }
    }


uploaded = st.file_uploader(
    "クレジット申込書の写真を選択",
    type=["jpg", "jpeg", "png"]
)


if uploaded:

    img = Image.open(uploaded)

    img = ImageOps.exif_transpose(
        img
    ).convert("RGB")

    st.image(
        img,
        caption="判定する写真",
        use_container_width=True
    )


    if st.button(
        "住所をチェック",
        type="primary",
        use_container_width=True
    ):

        prompt = """
これは日本語のクレジット申込書です。

今回確認するのは、

「ご契約者のご住所」

という欄だけです。

他の項目は一切判定しないでください。


【このチェックの目的】

住所の内容が正しいか、
実在する住所かを確認するものではありません。

確認したいのは、

「ご契約者のご住所」欄に住所が記入されていて、
さらに都道府県名から書き始められているか

だけです。


【非常に重要】

まず印刷された

「ご契約者のご住所」

という項目名を探してください。

その項目に対応する住所記入欄だけを見てください。


他の住所、

・勤務先所在地
・関係者情報の住所
・銀行住所
・別の住所欄

は絶対に使わないでください。


【判定例】

「大阪府大阪市中央区・・・」
→ prefecture_written=true
→ prefecture="大阪府"

「兵庫県神戸市灘区・・・」
→ prefecture_written=true
→ prefecture="兵庫県"

「東京都新宿区・・・」
→ prefecture_written=true
→ prefecture="東京都"

「北海道札幌市・・・」
→ prefecture_written=true
→ prefecture="北海道"


一方、

「大阪市中央区・・・」
→ prefecture_written=false
→ prefecture=""

「神戸市灘区・・・」
→ prefecture_written=false
→ prefecture=""

です。


市区町村から都道府県を推測してはいけません。

例えば、

「神戸市」

と書いてあるからといって、

兵庫県と推測してはいけません。

実際に住所欄に

「兵庫県」

という文字が書かれている場合だけ

prefecture_written=true

にしてください。


【各項目】

address_field_visible
= 「ご契約者のご住所」の指定欄を画像で確認できる。

has_handwriting
= その住所欄に手書きの住所がある。

prefecture_written
= その手書き住所に都道府県名が実際に書かれている。

prefecture
= 実際に書かれている都道府県名。
  書かれていなければ空文字。

uncertain
= 画像がぼやけているなど、本当に判定できない場合だけtrue。


印刷された「都・道・府・県」などの文字は、
住所の記入として数えないでください。

手書きされた住所だけを見てください。
"""


        with st.spinner("判定中…"):

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_to_data_url(img),
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                response_format=address_schema()
            )


        data = json.loads(
            response.choices[0].message.content
        )


        st.divider()

        st.subheader("判定結果")


        if not data["address_field_visible"]:

            st.info(
                "🔍 ご契約者住所欄を確認できませんでした"
            )

        elif data["uncertain"]:

            st.info(
                "🔍 画像から確実に判定できませんでした"
            )

        elif not data["has_handwriting"]:

            st.error(
                "❌ ご契約者住所が空欄です"
            )

        elif not data["prefecture_written"]:

            st.error(
                "❌ 都道府県名から記入されていません"
            )

        elif data["prefecture"] in PREFECTURES:

            st.success(
                "✅ 都道府県名から記入されています"
            )

            st.write(
                f"検出：**{data['prefecture']}**"
            )

        else:

            st.info(
                "🔍 都道府県名を確実に確認できませんでした"
            )
