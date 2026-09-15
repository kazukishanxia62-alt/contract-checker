import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from typing import List, Optional
import io
import traceback


# ============================================================
# 基本設定
# ============================================================

st.set_page_config(
    page_title="契約書チェック",
    page_icon="📄",
    layout="centered"
)

st.title("📄 契約書チェック")
st.caption("契約書を提出する前の記入漏れ・選択漏れチェック")

st.info(
    "AIによる提出前チェックです。"
    "記載内容そのものの事実確認ではなく、"
    "必要欄への記入・選択の有無を中心に確認します。"
)


# ============================================================
# Gemini
# ============================================================

try:
    client = genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"]
    )
except Exception as e:
    st.error("Gemini APIの設定を確認してください。")
    st.code(str(e))
    st.stop()


MODEL = "gemini-3.1-pro-preview"


# ============================================================
# 共通Schema
# ============================================================

class FieldCheck(BaseModel):
    located: bool
    has_entry: bool
    uncertain: bool = False


class CircleCheck(BaseModel):
    located: bool
    has_circle: bool
    uncertain: bool = False


# ============================================================
# PAGE1 本人
# ============================================================

class ApplicantResult(BaseModel):
    name: FieldCheck
    name_furigana: FieldCheck
    gender: CircleCheck
    birth_date: FieldCheck
    address: FieldCheck
    address_furigana: FieldCheck
    postal_code: FieldCheck
    residence: CircleCheck

    fixed_phone_has_entry: bool
    mobile_phone_has_entry: bool
    phone_uncertain: bool


class AddressRuleResult(BaseModel):
    field_located: bool
    has_entry: bool
    prefecture_explicit: bool
    uncertain: bool


# ============================================================
# PAGE1 本人雇用形態
# ============================================================

class ApplicantEmploymentResult(BaseModel):

    field_located: bool

    # まず「○自体があるか」を独立判定
    circle_visible: bool

    regular_employee: bool
    dispatch_employee: bool
    contract_employee: bool
    parttime_employee: bool

    public_employee: bool
    business_owner: bool
    housewife: bool
    pension: bool
    student: bool

    uncertain: bool


# ============================================================
# PAGE1 勤務年数
# ============================================================

class WorkYearsResult(BaseModel):

    field_located: bool

    year_position_located: bool
    year_handwriting_visible: bool
    year_value: Optional[int] = None

    months_position_located: bool

    # 「0」を空欄扱いさせないため、
    # 筆跡の存在と数字認識を分離
    months_handwriting_visible: bool
    months_zero_visible: bool
    months_value: Optional[int] = None

    uncertain: bool


# ============================================================
# PAGE1 勤務先
# ============================================================

class WorkResult(BaseModel):
    company_name: FieldCheck
    company_address: FieldCheck
    company_postal_code: FieldCheck
    company_phone: FieldCheck
    payday: FieldCheck
    dispatch_destination: FieldCheck


class IndustryResult(BaseModel):
    field_located: bool
    circle_visible: bool
    uncertain: bool


# ============================================================
# PAGE1 世帯
# ============================================================

class HouseholdBasicResult(BaseModel):
    field_located: bool
    required_entries_present: bool
    required_selections_present: bool
    uncertain: bool


class MonthlyCreditResult(BaseModel):

    exact_field_located: bool

    handwriting_visible: bool

    amount_readable: bool
    amount_yen: Optional[int] = None

    uncertain: bool


# ============================================================
# PAGE1 関係者
# ============================================================

class RelationBasicResult(BaseModel):
    name: FieldCheck
    name_furigana: FieldCheck
    gender: CircleCheck
    birth_date: FieldCheck
    relationship: FieldCheck
    address: FieldCheck
    postal_code: FieldCheck
    residence: CircleCheck
    contact: FieldCheck
    annual_income: FieldCheck
    years_employed: FieldCheck
    payday: FieldCheck
    company_name: FieldCheck
    company_location: FieldCheck
    company_postal_code: FieldCheck
    company_phone: FieldCheck


class RelationEmploymentResult(BaseModel):

    field_located: bool

    # ここも「何が選択されたか」より先に
    # ○そのものの存在を独立判定
    circle_visible: bool

    uncertain: bool


# ============================================================
# PAGE1 銀行
# ============================================================

class BankResult(BaseModel):
    section_located: bool
    japan_post_has_entry: bool
    other_bank_has_entry: bool
    account_holder_furigana: FieldCheck
    uncertain: bool


# ============================================================
# PAGE1 契約情報
# ============================================================

class ContractResult(BaseModel):
    service_period: FieldCheck
    article42_receipt_date: FieldCheck


# ============================================================
# PAGE2
# ============================================================

class GuardianResult(BaseModel):
    guardian_name_furigana: FieldCheck


class Page2AddressResult(BaseModel):
    field_located: bool
    has_entry: bool
    prefecture_explicit: bool
    prefecture_selector_located: bool
    appropriate_prefecture_circle: bool
    uncertain: bool


class TargetAResult(BaseModel):
    field_located: bool
    yes_circle_visible: bool
    uncertain: bool


class SchoolResult(BaseModel):
    field_located: bool
    public_circle: bool
    national_circle: bool
    private_circle: bool
    uncertain: bool


class CourseResult(BaseModel):
    field_located: bool
    has_entry: bool
    weekly_once: bool
    ninety_minutes: bool
    uncertain: bool


class Page2DatesResult(BaseModel):
    first_instruction_date: FieldCheck
    service_period_a: FieldCheck


class ReceiptResult(BaseModel):
    field_located: bool
    signature_visible: bool
    uncertain: bool


# ============================================================
# 数量
# ============================================================

