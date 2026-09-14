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

st.title("業種 選択チェック")

st.caption(
    "「業種」欄の選択肢に、手書きの○が付いているかを確認します。"
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
あなたは日本のクレジット申込書の
「記入漏れチェック」を行います。

今回確認する項目は1つだけです。

【確認対象】

契約者本人の勤務先情報にある
印刷された「業種」欄。


==================================================
このチェックの目的
==================================================

業種の内容が正しいかは確認しません。

今回知りたいのは、

「業種欄に並んでいる印刷済みの選択肢のうち、
どれかに手書きの○が付いているか」

だけです。


==================================================
対象欄を探す
==================================================

まず、

「ご契約者」

の勤務先情報を探してください。

その中にある、

「業種」

という印刷された項目を探してください。

業種欄には複数の業種の選択肢が
小さな印刷文字で横や縦に並んでいます。

今回見るのは、

その「業種」の選択肢部分だけです。


==================================================
非常に重要
==================================================

この書類には、

・性別
・ご住居
・雇用形態
・世帯状況
・続柄
・銀行関連
・その他の選択項目

など、

業種以外にも多数の手書き○があります。

これらの○は絶対に数えないでください。

書類全体に○が何個あるかを見るのではありません。

必ず、

「業種」という印刷ラベルに直接対応する
業種選択肢の範囲だけ

を見てください。


==================================================
○の判定
==================================================

業種選択肢の印刷文字を囲むような、

・手書きの丸
・ペンで付けられた明確な囲み

だけを選択として扱ってください。

印刷された罫線や、
文字そのものの丸い部分は○ではありません。

近くにある別項目の○も無視してください。


==================================================
判定方法
==================================================

業種欄の中に、

手書きの○が1つある
→ circle_count = 1

手書きの○がない
→ circle_count = 0

明らかに2つ以上の選択肢に○がある
→ circle_count = 2

3つ以上の場合も、
circle_count = 2 としてください。

つまり、

0 = 選択なし
1 = 1つ選択
2 = 複数選択

として返してください。


==================================================
重要：業種名を読む必要はありません
==================================================

どの業種が選ばれているかを
回答する必要はありません。

「製造」
「建設」
「サービス」

などをOCRして回答する必要もありません。

業種名を推測しないでください。

必要なのは、

対象となる業種欄の中に
手書き○が何個存在するか

だけです。


==================================================
正式な記入済み書類について
==================================================

正式な記入済み書類では、
周囲に大量の手書き文字や○があります。

周囲にたくさん○があっても、
それを理由に業種が選択済みだと
判断してはいけません。

最初に「業種」の場所を特定し、

その業種欄の内部だけを
視覚的に確認してください。


==================================================
判定不能
==================================================

次の場合だけ uncertain = true にしてください。

・「業種」欄が写真に写っていない
・業種欄が小さすぎて確認できない
・ピンぼけしている
・業種欄が途中で切れている
・○なのか印刷文字なのか区別できない

判断できない場合は推測しないでください。


==================================================
出力項目
==================================================

field_visible

= 「業種」という印刷ラベルと、
  その選択肢部分を確認できる。


circle_count

= 業種欄の内部に存在する手書き○の数。

0 = なし
1 = 1つ
2 = 複数


uncertain

= 確実に判定できない。


==================================================
最後の確認
==================================================

circle_count を決める前に、

「今数えている○は、本当に
『業種』という印刷ラベルに対応する
業種選択肢の中にある○か？」

を確認してください。

雇用形態や性別など、
別項目の○なら絶対に数えないでください。
"""

    schema = {
        "name": "industry_circle_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "field_visible": {
                    "type": "boolean"
                },
                "circle_count": {
                    "type": "integer",
                    "enum": [0, 1, 2]
                },
                "uncertain": {
                    "type": "boolean"
                }
            },
            "required": [
                "field_visible",
                "circle_count",
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


        # ==================================
        # 結果表示
        # ==================================

        if (
            result["uncertain"]
            or not result["field_visible"]
        ):

            st.warning(
                "🔍 業種：判定できません"
            )

            st.caption(
                "業種欄がもう少し大きく写るように撮影してください。"
            )


        elif result["circle_count"] == 0:

            st.error(
                "❌ 業種：未選択"
            )


        elif result["circle_count"] == 1:

            st.success(
                "✅ 業種：選択あり"
            )


        else:

            st.warning(
                "⚠️ 業種：複数選択されています"
            )


        with st.expander("判定データ"):
            st.json(result)
