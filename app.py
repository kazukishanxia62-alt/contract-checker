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
    page_title="業種チェック",
    page_icon="✅",
    layout="centered"
)

st.title("業種 記入チェック")

st.caption(
    "契約書の「業種」欄に手書きの記入があるかだけを確認します。"
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
# 業種判定
# ==========================================

def check_industry(images):

    prompt = """
あなたは日本の契約書の「記入漏れチェック」を行います。

今回確認する項目は1つだけです。

【確認対象】

印刷された「業種」という項目に対応する記入欄。


【目的】

業種の内容が正しいかを確認する必要はありません。

確認したいのは、

「業種欄に手書きの記入が存在するか」

だけです。


==================================================
重要ルール
==================================================

1.

まず契約書内の印刷された

「業種」

という項目名を探してください。


2.

その「業種」に直接対応している
記入欄だけを確認してください。


3.

その欄に手書き文字が明確に存在する場合、

has_entry = true

にしてください。


4.

業種欄そのものが見えていて、
手書き文字が存在しない場合、

has_entry = false

にしてください。


5.

書かれている内容を正確に読み取る必要はありません。

例えば、

製造業
サービス業
建設
小売
IT

など、何と書いてあるかは判定対象ではありません。


6.

業種として正しい内容かどうかも判定しません。

文字が書かれていればOKです。


7.

近くにある

・会社名
・勤務先名
・職種
・役職
・所在地
・電話番号
・雇用形態

などの記入を、

「業種」の記入として扱わないでください。


8.

用紙に最初から印刷されている文字は
記入として数えません。

確認するのは手書きの記入です。


9.

画像が横向き・縦向き・上下逆でも、
書類の向きを理解して確認してください。


10.

複数の画像が送られた場合は、
同じ契約書の別写真として扱ってください。

最も「業種」欄を確認しやすい画像を使用してください。


==================================================
判定不能
==================================================

次の場合のみ uncertain = true にしてください。

・「業種」欄が写真に写っていない
・文字が小さすぎる
・ピンぼけしている
・対象欄が途中で切れている
・手書き文字があるか判断できない

推測は禁止です。


==================================================
出力
==================================================

field_visible

= 印刷された「業種」と、
その記入欄を確認できる。


has_entry

= 「業種」の記入欄に
手書き文字が存在する。


uncertain

= 画像から確実に判断できない。


==================================================
最後の確認
==================================================

has_entry = true にする前に、

「私は、印刷された『業種』に直接対応する欄の中に
手書き文字が存在することを実際に確認できているか？」

を確認してください。

近くの別項目に文字があるだけなら
has_entry = false です。
"""

    schema = {
        "name": "industry_entry_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "field_visible": {
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
                "field_visible",
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


        if result["uncertain"] or not result["field_visible"]:

            st.warning(
                "🔍 業種：判定できません"
            )

        elif result["has_entry"]:

            st.success(
                "✅ 業種：記入あり"
            )

        else:

            st.error(
                "❌ 業種：未記入"
            )


        with st.expander("判定データ"):
            st.json(result)