class QuantityRow(BaseModel):
    row_label: str

    horizontal_values: List[int] = Field(
        default_factory=list
    )

    quantity_cell_located: bool

    quantity_handwriting_visible: bool

    written_quantity: Optional[int] = None

    uncertain: bool = False


class QuantityResult(BaseModel):
    table_located: bool
    applicable_rows_visible: bool
    rows: List[QuantityRow] = Field(default_factory=list)
    uncertain: bool


# ============================================================
# 共通思想
# ============================================================

COMMON = """
あなたは日本の契約書を提出する前に、
記入漏れ・選択漏れを確認する
視覚チェック担当です。

この仕事で最も重要なのは、

「書類の別の場所にある文字・数字・○を
対象欄のものとして誤認しないこと」

です。


━━━━━━━━━━━━━━━━━━━━━━

【基本原則】

内容が事実として正しいかを
審査する仕事ではありません。

原則として、

・指定欄に手書き記入が存在するか
・指定された選択欄に手書き○が存在するか

を確認します。


ただし次の項目だけは
内容まで確認します。

・住所の都道府県
・勤務年数の年／ヶ月
・月あたりクレジット支払額
・週1 90分
・数量
・公／国／私


━━━━━━━━━━━━━━━━━━━━━━

【対象欄を探す順序】

絶対に、

文字や数字を先に探してから
項目を推測してはいけません。

必ず、

1. 書類全体を確認
2. 対象となる大ブロックを確認
3. 印刷された項目名を確認
4. 項目名に直接対応する記入領域を確認
5. その領域内の手書き筆跡を確認
6. 必要な場合だけ内容を読む

の順番で判断してください。


━━━━━━━━━━━━━━━━━━━━━━

【重要】

手書きが薄い、
○が文字と重なっている、
数字が小さい、

という理由だけで
「未記入」と判断してはいけません。

手書き筆跡の存在が見えるが
内容だけ判別できない場合は、

uncertain=true

にしてください。


逆に、

対象欄を確実に特定できない場合も
推測せず uncertain=true にしてください。


━━━━━━━━━━━━━━━━━━━━━━

【フリガナ】

指定されたフリガナ欄に
手書き文字が存在すればOKです。

氏名との読みの一致は確認不要です。


【会社名】

指定欄に記入があればOKです。

実在性や正式名称は確認不要です。


【選択欄】

○の中の文字をOCRするだけではなく、

・印刷された選択肢
・選択肢の並び
・手書き○の位置

を視覚的に確認してください。
"""


# ============================================================
# PAGE1 構造
# ============================================================

PAGE1 = """
【1枚目：クレジット申込書】

この帳票は大きく、

A：ご契約者本人
B：ご契約者勤務先
C：世帯主・世帯状況
D：関係者情報
E：銀行口座
F：契約関連

の順番で構成されています。


━━━━━━━━━━━━━━━━━━━━━━

【B：本人勤務先】

本人住所等の下側にあります。

ここには、

・雇用形態
・業種
・会社名
・所在地
・郵便番号
・電話番号
・勤務年数
・給料日
・派遣先／出向先

などがあります。

Dの関係者情報とは
完全に別のブロックです。


━━━━━━━━━━━━━━━━━━━━━━

【本人の雇用形態】

印刷された選択肢の固定順は、

1段目・左から

正社員
派遣社員
契約社員
パート・アルバイト

2段目・左から

公務員
事業者
主婦
年金
学生

です。


━━━━━━━━━━━━━━━━━━━━━━

【世帯状況】

「世帯主の年収(税込)」

と

「世帯主のクレジットの
月あたりのお支払額」

は完全に別の欄です。


━━━━━━━━━━━━━━━━━━━━━━

【D：関係者情報】

本人情報とは別です。

関係者情報の氏名・住所・勤務先・雇用形態等は
必ずDブロック内だけを見てください。


━━━━━━━━━━━━━━━━━━━━━━

【銀行】

ゆうちょ銀行側と
ゆうちょ銀行以外の銀行側があります。

どちらか一方で構いません。
"""


# ============================================================
# PAGE2 構造
# ============================================================

PAGE2 = """
【2枚目：役務申込書・指導内容】

概ね、

左上：
契約者／保護者

右上：
指導対象A/B/C／学校

中央～下：
コース／指導内容／期間

中央～右下：
教材／数量／各単価／小計

最上部右側：
書面交付日／受領サイン

という構造です。


【受領サイン】

最上部右側にある

「受領サイン →」

の矢印直後の欄だけを確認してください。


【数量】

数量表は、

横方向の選択欄
→ 数量
→ 各単価
→ 小計

という関係です。

各単価、小計、合計などの金額を
数量として使用禁止です。
"""


# ============================================================
# Gemini通信
# ============================================================

def prepare_image(image):

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    buf = io.BytesIO()

    # 文字や○を潰さないため高品質
    image.save(
        buf,
        format="JPEG",
        quality=98,
        subsampling=0
    )

    return buf.getvalue()


def ask(image_bytes, prompt, schema):

    response = client.models.generate_content(

        model=MODEL,

        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg"
            )
        ],

        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema
        )
    )

    return schema.model_validate_json(
        response.text
    )


def safe_ask(image_bytes, prompt, schema):

    try:
        return ask(
            image_bytes,
            prompt,
            schema
        )

    except Exception as e:

        st.error(
            "Gemini APIでエラーが発生しました"
        )

        st.code(
            f"{type(e).__name__}: {str(e)}"
        )

        with st.expander("詳しいエラー"):
            st.code(traceback.format_exc())

        return None


# ============================================================
# 表示関数
# ============================================================

