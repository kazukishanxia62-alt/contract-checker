import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from pydantic import BaseModel
from typing import List
import io


st.set_page_config(
    page_title="Gemini 契約書テスト",
    page_icon="🔎"
)


# =========================
# Gemini
# =========================

client = genai.Client(
    api_key=st.secrets["GEMINI_API_KEY"]
)

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
# UI
# =========================

st.title("Gemini 契約書画像テスト")

st.write(
    "まず雇用形態・業種・数量の3項目だけを確認します。"
)


uploaded = st.file_uploader(
    "契約書の写真",
    type=["jpg", "jpeg", "png", "webp"]
)


if uploaded:

    image = Image.open(uploaded)

    image = ImageOps.exif_transpose(
        image
    ).convert("RGB")

    st.image(
        image,
        caption="判定画像",
        use_container_width=True
    )


    if st.button(
        "Geminiで判定",
        type="primary",
        use_container_width=True
    ):

        with st.spinner(
            "Geminiが確認中..."
        ):

            prompt = """
あなたは日本の契約書の
記入漏れを確認する担当者です。

これは内容の真偽を
審査する作業ではありません。

画像全体の構造と、
項目同士の位置関係を使って
判定してください。


====================
重要な基本ルール
====================

対象項目を単独で探さず、

1. 書類全体
2. 大きなブロック
3. 上下左右の周辺欄
4. 対象ラベル
5. 選択肢の位置

の順番で確認してください。


近くにある別の丸や数字を
絶対に対象項目として
流用しないでください。


判別できない場合は
推測せず uncertain=true。


====================
雇用形態
====================

クレジット契約書の場合、

ご契約者情報の下に
勤務先情報があります。

その勤務先情報の中に

「雇用形態」

があります。


選択肢の印刷順は

1 正社員
2 派遣社員
3 契約社員
4 パート・アルバイト
5 公務員
6 事業者
7 主婦
8 年金
9 学生


です。


文字認識だけでなく、

左から何番目か、
同じ行のどの位置か、

という位置関係を使ってください。


特に

派遣社員

と

契約社員

は隣なので、

丸の中心位置が
どちらに対応しているかを
慎重に確認してください。


====================
業種
====================

「業種」は

ご契約者の勤務先情報の中にあります。


まず勤務先ブロックを確認し、

その中の
「業種」ラベルに対応する
選択行だけを見てください。


雇用形態、
性別、
ご住居、
世帯情報、
関係者情報

などの丸を
業種の丸として数えてはいけません。


業種欄そのものが
見つからなければ

field_visible=false。


業種選択肢の範囲内に
手書きの丸が存在するときだけ

circle_present=true。


====================
数量
====================

役務申込書の場合、

中央付近に教材の表があります。


列は左から

教科・学年等

↓

数量

↓

各単価

↓

小計


という関係です。


各行について、

数量より左側にある
手書き整数を

horizontal_values

に入れてください。


その行の

「数量」

列そのものに
書かれている数字だけを

written_quantity

に入れてください。


数量セルが空欄なら

written_quantity=""

にしてください。


絶対に

12000
24000
36000
48000
108000
648000
712800

などの

各単価
小計
合計

を数量として
読んではいけません。


数量列より右側の数字は
written_quantityには使用禁止です。
"""


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


        st.success(
            "判定完了"
        )


        # =========================
        # 雇用形態
        # =========================

        st.subheader(
            "雇用形態"
        )

        emp = result.employment


        employment_list = [

            (
                "正社員",
                emp.regular_employee_circled
            ),

            (
                "派遣社員",
                emp.dispatch_employee_circled
            ),

            (
                "契約社員",
                emp.contract_employee_circled
            ),

            (
                "パート・アルバイト",
                emp.parttime_circled
            ),

            (
                "公務員",
                emp.public_employee_circled
            ),

            (
                "事業者",
                emp.business_owner_circled
            ),

            (
                "主婦",
                emp.housewife_circled
            ),

            (
                "年金",
                emp.pension_circled
            ),

            (
                "学生",
                emp.student_circled
            )
        ]


        selected = [

            name

            for name, circled
            in employment_list

            if circled
        ]


        if (
            emp.uncertain
            or not emp.field_visible
        ):

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
                "✅ 雇用形態："
                + selected[0]
            )


        # =========================
        # 業種
        # =========================

        st.subheader(
            "業種"
        )

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

        st.subheader(
            "数量"
        )

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
                        f"❌ {row.row_label}："
                        f"数量欄が空欄"
                    )

                    continue


                try:

                    written = int(
                        row.written_quantity
                    )

                except:

                    st.warning(
                        f"🔍 {row.row_label}："
                        f"数量を読み取れません"
                    )

                    continue


                if written >= 1000:

                    st.warning(
                        f"🔍 {row.row_label}："
                        f"{written} は金額誤読の可能性"
                    )

                    continue


                if written == expected:

                    st.success(
                        f"✅ {row.row_label}："
                        f"{expected} = {written}"
                    )


                else:

                    st.error(
                        f"❌ {row.row_label}："
                        f"横合計 {expected} / "
                        f"数量 {written}"
                    )
