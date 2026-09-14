import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
from openai import OpenAI


st.set_page_config(
    page_title="雇用形態テスト",
    page_icon="🔍",
    layout="centered"
)

st.title("🔍 雇用形態だけ判定テスト")

st.info(
    "今は雇用形態だけをテストします。"
    "氏名・住所・銀行・関係者情報などは一切チェックしません。"
)


client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

MODEL = "gpt-5.4-mini"


def image_to_data_url(img):

    img = ImageOps.exif_transpose(
        img
    ).convert("RGB")

    if max(img.size) > 2600:

        scale = 2600 / max(img.size)

        img = img.resize(
            (
                int(img.width * scale),
                int(img.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

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


def employment_schema():

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "employment_check",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "field_visible": {
                        "type": "boolean"
                    },
                    "circle_count": {
                        "type": "integer"
                    },
                    "selected_label": {
                        "type": "string"
                    },
                    "uncertain": {
                        "type": "boolean"
                    }
                },
                "required": [
                    "field_visible",
                    "circle_count",
                    "selected_label",
                    "uncertain"
                ],
                "additionalProperties": False
            }
        }
    }


def check_employment(img):

    prompt = """
これは日本語のクレジット契約書です。

今回確認するのは、
ご契約者本人の「雇用形態」欄だけです。

他の項目は一切チェックしないでください。

氏名、住所、勤務年数、会社名、所在地、
世帯情報、関係者情報、銀行口座などは
完全に無視してください。


【目的】

雇用形態欄の中で、
どの印刷選択肢に
実際の手書きの○が付いているかを判定します。


【この用紙の雇用形態の選択肢】

・正社員
・派遣社員
・契約社員
・パート・アルバイト
・公務員
・事業者
・主婦
・年金
・学生

などがあります。


【重要】

まず「雇用形態」という印刷見出しを探してください。

次に、その欄の中にある
青ペン・黒ペン等による
手書きの○・囲みだけを探してください。

そして、その手書き○が囲っている
印刷文字を読んでください。


例えば、

正社員の文字の周囲に
青ペンの○がある場合

selected_label="正社員"

です。


「派遣社員」という印刷文字が見えるだけでは
派遣社員を選択したことにはなりません。


印刷文字
罫線
印刷された丸
数字の0
文字の曲線

は手書き○ではありません。


【返答ルール】

雇用形態欄が確認できる
→ field_visible=true

雇用形態欄が写真にない
→ field_visible=false


手書き○が1個
→ circle_count=1
→ selected_labelにその選択肢


手書き○が0個
→ circle_count=0
→ selected_label=""


複数の○
→ circle_countをその個数にする


写真がぼけている等で
本当に判定できない場合だけ
uncertain=true


欄がはっきり見えていて
○がない場合は
uncertain=falseです。
"""

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
        response_format=employment_schema()
    )

    return json.loads(
        response.choices[0].message.content
    )


uploaded = st.file_uploader(
    "雇用形態が写っている写真を1枚選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ]
)


if uploaded:

    image = Image.open(uploaded)

    st.image(
        image,
        caption="テスト画像",
        use_container_width=True
    )


    if st.button(
        "雇用形態を判定",
        type="primary",
        use_container_width=True
    ):

        try:

            with st.spinner(
                "雇用形態だけ確認しています…"
            ):

                data = check_employment(
                    image
                )


            st.divider()


            if not data["field_visible"]:

                st.error(
                    "❌ 雇用形態欄を確認できません"
                )


            elif data["uncertain"]:

                st.warning(
                    "🔍 雇用形態：要確認"
                )


            elif data["circle_count"] == 0:

                st.error(
                    "❌ 雇用形態：○なし"
                )


            elif data["circle_count"] == 1:

                st.success(
                    f"✅ 雇用形態：{data['selected_label']}"
                )


                if "派遣" in data["selected_label"]:

                    st.warning(
                        "派遣社員なので、派遣先・出向先の確認が必要"
                    )

                else:

                    st.info(
                        "派遣先・出向先：対象外"
                    )


            else:

                st.warning(
                    f"⚠️ 雇用形態：○が{data['circle_count']}個あります"
                )


            with st.expander(
                "判定データ"
            ):

                st.json(
                    data
                )


        except Exception as e:

            st.error(
                "エラーが発生しました"
            )

            st.code(
                str(e)
            )