def show_field(label, value):

    if value.uncertain or not value.located:

        st.warning(
            f"🔍 {label}：要確認"
        )

    elif value.has_entry:

        st.success(
            f"✅ {label}：記入あり"
        )

    else:

        st.error(
            f"❌ {label}：未記入"
        )


def show_circle(label, value):

    if value.uncertain or not value.located:

        st.warning(
            f"🔍 {label}：要確認"
        )

    elif value.has_circle:

        st.success(
            f"✅ {label}：選択あり"
        )

    else:

        st.error(
            f"❌ {label}：選択なし"
        )


# ============================================================
# UI
# ============================================================

st.divider()

relation_enabled = st.checkbox(
    "関係者情報をチェックする",
    value=True
)

st.subheader("① クレジット申込書")

page1_file = st.file_uploader(
    "1枚目を選択",
    type=["jpg", "jpeg", "png", "webp"],
    key="page1"
)

st.subheader("② 役務申込書・指導内容")

page2_file = st.file_uploader(
    "2枚目を選択",
    type=["jpg", "jpeg", "png", "webp"],
    key="page2"
)


if page1_file:

    st.image(
        Image.open(page1_file),
        caption="① クレジット申込書",
        use_container_width=True
    )


if page2_file:

    st.image(
        Image.open(page2_file),
        caption="② 役務申込書・指導内容",
        use_container_width=True
    )


st.divider()


if st.button(
    "契約書をチェック",
    type="primary",
    use_container_width=True
):

    if not page1_file and not page2_file:

        st.warning(
            "写真を選択してください。"
        )

        st.stop()


    # ========================================================
    # PAGE 1
    # ========================================================

    if page1_file:

        p1 = prepare_image(
            Image.open(page1_file)
        )

        st.header(
            "① クレジット申込書"
        )


        # ====================================================
        # 本人基本情報
        # ====================================================

        with st.spinner(
            "ご契約者情報を確認中..."
        ):

            applicant = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認するのは
A：ご契約者本人情報だけです。

確認対象：

氏名
氏名フリガナ
性別
生年月日
住所
住所フリガナ
郵便番号
住居
固定電話
携帯電話

住所フリガナは
本人住所に直接対応する
住所フリガナ欄だけを確認してください。

氏名フリガナを
住所フリガナとして使用禁止。

電話番号は、
固定電話または携帯電話の
どちらか一方が記入されていればOK。
""",

                ApplicantResult
            )


        if applicant:

            st.subheader(
                "ご契約者"
            )

            show_field(
                "氏名",
                applicant.name
            )

            show_field(
                "氏名フリガナ",
                applicant.name_furigana
            )

            show_circle(
                "性別",
                applicant.gender
            )

            show_field(
                "生年月日",
                applicant.birth_date
            )

            show_field(
                "ご住所",
                applicant.address
            )

            show_field(
                "ご住所フリガナ",
                applicant.address_furigana
            )

            show_field(
                "郵便番号",
                applicant.postal_code
            )

            show_circle(
                "ご住居",
                applicant.residence
            )

            if applicant.phone_uncertain:

                st.warning(
                    "🔍 連絡先：要確認"
                )

            elif (
                applicant.fixed_phone_has_entry
                or applicant.mobile_phone_has_entry
            ):

                st.success(
                    "✅ 連絡先：記入あり"
                )

            else:

                st.error(
                    "❌ 連絡先：未記入"
                )


        # ====================================================
        # 本人住所 都道府県
        # ====================================================

        with st.spinner(
            "住所を確認中..."
        ):

            address = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認するのは
Aブロックの
「ご契約者のご住所」だけです。

住所文字列そのものが
都道府県名から始まっているかを確認。

例：

大阪府大阪市...
→ prefecture_explicit=true

大阪市...
→ prefecture_explicit=false

神戸市...
→ prefecture_explicit=false

市区町村から
都道府県を推測してはいけません。

フォームに印刷されている
「都・道・府・県」という文字だけでは
都道府県記入とはみなしません。
""",

                AddressRuleResult
            )


        if address:

            if (
                address.uncertain
                or not address.field_located
            ):

                st.warning(
                    "🔍 ご住所の都道府県：要確認"
                )

            elif not address.has_entry:

                st.error(
                    "❌ ご住所：未記入"
                )

            elif address.prefecture_explicit:

                st.success(
                    "✅ ご住所：都道府県から記入"
                )

            else:

                st.error(
                    "❌ ご住所：都道府県名から記入してください"
                )


        # ====================================================
        # ★ 本人雇用形態
        # ====================================================

        with st.spinner(
            "雇用形態を確認中..."
        ):

            employment = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認する対象は

B：ご契約者勤務先ブロック内の
「雇用形態」

ただ1つです。


━━━━━━━━━━━━━━━━━━━━━━

【最初にすること】

数字や○を探す前に、

1.
ご契約者本人の勤務先ブロック

2.
その中の印刷された
「雇用形態」

3.
その右側または周囲に並ぶ
雇用形態の選択肢

を特定してください。


━━━━━━━━━━━━━━━━━━━━━━

【固定された選択肢】

1段目を左から：

正社員
派遣社員
契約社員
パート・アルバイト

2段目を左から：

公務員
事業者
主婦
年金
学生


━━━━━━━━━━━━━━━━━━━━━━

【非常に重要】

まず、

「雇用形態の選択肢領域の中に
手書きの○が存在するか」

を視覚的に確認してください。

存在すれば

circle_visible=true

です。


その後で初めて、
○の中心位置がどの選択肢に
対応するか判断してください。


○が印刷文字と重なっていても構いません。

文字OCRだけで判断してはいけません。


