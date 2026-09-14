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

st.title("🔍 雇用形態テスト")

client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

MODEL = "gpt-5.4-mini"


# =========================================================
# 画像
# =========================================================

def image_to_data_url(img):

    buf = BytesIO()

    img.convert("RGB").save(
        buf,
        format="JPEG",
        quality=95
    )

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buf.getvalue()).decode()
    )


# =========================================================
# Schema
# =========================================================

def schema():

    choice = {
        "type": "object",
        "properties": {
            "label_visible": {
                "type": "boolean"
            },
            "circle_present": {
                "type": "boolean"
            },
            "confidence": {
                "type": "string",
                "enum": [
                    "high",
                    "medium",
                    "low"
                ]
            }
        },
        "required": [
            "label_visible",
            "circle_present",
            "confidence"
        ],
        "additionalProperties": False
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "employment_circle_check",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {

                    "regular": choice,
                    "dispatch": choice,
                    "contract": choice,
                    "parttime": choice,
                    "other": choice,

                    "dispatch_company_visible": {
                        "type": "boolean"
                    },

                    "dispatch_company_has_entry": {
                        "type": "boolean"
                    },

                    "dispatch_company_uncertain": {
                        "type": "boolean"
                    }
                },
                "required": [
                    "regular",
                    "dispatch",
                    "contract",
                    "parttime",
                    "other",
                    "dispatch_company_visible",
                    "dispatch_company_has_entry",
                    "dispatch_company_uncertain"
                ],
                "additionalProperties": False
            }
        }
    }


# =========================================================
# AI判定
# =========================================================

def check_employment(img):

    prompt = """
これは日本語のクレジット申込書です。

今回の目的は文字をOCRすることではありません。

「雇用形態」の各選択肢のどこに
手書きの○が付いているかを、
位置関係から判定してください。


【最重要】

まず画像内から印刷された

「雇用形態」

という見出しを探してください。

その雇用形態欄の中だけを判定します。


次に以下の各選択肢を
それぞれ独立して確認してください。

regular
= 正社員

dispatch
= 派遣社員

contract
= 契約社員

parttime
= パート・アルバイト

other
= その他


それぞれについて、

label_visible
= その印刷された選択肢を確認できるか

circle_present
= その選択肢の文字または選択位置に、
  実際の手書き○・囲みが重なっているか

を判定してください。


==================================================
非常に重要
==================================================

「どの雇用形態だと思うか」を推測してはいけません。

5個の選択肢を1個ずつ別々に見てください。


例えば、

正社員       ○なし
派遣社員     ○あり
契約社員     ○なし

なら、

regular.circle_present=false
dispatch.circle_present=true
contract.circle_present=false

です。


○の中心位置が
どの印刷文字・選択位置に最も対応しているかを
よく確認してください。


隣の選択肢に○をずらして判定しないでください。

特に

「派遣社員」
と
「契約社員」

は隣接しているため、
必ず別々に確認してください。


印刷されている文字そのもの、
文字を囲む表の罫線、
印刷された丸印、

これらは手書き○ではありません。


画像が横向き・縦向き・90度回転していても、
書類を正しい向きに頭の中で回転させて確認してください。


==================================================
派遣先・出向先
==================================================

さらに、

「派遣先・出向先」

と印刷された会社名欄を探してください。

dispatch_company_visible
= その指定欄が画像で確認できるか

dispatch_company_has_entry
= その指定欄そのものに手書き記入があるか

dispatch_company_uncertain
= 見えているが本当に判定できない場合のみtrue


勤務先の「会社名」など、
別の会社名を派遣先として使用してはいけません。


個人名や会社名などの内容そのものを
返す必要はありません。
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
        response_format=schema()
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# UI
# =========================================================

uploaded = st.file_uploader(
    "クレジット申込書の写真",
    type=[
        "jpg",
        "jpeg",
        "png"
    ]
)


if uploaded:

    img = Image.open(uploaded)

    img = ImageOps.exif_transpose(img).convert("RGB")

    # 大きすぎる画像だけ縮小
    if max(img.size) > 3200:

        scale = 3200 / max(img.size)

        img = img.resize(
            (
                int(img.width * scale),
                int(img.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

    st.image(
        img,
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
                "○の位置を確認しています…"
            ):

                data = check_employment(img)


            choices = [
                ("regular", "正社員"),
                ("dispatch", "派遣社員"),
                ("contract", "契約社員"),
                ("parttime", "パート・アルバイト"),
                ("other", "その他")
            ]


            selected = []

            for key, label in choices:

                value = data[key]

                if (
                    value["label_visible"]
                    and
                    value["circle_present"]
                ):

                    selected.append(label)


            st.divider()


            # =============================================
            # 最終判定はPython
            # =============================================

            if len(selected) == 1:

                employment = selected[0]

                st.success(
                    f"✅ 雇用形態：{employment}"
                )


                # 派遣社員だけ追加チェック
                if employment == "派遣社員":

                    if not data[
                        "dispatch_company_visible"
                    ]:

                        st.warning(
                            "🔍 派遣先・出向先："
                            "欄を確認できません"
                        )

                    elif data[
                        "dispatch_company_uncertain"
                    ]:

                        st.warning(
                            "🔍 派遣先・出向先："
                            "判定できません"
                        )

                    elif data[
                        "dispatch_company_has_entry"
                    ]:

                        st.success(
                            "✅ 派遣先・出向先：記入あり"
                        )

                    else:

                        st.error(
                            "❌ 派遣先・出向先：空欄"
                        )

                else:

                    st.info(
                        "派遣先・出向先：対象外"
                    )


            elif len(selected) == 0:

                st.warning(
                    "🔍 雇用形態：○を特定できません"
                )


            else:

                st.error(
                    "⚠️ 雇用形態：複数の○を検出しました"
                )

                st.write(
                    "検出："
                    + " / ".join(selected)
                )


            # =============================================
            # 判定データ
            # =============================================

            with st.expander(
                "判定データ"
            ):

                for key, label in choices:

                    value = data[key]

                    st.write(
                        f"**{label}**"
                    )

                    st.write(
                        "文字位置を確認：",
                        value["label_visible"]
                    )

                    st.write(
                        "○あり：",
                        value["circle_present"]
                    )

                    st.write(
                        "確信度：",
                        value["confidence"]
                    )

                    st.divider()


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
