import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from pydantic import BaseModel
from typing import List
import io
import traceback


st.set_page_config(
    page_title="Gemini 契約書テスト",
    page_icon="🔎"
)

st.title("Gemini 契約書画像テスト")
st.write("雇用形態・業種・数量をGeminiで確認します。")


# =========================
# Gemini
# =========================

try:
    client = genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"]
    )
except Exception as e:
    st.error("Gemini APIキーの設定でエラーが発生しました")
    st.code(str(e))
    st.stop()


MODEL = "gemini-3.1-pro-preview"


# =========================
# 出力形式
# =========================

class EmploymentResult(BaseModel):
    field_visible: bool

    regular_employee_circled: bool
    dispatch_employee_circled: bool
    contract_employee_circled: bool
    parttime_circled: bool

    public_employee_circled: bool
    business_owner_circled: bool
    housewife_circled: bool
    pension_circled: bool
    student_circled: bool

    uncertain: bool


class IndustryResult(BaseModel):
    field_visible: bool
    circle_present: bool
    uncertain: bool


class QuantityRow(BaseModel):
    row_label: str
    horizontal_values: List[int]
    written_quantity: str
    quantity_cell_has_handwriting: bool


class QuantityResult(BaseModel):
    table_visible: bool
    rows: List[QuantityRow]
    uncertain: bool


class ContractCheck(BaseModel):
    employment: EmploymentResult
    industry: IndustryResult
    quantity: QuantityResult


# =========================
# 画像
# =========================

uploaded = st.file_uploader(
    "契約書の写真を1枚選択",
    type=["jpg", "jpeg", "png", "webp"]
)