━━━━━━━━━━━━━━━━━━━━━━

【派遣社員と契約社員】

特に重要です。

1段目は

正社員
↓右
派遣社員
↓右
契約社員
↓右
パート・アルバイト

の順番です。

派遣社員は
正社員の右隣。

契約社員は
派遣社員の右隣です。

○の中心が
派遣社員の印刷文字領域に
重なっているなら

dispatch_employee=true

です。


━━━━━━━━━━━━━━━━━━━━━━

【禁止】

次の○は絶対に使用禁止。

性別
住居
業種
世帯状況
関係者の雇用形態
関係者の住居
銀行


━━━━━━━━━━━━━━━━━━━━━━

【重要な安全ルール】

circle_visible=true
なのに、

どの選択肢かだけが
判別できない場合、

全選択肢をfalseにして
「選択なし」にしてはいけません。

その場合は

uncertain=true

にしてください。


○が本当に存在しない場合だけ

circle_visible=false
uncertain=false

です。
""",

                ApplicantEmploymentResult
            )


        dispatch_selected = False

        if employment:

            st.subheader(
                "勤務先"
            )

            choices = [

                (
                    "正社員",
                    employment.regular_employee
                ),

                (
                    "派遣社員",
                    employment.dispatch_employee
                ),

                (
                    "契約社員",
                    employment.contract_employee
                ),

                (
                    "パート・アルバイト",
                    employment.parttime_employee
                ),

                (
                    "公務員",
                    employment.public_employee
                ),

                (
                    "事業者",
                    employment.business_owner
                ),

                (
                    "主婦",
                    employment.housewife
                ),

                (
                    "年金",
                    employment.pension
                ),

                (
                    "学生",
                    employment.student
                ),
            ]


            selected = [

                name

                for name, selected_value
                in choices

                if selected_value
            ]


            dispatch_selected = (
                employment.dispatch_employee
            )


            if (
                employment.uncertain
                or not employment.field_located
            ):

                st.warning(
                    "🔍 雇用形態：要確認"
                )


            elif not employment.circle_visible:

                st.error(
                    "❌ 雇用形態：選択なし"
                )


            elif len(selected) == 0:

                # ○は見えている。
                # 選択肢だけ分からないので
                # 「未選択」にはしない。

                st.warning(
                    "🔍 雇用形態："
                    "○は確認できましたが選択肢を特定できません"
                )


            elif len(selected) > 1:

                st.warning(
                    "🔍 雇用形態：複数候補 "
                    + " / ".join(selected)
                )


            else:

                st.success(
                    "✅ 雇用形態："
                    + selected[0]
                )


        # ====================================================
        # 勤務先基本
        # ====================================================

        with st.spinner(
            "勤務先情報を確認中..."
        ):

            work = safe_ask(

                p1,

                COMMON + PAGE1 + """
B：ご契約者本人の
勤務先ブロックだけを確認。

対象：

会社名
所在地
所在地郵便番号
所在地電話番号
給料日
派遣先・出向先の会社名

勤務年数と雇用形態は
この判定では扱いません。

別ブロックの記入を流用禁止。
""",

                WorkResult
            )


        if work:

            show_field(
                "会社名",
                work.company_name
            )

            show_field(
                "所在地",
                work.company_address
            )

            show_field(
                "所在地の郵便番号",
                work.company_postal_code
            )

            show_field(
                "所在地の電話番号",
                work.company_phone
            )

            show_field(
                "給料日",
                work.payday
            )


            if dispatch_selected:

                show_field(
                    "派遣先・出向先の会社名",
                    work.dispatch_destination
                )

            elif employment and employment.uncertain:

                st.warning(
                    "🔍 派遣先・出向先："
                    "雇用形態が要確認のため要確認"
                )

            else:

                st.info(
                    "ℹ️ 派遣先・出向先：対象外"
                )


        # ====================================================
        # ★ 勤務年数 19年0ヶ月対策
        # ====================================================

        with st.spinner(
            "勤務年数を確認中..."
        ):

            years = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回見る対象は1つだけ。

B：ご契約者本人勤務先の
「勤務年数」欄です。


━━━━━━━━━━━━━━━━━━━━━━

【絶対に守る順番】

最初に数字を探してはいけません。

必ず、

本人勤務先ブロック
↓
印刷された「勤務年数」
↓
その勤務年数に対応する記入欄
↓
印刷された「年」
↓
印刷された「ヶ月」

の順番で位置関係を確認。


━━━━━━━━━━━━━━━━━━━━━━

勤務年数欄は、

[手書き数字] 年 [手書き数字] ヶ月

という構造です。


━━━━━━━━━━━━━━━━━━━━━━

【年】

まず印刷された「年」を特定。

その直前の記入位置に
手書き筆跡があるかを確認。

あるなら

year_handwriting_visible=true

です。

その数字を明確に読める場合だけ
year_valueに入れてください。


━━━━━━━━━━━━━━━━━━━━━━

【ヶ月】

ここが特に重要です。

まず印刷された「ヶ月」を特定。

次に、

「ヶ月」の直前の記入位置に
手書き筆跡が存在するか

を数字の意味とは別に
視覚的に確認してください。

筆跡がある場合、

months_handwriting_visible=true

です。


━━━━━━━━━━━━━━━━━━━━━━

【0ヶ月は記入あり】

数字の「0」は、

小さな丸
楕円
円形の筆跡

に見えることがあります。

これを

空欄
印刷された丸
汚れ

と安易に判断してはいけません。


「ヶ月」の直前の数字記入位置に

手書きの0

が存在する場合、

months_handwriting_visible=true
months_zero_visible=true
months_value=0

です。


0は明確な数字です。

0ヶ月を
「ヶ月未記入」
にしてはいけません。


━━━━━━━━━━━━━━━━━━━━━━

【重要】

months_valueが0だから
記入なし、

という判断は禁止。

0は記入ありです。


━━━━━━━━━━━━━━━━━━━━━━

【例】

19年0ヶ月

の場合：

field_located=true

year_position_located=true
year_handwriting_visible=true
year_value=19

months_position_located=true
months_handwriting_visible=true
months_zero_visible=true
months_value=0

uncertain=false


━━━━━━━━━━━━━━━━━━━━━━

【禁止】

勤務年数以外にある

生年月日
年齢
西暦
契約日
年収
給料日
郵便番号
電話番号
世帯主情報
関係者情報

の数字は使用禁止。


━━━━━━━━━━━━━━━━━━━━━━

勤務年数欄に筆跡が見えるが
数字だけ読めない場合は

「未記入」ではなく
uncertain=true

にしてください。
""",

                WorkYearsResult
            )


        if years:

            if (
                years.uncertain
                or not years.field_located
            ):

                st.warning(
                    "🔍 勤務年数：要確認"
                )

            elif not years.year_position_located:

                st.warning(
                    "🔍 勤務年数：「年」欄を特定できません"
                )

            elif not years.months_position_located:

                st.warning(
                    "🔍 勤務年数：「ヶ月」欄を特定できません"
                )

            elif not years.year_handwriting_visible:

                st.error(
                    "❌ 勤務年数：年が未記入"
                )

            elif not years.months_handwriting_visible:

                st.error(
                    "❌ 勤務年数：ヶ月が未記入"
                )

            elif years.year_value is None:

                st.warning(
                    "🔍 勤務年数：年の数字を要確認"
                )

            else:

                # 0ヶ月専用救済
                if years.months_zero_visible:

                    months = 0

                else:

                    months = years.months_value


                if months is None:

                    st.warning(
                        "🔍 勤務年数："
                        "ヶ月の記入はありますが数字を要確認"
                    )

                elif months < 0 or months > 11:

                    st.warning(
                        "🔍 勤務年数："
                        f"{years.year_value}年{months}ヶ月 "
                        "（ヶ月を確認してください）"
                    )

                else:

                    st.success(
                        "✅ 勤務年数："
                        f"{years.year_value}年{months}ヶ月"
                    )


        # ====================================================
        # 業種
        # ====================================================

        with st.spinner(
            "業種を確認中..."
        ):

            industry = safe_ask(

                p1,

                COMMON + PAGE1 + """
B：本人勤務先ブロック内の
印刷された「業種」だけを確認。

まず業種ラベルを特定。

その業種の選択肢領域内に
手書き○がある場合だけ

circle_visible=true。

雇用形態やその他の○は
使用禁止。
""",

                IndustryResult
            )


        if industry:

            if (
                industry.uncertain
                or not industry.field_located
            ):

                st.warning(
                    "🔍 業種：要確認"
                )

            elif industry.circle_visible:

                st.success(
                    "✅ 業種：選択あり"
                )

            else:

                st.error(
                    "❌ 業種：選択なし"
                )


        # ====================================================
        # 世帯状況
        # ====================================================

        with st.spinner(
            "世帯状況を確認中..."
        ):

            household = safe_ask(

                p1,

                COMMON + PAGE1 + """
C：世帯主・世帯状況だけを確認。

必要な記入項目と
必要な選択項目が埋まっているか確認。

ただし、
世帯主確認欄の右側にある
「連絡先」は空欄でも問題ありません。

月あたりクレジット金額は
この判定では扱いません。
""",

                HouseholdBasicResult
            )


        if household:

            st.subheader(
                "世帯状況"
            )

            if (
                household.uncertain
                or not household.field_located
            ):

                st.warning(
                    "🔍 世帯状況：要確認"
                )

            elif (
                household.required_entries_present
                and household.required_selections_present
            ):

                st.success(
                    "✅ 世帯状況：必要項目記入あり"
                )

            else:

                st.error(
                    "❌ 世帯状況：記入・選択漏れあり"
                )


        # ====================================================
        # ★ 月あたりクレジット
        # ====================================================

        with st.spinner(
            "月あたりクレジットを確認中..."
        ):

            monthly_credit = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認するのは1つだけ。

C：世帯状況ブロックの

「世帯主のクレジットの
月あたりのお支払額」

という印刷欄です。


━━━━━━━━━━━━━━━━━━━━━━

まずこの印刷ラベルを
確実に特定してください。

そのラベルに直接対応する
金額記入欄だけを見る。


━━━━━━━━━━━━━━━━━━━━━━

すぐ近くにある

「世帯主の年収(税込)」

は絶対に使用禁止。


例：

年収欄に
400万円

と書かれていても、

月あたり支払額を
400万円や400000円と
判断してはいけません。


━━━━━━━━━━━━━━━━━━━━━━

指定された月額欄に
手書き筆跡が存在する場合：

handwriting_visible=true


金額を明確に読める場合だけ：

amount_readable=true

amount_yenに円単位整数を入れる。


8万円 → 80000

10万円 → 100000

12万円 → 120000


欄に記入はあるが
金額が不鮮明：