if uploaded is not None:

    image = Image.open(uploaded)

    image = ImageOps.exif_transpose(
        image
    ).convert("RGB")

    st.image(
        image,
        caption="判定する画像",
        use_container_width=True
    )


    if st.button(
        "Geminiで判定",
        type="primary",
        use_container_width=True
    ):

        prompt = """
あなたは日本の契約書の記入漏れを確認する担当者です。

目的は記載内容の真偽を審査することではありません。
指定された欄に必要な記入や丸が存在するかを確認します。

画像が横向き・縦向きでも、書類全体のレイアウトを理解して確認してください。

対象欄を探すときは、

1. 書類全体
2. 大きなブロック
3. 周囲の印刷ラベル
4. 対象欄
5. 対象欄内部の位置関係

の順番で特定してください。

別の欄の文字、丸、数字を対象欄のものとして使用してはいけません。

見えない、または判断できない場合は推測せず uncertain=true にしてください。


【雇用形態】

クレジット申込書の「ご契約者」の勤務先情報にある
「雇用形態」を確認してください。

選択肢は次の位置関係です。

正社員
派遣社員
契約社員
パート・アルバイト
公務員
事業者
主婦
年金
学生

各選択肢について、
手書きの丸が実際に重なっているかを確認してください。

特に

派遣社員
契約社員

は隣接しています。

文字を推測するのではなく、
丸の中心位置がどの印刷文字に対応しているかを確認してください。


【業種】

同じ「ご契約者」の勤務先情報にある
「業種」欄を確認してください。

まず印刷された「業種」ラベルを発見してください。

その業種欄の選択肢の範囲内に
手書きの丸が存在する場合のみ

circle_present=true

にしてください。

雇用形態、性別、ご住居、世帯情報、
関係者情報などにある丸は絶対に使用しないでください。

業種欄そのものが画像に存在しない場合は

field_visible=false

にしてください。


【数量】

役務申込書の教材表を確認してください。

各対象行について、
数量欄より左側に並んでいる手書き整数を
horizontal_values に入れてください。

そして印刷された「数量」列のセルそのものに
書かれている数字だけを

written_quantity

に入れてください。

数量セルが空欄なら

written_quantity=""

quantity_cell_has_handwriting=false

にしてください。

数量列より右側にある

各単価
小計
合計

の数字は絶対に数量として使用しないでください。

特に

36000
108000
648000
712800

などの金額を数量として読み取ってはいけません。
"""


        try:

            with st.spinner("Geminiが確認中..."):

                buffer = io.BytesIO()

                image.save(
                    buffer,
                    format="JPEG",
                    quality=97
                )

                response = client.models.generate_content(

                    model=MODEL,

                    contents=[
                        prompt,

                        types.Part.from_bytes(
                            data=buffer.getvalue(),
                            mime_type="image/jpeg"
                        )
                    ],

                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ContractCheck
                    )
                )

                result = ContractCheck.model_validate_json(
                    response.text
                )


            st.success("Gemini APIとの通信に成功しました")


            # =========================
            # 雇用形態
            # =========================

            st.subheader("雇用形態")

            emp = result.employment

            employment_list = [
                ("正社員", emp.regular_employee_circled),
                ("派遣社員", emp.dispatch_employee_circled),
                ("契約社員", emp.contract_employee_circled),
                ("パート・アルバイト", emp.parttime_circled),
                ("公務員", emp.public_employee_circled),
                ("事業者", emp.business_owner_circled),
                ("主婦", emp.housewife_circled),
                ("年金", emp.pension_circled),
                ("学生", emp.student_circled),
            ]

            selected = [
                name
                for name, value in employment_list
                if value
            ]

            if emp.uncertain or not emp.field_visible:

                st.warning(
                    "🔍 雇用形態：判定できません"
                )

            elif len(selected) == 0:

                st.error(
                    "❌ 雇用形態：選択なし"
                )

            elif len(selected) > 1:

                st.warning(
                    "⚠️ 雇用形態：複数検出 "
                    + " / ".join(selected)
                )

            else:

                st.success(
                    "✅ 雇用形態：" + selected[0]
                )


            # =========================
            # 業種
            # =========================

            st.subheader("業種")

            industry = result.industry

            if (
                industry.uncertain
                or not industry.field_visible
            ):

                st.warning(
                    "🔍 業種：判定できません"
                )

            elif industry.circle_present:

                st.success(
                    "✅ 業種：選択あり"
                )

            else:

                st.error(
                    "❌ 業種：選択なし"
                )


            # =========================
            # 数量
            # =========================

            st.subheader("数量")

            quantity = result.quantity

            if quantity.uncertain:

                st.warning(
                    "🔍 数量：判定できません"
                )

            elif not quantity.table_visible:

                st.warning(
                    "🔍 数量表が見つかりません"
                )

            elif len(quantity.rows) == 0:

                st.warning(
                    "🔍 対象行を特定できません"
                )

            else:

                for row in quantity.rows:

                    expected = sum(
                        row.horizontal_values
                    )

                    if not row.quantity_cell_has_handwriting:

                        st.error(
                            f"❌ {row.row_label}：数量欄が空欄"
                        )

                        continue

                    try:

                        written = int(
                            row.written_quantity
                        )

                    except:

                        st.warning(
                            f"🔍 {row.row_label}：数量を読み取れません"
                        )

                        continue

                    if written >= 1000:

                        st.warning(
                            f"🔍 {row.row_label}："
                            f"{written} は金額誤読の可能性"
                        )

                    elif written == expected:

                        st.success(
                            f"✅ {row.row_label}："
                            f"{expected} = {written}"
                        )

                    else:

                        st.error(
                            f"❌ {row.row_label}："
                            f"横合計 {expected} / 数量 {written}"
                        )


        # =========================
        # エラーを画面に表示
        # =========================

        except Exception as e:

            st.error(
                "Gemini APIでエラーが発生しました"
            )

            st.write(
                "↓ この内容をスクショして送ってください"
            )

            st.code(
                f"{type(e).__name__}: {str(e)}"
            )

            with st.expander(
                "詳しいエラー"
            ):

                st.code(
                    traceback.format_exc()
                )