handwriting_visible=true
amount_readable=false
uncertain=true
""",

                MonthlyCreditResult
            )


        if monthly_credit:

            if (
                monthly_credit.uncertain
                or not monthly_credit.exact_field_located
            ):

                st.warning(
                    "🔍 月あたりクレジット支払額：要確認"
                )

            elif not monthly_credit.handwriting_visible:

                st.error(
                    "❌ 月あたりクレジット支払額：未記入"
                )

            elif (
                not monthly_credit.amount_readable
                or monthly_credit.amount_yen is None
            ):

                st.warning(
                    "🔍 月あたりクレジット支払額："
                    "記入あり・金額要確認"
                )

            elif monthly_credit.amount_yen > 100000:

                st.error(
                    "⚠️ 月あたりクレジット支払額："
                    f"{monthly_credit.amount_yen:,}円 "
                    "（10万円超）"
                )

            else:

                st.success(
                    "✅ 月あたりクレジット支払額："
                    f"{monthly_credit.amount_yen:,}円"
                )


        # ====================================================
        # 関係者
        # ====================================================

        if relation_enabled:

            with st.spinner(
                "関係者情報を確認中..."
            ):

                relation = safe_ask(

                    p1,

                    COMMON + PAGE1 + """
D：関係者情報ブロックだけ。

本人欄から情報を流用禁止。

確認：

氏名
氏名フリガナ
性別
生年月日
ご契約者との関係
住所
郵便番号
住居
連絡先
税込年収
勤務年数
給料日
会社名
所在地
所在地郵便番号
所在地電話番号

雇用形態だけは
別判定するのでここでは扱わない。

関係者住所は、

実際の住所
または
「同上」

のどちらでも記入あり。

ただし郵便番号は別途必要。
""",

                    RelationBasicResult
                )


            if relation:

                st.subheader(
                    "関係者情報"
                )

                show_field(
                    "関係者情報・氏名",
                    relation.name
                )

                show_field(
                    "関係者情報・氏名フリガナ",
                    relation.name_furigana
                )

                show_circle(
                    "関係者情報・性別",
                    relation.gender
                )

                show_field(
                    "関係者情報・生年月日",
                    relation.birth_date
                )

                show_field(
                    "関係者情報・ご契約者との関係",
                    relation.relationship
                )

                show_field(
                    "関係者情報・ご住所",
                    relation.address
                )

                show_field(
                    "関係者情報・ご住所の郵便番号",
                    relation.postal_code
                )

                show_circle(
                    "関係者情報・ご住居",
                    relation.residence
                )

                show_field(
                    "関係者情報・連絡先",
                    relation.contact
                )

                show_field(
                    "関係者情報・税込年収",
                    relation.annual_income
                )


            # ================================================
            # ★ 関係者 雇用形態専用
            # ================================================

            with st.spinner(
                "関係者の雇用形態を確認中..."
            ):

                relation_emp = safe_ask(

                    p1,

                    COMMON + PAGE1 + """
今回見るのは

D：関係者情報ブロック内の
「雇用形態」

だけです。


━━━━━━━━━━━━━━━━━━━━━━

本人勤務先の雇用形態ではありません。

必ず最初に

「関係者情報」

という大きなブロックを特定してください。

その中にある

「雇用形態」

という印刷ラベルを探します。


━━━━━━━━━━━━━━━━━━━━━━

今回は、

どの職種が選ばれているかを
読み取ることより、

「関係者の雇用形態欄の
選択肢領域に手書き○が
1つ以上存在するか」

を最優先で確認してください。


手書き○が存在すれば

circle_visible=true

です。


━━━━━━━━━━━━━━━━━━━━━━

○が印刷文字に重なっていても
選択ありです。

○の中の文字を
完全にOCRできなくても構いません。


━━━━━━━━━━━━━━━━━━━━━━

【絶対禁止】

本人の雇用形態の○
本人の業種の○
本人の性別
関係者の性別
関係者の住居

などを流用禁止。


━━━━━━━━━━━━━━━━━━━━━━

関係者の雇用形態領域に
○らしい手書き筆跡が見えるが
確信できない場合：

uncertain=true

明確に○がある場合：

field_located=true
circle_visible=true
uncertain=false

本当に○がない場合だけ：

field_located=true
circle_visible=false
uncertain=false
""",

                    RelationEmploymentResult
                )


            if relation_emp:

                if (
                    relation_emp.uncertain
                    or not relation_emp.field_located
                ):

                    st.warning(
                        "🔍 関係者情報・雇用形態：要確認"
                    )

                elif relation_emp.circle_visible:

                    st.success(
                        "✅ 関係者情報・雇用形態：選択あり"
                    )

                else:

                    st.error(
                        "❌ 関係者情報・雇用形態：選択なし"
                    )


            if relation:

                show_field(
                    "関係者情報・勤務年数",
                    relation.years_employed
                )

                show_field(
                    "関係者情報・給料日",
                    relation.payday
                )

                show_field(
                    "関係者情報・会社名",
                    relation.company_name
                )

                show_field(
                    "関係者情報・所在地",
                    relation.company_location
                )

                show_field(
                    "関係者情報・所在地の郵便番号",
                    relation.company_postal_code
                )

                show_field(
                    "関係者情報・所在地の電話番号",
                    relation.company_phone
                )


        # ====================================================
        # 銀行
        # ====================================================

        with st.spinner(
            "銀行口座を確認中..."
        ):

            bank = safe_ask(

                p1,

                COMMON + PAGE1 + """
E：銀行口座だけを確認。

ゆうちょ銀行側、
または
ゆうちょ銀行以外の銀行側、

どちらか一方に必要な口座記入があればOK。

両方を必須にしない。

さらに、
下部の「口座名義人」に対応する
フリガナ欄を確認。
""",

                BankResult
            )


        if bank:

            st.subheader(
                "銀行口座"
            )

            if (
                bank.uncertain
                or not bank.section_located
            ):

                st.warning(
                    "🔍 銀行口座：要確認"
                )

            elif (
                bank.japan_post_has_entry
                or bank.other_bank_has_entry
            ):

                st.success(
                    "✅ 銀行口座：記入あり"
                )

            else:

                st.error(
                    "❌ 銀行口座：未記入"
                )


            show_field(
                "口座名義人フリガナ",
                bank.account_holder_furigana
            )


        # ====================================================
        # 契約関連
        # ====================================================

        with st.spinner(
            "契約情報を確認中..."
        ):

            contract = safe_ask(

                p1,

                COMMON + PAGE1 + """
F：契約関連。

確認するのは正確に次の2つ。

・役務提供期間

・特定商取引法第42条第2項
または第3項書面の受領年月日

受領年月日は
その指定欄の
年・月・日が記入されているか確認。

別の日付を流用禁止。
""",

                ContractResult
            )


        if contract:

            st.subheader(
                "契約情報"
            )

            show_field(
                "役務提供期間",
                contract.service_period
            )

            show_field(
                "特定商取引法第42条第2項又は第3項書面の受領年月日",
                contract.article42_receipt_date
            )


    # ========================================================
    # PAGE 2
    # ========================================================

    if page2_file:

        p2 = prepare_image(
            Image.open(page2_file)
        )

        st.header(
            "② 役務申込書・指導内容"
        )


        # ====================================================
        # 保護者
        # ====================================================

        with st.spinner(
            "保護者情報を確認中..."
        ):

            guardian = safe_ask(

                p2,

                COMMON + PAGE2 + """
「保護者氏名」に直接対応する
フリガナ欄だけを確認。

フリガナ欄に
手書き文字が存在すればOK。

他の氏名フリガナを流用禁止。
""",

                GuardianResult
            )


        if guardian:

            st.subheader(
                "保護者情報"
            )

            show_field(
                "保護者氏名フリガナ",
                guardian.guardian_name_furigana
            )


        # ====================================================
        # PAGE2住所
        # ====================================================

        with st.spinner(
            "住所を確認中..."
        ):

            p2_address = safe_ask(

                p2,

                COMMON + PAGE2 + """
「ご住所・連絡先」の
住所欄だけを確認。

必要条件は2つ。

1.
住所文字列に
都道府県名が明示されている。

市区町村から推測禁止。

2.
印刷された
「都・道・府・県」のうち
その住所に対応するものに
手書き○がある。

両方を別々に確認。
""",

                Page2AddressResult
            )


        if p2_address:

            st.subheader(
                "ご住所・連絡先"
            )

            if (
                p2_address.uncertain
                or not p2_address.field_located
            ):

                st.warning(
                    "🔍 ご住所：要確認"
                )

            elif not p2_address.has_entry:

                st.error(
                    "❌ ご住所：未記入"
                )

            else:

                if p2_address.prefecture_explicit:

                    st.success(
                        "✅ ご住所：都道府県名あり"
                    )

                else:

                    st.error(
                        "❌ ご住所：都道府県名なし"
                    )


                if not p2_address.prefecture_selector_located:

                    st.warning(
                        "🔍 都・道・府・県：要確認"
                    )

                elif p2_address.appropriate_prefecture_circle:

                    st.success(
                        "✅ 都・道・府・県：○あり"
                    )

                else:

                    st.error(
                        "❌ 都・道・府・県：適切な○なし"
                    )


        # ====================================================
        # 指導対象A
        # ====================================================

        with st.spinner(
            "指導対象Aを確認中..."
        ):

            target = safe_ask(

                p2,

                COMMON + PAGE2 + """
右上の
「指導対象A」を特定。

そのAに対応する
印刷された「有」に
実際の手書き○があるかだけ確認。

他の○を流用禁止。
""",

                TargetAResult
            )


        if target:

            if (
                target.uncertain
                or not target.field_located
            ):

                st.warning(
                    "🔍 指導対象A：要確認"
                )

            elif target.yes_circle_visible:

                st.success(
                    "✅ 指導対象A：「有」に○あり"
                )

            else:

                st.error(
                    "❌ 指導対象A：「有」に○なし"
                )


        # ====================================================
        # 公・国・私
        # ====================================================

        with st.spinner(
            "学校区分を確認中..."
        ):

            school = safe_ask(

                p2,

                COMMON + PAGE2 + """
右上の学校情報にある

公
国
私

の3つだけを確認。

それぞれに
手書き○があるか判断。

性別、
指導対象A、
学校種別以外の○を
使用禁止。
""",

                SchoolResult
            )


        if school:

            school_choices = [

                name

                for name, value in [

                    (
                        "公",
                        school.public_circle
                    ),

                    (
                        "国",
                        school.national_circle
                    ),

                    (
                        "私",
                        school.private_circle
                    )

                ]

                if value
            ]


            if (
                school.uncertain
                or not school.field_located
            ):

                st.warning(
                    "🔍 公・国・私：要確認"
                )

            elif len(school_choices) == 0:

                st.error(
                    "❌ 公・国・私：選択なし"
                )

            elif len(school_choices) > 1:

                st.error(
                    "❌ 公・国・私：複数選択 "
                    + " / ".join(school_choices)
                )

            else:

                st.success(
                    "✅ 公・国・私："
                    + school_choices[0]
                )


        # ====================================================
        # コース
        # ====================================================

        with st.spinner(
            "コース名を確認中..."
        ):

            course = safe_ask(

                p2,

                COMMON + PAGE2 + """
印刷された
「コース名」

のすぐ横の指定欄だけを見る。

この指定欄に、

週1
かつ
90分

という意味の記入が必要。

近くにある

4回/月

だけを見て
条件達成としてはいけません。
""",

                CourseResult
            )


        if course:

            if (
                course.uncertain
                or not course.field_located
            ):

                st.warning(
                    "🔍 コース名：要確認"
                )

            elif not course.has_entry:

                st.error(
                    "❌ コース名：未記入"
                )

            elif (
                course.weekly_once
                and course.ninety_minutes
            ):

                st.success(
                    "✅ コース名：週1・90分"
                )

            else:

                st.error(
                    "❌ コース名："
                    "週1・90分を確認できません"
                )


        # ====================================================
        # 初回指導日 / 役務提供期間
        # ====================================================

        with st.spinner(
            "日付・期間を確認中..."
        ):

            dates = safe_ask(

                p2,

                COMMON + PAGE2 + """
確認するのは、

・初回指導日
・役務提供期間A

だけ。

役務提供期間は
A行だけが対象。

B行が空欄でも問題ありません。
""",

                Page2DatesResult
            )


        if dates:

            show_field(
                "初回指導日",
                dates.first_instruction_date
            )

            show_field(
                "役務提供期間A",
                dates.service_period_a
            )


        # ====================================================
        # 受領サイン
        # ====================================================

        with st.spinner(
            "受領サインを確認中..."
        ):

            receipt = safe_ask(

                p2,

                COMMON + PAGE2 + """
今回見るのは
受領サインだけ。

書類の最上部右側。

「書面交付日」と
同じ上部バーにある

「受領サイン →」

を探す。

矢印の直後にある
指定記入領域だけを確認。

そこに手書き署名があれば

signature_visible=true。

保護者氏名
契約者氏名
生徒氏名
その他の署名

を流用禁止。
""",

                ReceiptResult
            )


        if receipt:

            if (
                receipt.uncertain
                or not receipt.field_located
            ):

                st.warning(
                    "🔍 受領サイン：要確認"
                )

            elif receipt.signature_visible:

                st.success(
                    "✅ 受領サイン：記入あり"
                )

            else:

                st.error(
                    "❌ 受領サイン：未記入"
                )


        # ====================================================
        # 数量
        # ====================================================

        with st.spinner(
            "数量を確認中..."
        ):

            quantity = safe_ask(

                p2,

                COMMON + PAGE2 + """
教材・数量表だけを確認。


━━━━━━━━━━━━━━━━━━━━━━

まず表の印刷された列見出し

「数量」

を必ず特定。


━━━━━━━━━━━━━━━━━━━━━━

各対象行について、

数量列より左側にある
同じ行の手書き数量要素を

horizontal_values

に入れる。


例：

1 1 1

なら

[1,1,1]


━━━━━━━━━━━━━━━━━━━━━━

次に、

同じ行の
「数量」列セルそのものを見る。


そこに手書き数字があるなら

quantity_handwriting_visible=true

written_quantityに
その数字を入れる。


空欄なら

quantity_handwriting_visible=false
written_quantity=null


━━━━━━━━━━━━━━━━━━━━━━

【絶対禁止】

数量を自分で計算して
written_quantityに補完禁止。

written_quantityは
実際に数量セルに書かれている数字だけ。


━━━━━━━━━━━━━━━━━━━━━━

数量列より右側にある

各単価
小計
合計
金額

は絶対に数量ではない。


特に

36000
108000
648000
712800

などを
数量として使用禁止。


━━━━━━━━━━━━━━━━━━━━━━

数量セルに筆跡があるが
数字が読めない場合：

quantity_handwriting_visible=true
written_quantity=null
uncertain=true
""",

                QuantityResult
            )


        if quantity:

            st.subheader(
                "数量"
            )

            if quantity.uncertain:

                st.warning(
                    "🔍 数量表：要確認"
                )

            elif not quantity.table_located:

                st.warning(
                    "🔍 数量表を特定できません"
                )

            elif not quantity.applicable_rows_visible:

                st.warning(
                    "🔍 数量：対象行を特定できません"
                )

            elif len(quantity.rows) == 0:

                st.warning(
                    "🔍 数量：対象行を特定できません"
                )

            else:

                for row in quantity.rows:

                    expected = sum(
                        row.horizontal_values
                    )


                    if row.uncertain:

                        st.warning(
                            f"🔍 {row.row_label}：要確認"
                        )

                        continue


                    if not row.quantity_cell_located:

                        st.warning(
                            f"🔍 {row.row_label}："
                            "数量欄を特定できません"
                        )

                        continue


                    if not row.quantity_handwriting_visible:

                        st.error(
                            f"❌ {row.row_label}："
                            f"横合計 {expected} / "
                            "数量欄 未記入"
                        )

                        continue


                    if row.written_quantity is None:

                        st.warning(
                            f"🔍 {row.row_label}："
                            "数量欄に記入あり・数字要確認"
                        )

                        continue


                    # 金額列誤読の防御
                    if row.written_quantity >= 1000:

                        st.warning(
                            f"🔍 {row.row_label}："
                            f"{row.written_quantity}を検出。"
                            "金額列の誤読の可能性あり"
                        )

                        continue


                    if row.written_quantity == expected:

                        st.success(
                            f"✅ {row.row_label}："
                            f"横合計 {expected} / "
                            f"数量 {row.written_quantity}"
                        )

                    else:

                        st.error(
                            f"❌ {row.row_label}："
                            f"横合計 {expected} / "
                            f"数量 {row.written_quantity}"
                        )


    # ========================================================
    # 完了
    # ========================================================

    st.divider()

    st.success(
        "チェック完了"
    )

    st.caption(
        "🔍 要確認になった項目は、"
        "AIが画像から確実に判断できなかった項目です。"
        "提出前に人の目でも最終確認してください。"
    )
