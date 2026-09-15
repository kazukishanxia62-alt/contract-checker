import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from typing import List
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
st.caption("提出前の記入漏れ・選択漏れをAIで確認します。")

st.info(
    "このアプリは提出前チェックの補助ツールです。"
    "最終確認は必ず人が行ってください。"
)


# ============================================================
# Gemini
# ============================================================

try:
    client = genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"]
    )
except Exception as e:
    st.error("Gemini APIの設定エラーです。")
    st.code(str(e))
    st.stop()


MODEL = "gemini-3.1-pro-preview"


# ============================================================
# 共通データ型
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
# 勤務年数専用
# ============================================================

class WorkYearsCheck(BaseModel):
    field_located: bool

    year_has_entry: bool
    year_value: int | None = None

    months_has_entry: bool
    months_value: int | None = None

    uncertain: bool = False


# ============================================================
# 1枚目：契約者
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
# 1枚目：勤務先
# ============================================================

class EmploymentResult(BaseModel):
    field_located: bool

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


class WorkResult(BaseModel):
    company_name: FieldCheck
    company_address: FieldCheck
    company_postal_code: FieldCheck
    company_phone: FieldCheck
    years_employed: FieldCheck
    payday: FieldCheck

    dispatch_destination: FieldCheck


class IndustryResult(BaseModel):
    field_located: bool
    circle_present: bool
    uncertain: bool


# ============================================================
# 1枚目：世帯
# ============================================================

class HouseholdResult(BaseModel):
    field_located: bool

    household_required_entries_present: bool
    household_required_selections_present: bool

    monthly_credit_field_located: bool
    monthly_credit_has_entry: bool

    monthly_credit_yen: int | None = None

    uncertain: bool


# ============================================================
# 1枚目：関係者情報
# ============================================================

class RelationResult(BaseModel):
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
    employment_type: CircleCheck
    years_employed: FieldCheck
    payday: FieldCheck
    company_name: FieldCheck
    company_location: FieldCheck
    company_postal_code: FieldCheck
    company_phone: FieldCheck


# ============================================================
# 1枚目：銀行・契約
# ============================================================

class BankResult(BaseModel):
    bank_section_located: bool

    japan_post_side_has_entry: bool
    other_bank_side_has_entry: bool

    account_holder_furigana: FieldCheck

    uncertain: bool


class ContractInfoResult(BaseModel):
    service_period: FieldCheck
    article42_receipt_date: FieldCheck


# ============================================================
# 2枚目
# ============================================================

class GuardianResult(BaseModel):
    guardian_name_furigana: FieldCheck


class Page2AddressResult(BaseModel):
    address_field_located: bool
    address_has_entry: bool

    prefecture_name_explicit: bool

    prefecture_mark_field_located: bool
    correct_prefecture_mark_circled: bool

    uncertain: bool


class TargetAResult(BaseModel):
    field_located: bool
    yes_circled: bool
    uncertain: bool


class SchoolCategoryResult(BaseModel):
    field_located: bool

    public_circled: bool
    national_circled: bool
    private_circled: bool

    uncertain: bool


class CourseResult(BaseModel):
    field_located: bool
    has_entry: bool

    weekly_once_present: bool
    ninety_minutes_present: bool

    uncertain: bool


class Page2DatesResult(BaseModel):
    first_instruction_date: FieldCheck
    service_period_a: FieldCheck


class ReceiptResult(BaseModel):
    field_located: bool
    has_signature: bool
    uncertain: bool


# ============================================================
# 数量
# ============================================================

class QuantityRow(BaseModel):
    row_label: str

    horizontal_values: List[int] = Field(
        default_factory=list
    )

    written_quantity: str = ""

    quantity_box_has_handwriting: bool = False


class QuantityResult(BaseModel):
    table_located: bool
    applicable_rows_detected: bool

    rows: List[QuantityRow] = Field(
        default_factory=list
    )

    uncertain: bool


# ============================================================
# 共通プロンプト
# ============================================================

COMMON = """
あなたは日本の契約書の
「提出前記入漏れチェック」を行います。

非常に重要です。

このアプリは契約内容が事実として正しいかを
審査するものではありません。

原則として確認するのは、

・指定欄に記入があるか
・指定選択肢に手書きの○があるか
・明示された特別ルールを満たすか

だけです。


【絶対ルール】

別の欄にある文字・数字・○を、
対象欄のものとして流用してはいけません。

対象欄を特定するときは、

1. 書類全体
2. 大きなブロック
3. 上下左右の隣接ブロック
4. 印刷された対象ラベル
5. 同じ行・同じ欄の位置関係
6. その欄の手書き記入

の順番で確認してください。

対象欄の位置を確定できなければ、
推測してOKにしてはいけません。

その場合は uncertain=true にしてください。


【存在チェック】

氏名、フリガナ、会社名、勤務年数などは、
原則として指定欄に手書き記入が存在すればOKです。

フリガナについて、
氏名との読み方の一致を審査しません。

会社名について、
実在性や正式名称の正しさを審査しません。


【○チェック】

選択式項目は文字認識だけで判断せず、
指定された印刷文字の上または周囲に
実際の手書き○が存在するか確認してください。


【内容まで確認する特別項目】

・住所の都道府県
・月額クレジット支払額10万円
・数量一致
・週1回90分
・公・国・私
・その他この指示で明示されたもの

だけは内容まで確認します。
"""


PAGE1_STRUCTURE = """
【1枚目の書類構造】

これはクレジット申込書です。

書類を大きく見ると、
上から下へ概ね次の構造になっています。

A：ご契約者本人情報
B：ご契約者の勤務先情報
C：世帯主・世帯状況
D：関係者情報
E：銀行口座情報
F：契約関連情報

必ずこの構造を使って
対象欄を特定してください。


【勤務先ブロック】

雇用形態・業種・会社名等は
Bの勤務先ブロックにあります。

本人情報や関係者情報にある○を
勤務先の○として扱ってはいけません。


【雇用形態の印刷順】

雇用形態は概ね、

1段目：
正社員
派遣社員
契約社員
パート・アルバイト

2段目：
公務員
事業者
主婦
年金
学生

の順です。

特に
「派遣社員」と「契約社員」は隣接しています。

○の中心位置が
どの印刷選択肢に対応しているかで判定してください。


【派遣先】

「派遣先・出向先の会社名」は
雇用形態付近にあります。

派遣社員が選択された場合のみ
必須になります。


【世帯状況】

「世帯主の年収(税込)」と
「世帯主のクレジットの月あたりのお支払額」は
別の項目です。

絶対に混同しないでください。

年収欄の
400万円、500万円等を
月額クレジット支払額として
読み取ってはいけません。


【関係者情報】

Dブロックは本人情報とは別です。

本人の住所、電話番号、勤務先などを
関係者情報として流用してはいけません。


【銀行】

ゆうちょ銀行側と
ゆうちょ銀行以外の銀行側があります。

どちらか一方に必要な記入があればよく、
両方を必須にしてはいけません。
"""


PAGE2_STRUCTURE = """
【2枚目の書類構造】

これは役務申込書・指導内容です。

大きく、

左上：
契約者・保護者関連

右上：
指導対象A/B/C・学校関連

中央～下：
コース・指導内容・期間

中央右～下：
教材・数量・各単価・小計の表

最上部右側：
書面交付日と受領サイン

という構造です。


【受領サイン】

受領サインは
書類右上の上部バーにあります。

印刷された

「受領サイン →」

のすぐ右側の指定欄だけを確認してください。

書類内の他の氏名や署名を
受領サインとして使用してはいけません。


【数量表】

表には概ね

横方向の選択・学年等
→ 数量
→ 各単価
→ 小計

という列関係があります。

必ず印刷された「数量」列を特定してください。

「数量」より右側にある
各単価、小計、合計の金額は
数量ではありません。
"""


# ============================================================
# Gemini呼び出し
# ============================================================

def prepare_image(image):
    image = ImageOps.exif_transpose(
        image
    ).convert("RGB")

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=97
    )

    return buffer.getvalue()


def ask_gemini(image_bytes, prompt, schema):

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


# ============================================================
# 表示関数
# ============================================================

def show_field(label, field):

    if field.uncertain or not field.located:
        st.warning(f"🔍 {label}：要確認")

    elif field.has_entry:
        st.success(f"✅ {label}：記入あり")

    else:
        st.error(f"❌ {label}：未記入")


def show_circle(label, field):

    if field.uncertain or not field.located:
        st.warning(f"🔍 {label}：要確認")

    elif field.has_circle:
        st.success(f"✅ {label}：選択あり")

    else:
        st.error(f"❌ {label}：選択なし")


def show_work_years(label, result):

    if result.uncertain or not result.field_located:
        st.warning(f"🔍 {label}：要確認")
        return

    if (
        not result.year_has_entry
        and not result.months_has_entry
    ):
        st.error(
            f"❌ {label}：年・ヶ月とも未記入"
        )
        return

    if not result.year_has_entry:

        if result.months_value is not None:
            st.error(
                f"❌ {label}：年が未記入"
                f"（ヶ月：{result.months_value}ヶ月）"
            )
        else:
            st.error(
                f"❌ {label}：年が未記入"
            )

        return

    if not result.months_has_entry:

        if result.year_value is not None:
            st.error(
                f"❌ {label}：ヶ月が未記入"
                f"（年：{result.year_value}年）"
            )
        else:
            st.error(
                f"❌ {label}：ヶ月が未記入"
            )

        return

    if (
        result.year_value is None
        or result.months_value is None
    ):
        st.warning(
            f"🔍 {label}："
            "数字を正確に読み取れません"
        )
        return

    if (
        result.months_value < 0
        or result.months_value > 11
    ):
        st.warning(
            f"🔍 {label}："
            f"{result.year_value}年"
            f"{result.months_value}ヶ月 "
            "（ヶ月の値を確認してください）"
        )
        return

    st.success(
        f"✅ {label}："
        f"{result.year_value}年"
        f"{result.months_value}ヶ月"
    )


def safe_analysis(image_bytes, prompt, schema):

    try:
        return ask_gemini(
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
# UI
# ============================================================

st.divider()

relation_enabled = st.checkbox(
    "1枚目の「関係者情報」もチェックする",
    value=True
)

st.subheader("① クレジット申込書")

page1_file = st.file_uploader(
    "1枚目の写真を選択",
    type=["jpg", "jpeg", "png", "webp"],
    key="page1"
)

st.subheader("② 役務申込書・指導内容")

page2_file = st.file_uploader(
    "2枚目の写真を選択",
    type=["jpg", "jpeg", "png", "webp"],
    key="page2"
)


if page1_file:

    p1_image = Image.open(page1_file)

    st.image(
        p1_image,
        caption="① クレジット申込書",
        use_container_width=True
    )


if page2_file:

    p2_image = Image.open(page2_file)

    st.image(
        p2_image,
        caption="② 役務申込書・指導内容",
        use_container_width=True
    )


st.divider()


# ============================================================
# 実行
# ============================================================

if st.button(
    "契約書をチェック",
    type="primary",
    use_container_width=True
):

    if not page1_file and not page2_file:

        st.warning(
            "契約書の写真を選択してください。"
        )

        st.stop()


    # ========================================================
    # PAGE 1
    # ========================================================

    if page1_file:

        st.header("① クレジット申込書")

        p1_image = Image.open(page1_file)

        p1_bytes = prepare_image(
            p1_image
        )


        # ----------------------------------------------------
        # 本人情報
        # ----------------------------------------------------

        with st.spinner(
            "① ご契約者情報を確認中..."
        ):

            applicant = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【今回の対象】

A：ご契約者本人情報だけを確認してください。

確認対象：

・氏名
・氏名フリガナ
・性別
・生年月日
・ご住所
・ご住所のフリガナ
・郵便番号
・ご住居
・固定電話
・携帯電話

住所フリガナは、
本人住所に対応する
「住所のフリガナ欄」だけを見てください。

氏名フリガナを
住所フリガナとして使用してはいけません。

電話は、
固定電話または携帯電話の
どちらか一方が記入されていれば
連絡先としてOKです。
""",
                ApplicantResult
            )


        if applicant:

            st.subheader("ご契約者")

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
                    "❌ 連絡先：固定電話・携帯電話とも未記入"
                )


        # ----------------------------------------------------
        # 都道府県
        # ----------------------------------------------------

        with st.spinner(
            "① 住所の都道府県を確認中..."
        ):

            address_rule = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

ご契約者本人の
「ご契約者のご住所」欄だけを確認してください。

住所が実在するかは確認しません。

ただし住所文字列そのものに
都道府県名が明示されている必要があります。

例：

大阪府大阪市...
→ prefecture_explicit=true

大阪市...
→ prefecture_explicit=false

市区町村名から都道府県を
推測してはいけません。

印刷されたフォーム側の
「都・道・府・県」の文字だけでは
都道府県記入とはみなしません。
""",
                AddressRuleResult
            )


        if address_rule:

            if address_rule.uncertain:

                st.warning(
                    "🔍 住所の都道府県：要確認"
                )

            elif not address_rule.has_entry:

                st.error(
                    "❌ ご住所：未記入"
                )

            elif address_rule.prefecture_explicit:

                st.success(
                    "✅ ご住所：都道府県から記入"
                )

            else:

                st.error(
                    "❌ ご住所：都道府県名から記入してください"
                )


        # ----------------------------------------------------
        # 雇用形態
        # ----------------------------------------------------

        with st.spinner(
            "① 雇用形態を確認中..."
        ):

            employment = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【今回の対象】

B：ご契約者本人の勤務先ブロックにある
「雇用形態」だけを確認してください。

選択肢は：

正社員
派遣社員
契約社員
パート・アルバイト
公務員
事業者
主婦
年金
学生

です。

各選択肢に
実際に手書き○が重なっている場合のみ
trueにしてください。

別の選択欄の○を使用禁止。
""",
                EmploymentResult
            )


        dispatch_selected = False

        if employment:

            st.subheader("勤務先")

            emp_options = [
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
                for name, value in emp_options
                if value
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

            elif len(selected) == 0:

                st.error(
                    "❌ 雇用形態：選択なし"
                )

            elif len(selected) > 1:

                st.warning(
                    "🔍 雇用形態：複数検出 "
                    + " / ".join(selected)
                )

            else:

                st.success(
                    "✅ 雇用形態：" + selected[0]
                )


        # ----------------------------------------------------
        # 勤務先情報
        # ----------------------------------------------------

        with st.spinner(
            "① 勤務先情報を確認中..."
        ):

            work = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

ご契約者本人の勤務先ブロックだけ。

確認するのは：

・会社名
・所在地
・所在地の郵便番号
・所在地の電話番号
・勤務年数
・給料日
・派遣先・出向先の会社名

それぞれ指定欄に
記入が存在するかだけ確認してください。

派遣先・出向先については、
指定された欄そのものだけを確認してください。
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
                "勤務年数・記入",
                work.years_employed
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

            else:

                st.info(
                    "ℹ️ 派遣先・出向先：対象外"
                )


        # ----------------------------------------------------
        # ★ 本人の勤務年数「年・ヶ月」専用判定
        # ----------------------------------------------------

        with st.spinner(
            "① 勤務年数の年・ヶ月を確認中..."
        ):

            applicant_work_years = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【今回の対象は1つだけ】

ご契約者本人の勤務先ブロックにある
「勤務年数」欄だけを確認してください。

関係者情報の勤務年数ではありません。

まず、
ご契約者勤務先ブロックの
印刷された「勤務年数」ラベルを
確実に特定してください。

その欄に印刷されている

「年」
「ヶ月」

を基準にします。


【判定方法】

「年」の直前の記入スペースに
手書き数字が存在するか。

「ヶ月」の直前の記入スペースに
手書き数字が存在するか。

を別々に判定してください。


例：

2年4ヶ月

year_has_entry=true
year_value=2

months_has_entry=true
months_value=4


2年0ヶ月

year_has_entry=true
year_value=2

months_has_entry=true
months_value=0


0年6ヶ月

year_has_entry=true
year_value=0

months_has_entry=true
months_value=6


2年　ヶ月

year_has_entry=true
year_value=2

months_has_entry=false
months_value=null


年　6ヶ月

year_has_entry=false
year_value=null

months_has_entry=true
months_value=6


【絶対禁止】

・生年月日の年や月
・契約年月日
・年収
・給料日
・関係者情報の勤務年数
・その他の数字

を使用してはいけません。

実際に「0」と書いてあれば、
0も記入ありです。

対象の勤務年数欄を
確実に特定できない場合は
uncertain=true。
""",
                WorkYearsCheck
            )


        if applicant_work_years:

            show_work_years(
                "勤務年数",
                applicant_work_years
            )


        # ----------------------------------------------------
        # 業種
        # ----------------------------------------------------

        with st.spinner(
            "① 業種を確認中..."
        ):

            industry = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

ご契約者本人の勤務先ブロック内の
印刷された「業種」欄だけ。

まず「業種」ラベルを確認し、
その業種選択肢の範囲内に
手書き○が存在する場合だけ
circle_present=true。

雇用形態、
性別、
住居、
世帯状況、
関係者情報等の○は使用禁止。
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

            elif industry.circle_present:

                st.success(
                    "✅ 業種：選択あり"
                )

            else:

                st.error(
                    "❌ 業種：選択なし"
                )


        # ----------------------------------------------------
        # 世帯状況
        # ----------------------------------------------------

        with st.spinner(
            "① 世帯状況を確認中..."
        ):

            household = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

C：世帯主・世帯状況ブロック。

必要な記入欄・選択欄に
記入または○が存在するか確認してください。

さらに、

「世帯主のクレジットの
月あたりのお支払額」

という正確な欄を探してください。

その欄に金額があれば
円換算した整数を
monthly_credit_yen にしてください。

絶対に
「世帯主の年収(税込)」
を使用しないでください。

月額欄を確実に特定できない場合は
uncertain=true。

右側の「連絡先」は
空欄でも問題ありません。
""",
                HouseholdResult
            )


        if household:

            st.subheader("世帯状況")

            if household.uncertain:

                st.warning(
                    "🔍 世帯状況：要確認"
                )

            else:

                if (
                    household.household_required_entries_present
                    and household.household_required_selections_present
                ):

                    st.success(
                        "✅ 世帯状況：必要項目記入あり"
                    )

                else:

                    st.error(
                        "❌ 世帯状況：必要項目に記入漏れあり"
                    )


                if not household.monthly_credit_field_located:

                    st.warning(
                        "🔍 月あたりクレジット支払額：要確認"
                    )

                elif not household.monthly_credit_has_entry:

                    st.error(
                        "❌ 月あたりクレジット支払額：未記入"
                    )

                elif household.monthly_credit_yen is None:

                    st.warning(
                        "🔍 月あたりクレジット支払額：金額要確認"
                    )

                elif household.monthly_credit_yen > 100000:

                    st.error(
                        "⚠️ 世帯主のクレジット月額："
                        f"{household.monthly_credit_yen:,}円 "
                        "（10万円超）"
                    )

                else:

                    st.success(
                        "✅ 世帯主のクレジット月額："
                        f"{household.monthly_credit_yen:,}円"
                    )


        # ----------------------------------------------------
        # 関係者情報
        # ----------------------------------------------------

        if relation_enabled:

            with st.spinner(
                "① 関係者情報を確認中..."
            ):

                relation = safe_analysis(
                    p1_bytes,

                    COMMON
                    + PAGE1_STRUCTURE
                    + """
【対象】

D：関係者情報ブロックだけ。

本人情報を絶対に流用しないでください。

確認項目：

氏名
氏名フリガナ
性別
生年月日
ご契約者との関係
ご住所
ご住所の郵便番号
ご住居
連絡先
税込年収
雇用形態
勤務年数
給料日
会社名
所在地
所在地の郵便番号
所在地の電話番号

住所は実住所でも
「同上」でも記入ありとしてOKです。

ただし郵便番号は
別途記入が必要です。
""",
                    RelationResult
                )


            if relation:

                st.subheader("関係者情報")

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

                show_circle(
                    "関係者情報・雇用形態",
                    relation.employment_type
                )

                show_field(
                    "関係者情報・勤務年数・記入",
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


            # ------------------------------------------------
            # ★ 関係者の勤務年数専用判定
            # ------------------------------------------------

            with st.spinner(
                "① 関係者の勤務年数を確認中..."
            ):

                relation_work_years = safe_analysis(
                    p1_bytes,

                    COMMON
                    + PAGE1_STRUCTURE
                    + """
【今回の対象は1つだけ】

D：関係者情報ブロック内にある
「勤務年数」欄だけを確認してください。

ご契約者本人の勤務年数ではありません。

まず関係者情報ブロックを特定し、
その中にある
印刷された「勤務年数」を
確実に特定してください。

その欄の

「年」の直前にある手書き数字

「ヶ月」の直前にある手書き数字

だけを読み取ってください。


例：

3年8ヶ月

year_has_entry=true
year_value=3

months_has_entry=true
months_value=8


3年0ヶ月

year_has_entry=true
year_value=3

months_has_entry=true
months_value=0


0年8ヶ月

year_has_entry=true
year_value=0

months_has_entry=true
months_value=8


3年　ヶ月

year_has_entry=true
year_value=3

months_has_entry=false
months_value=null


年　8ヶ月

year_has_entry=false
year_value=null

months_has_entry=true
months_value=8


【絶対禁止】

・ご契約者本人の勤務年数
・生年月日
・年収
・給料日
・その他の日付や数字

を使用してはいけません。

対象欄を確実に特定できない場合は
uncertain=true。
""",
                    WorkYearsCheck
                )


            if relation_work_years:

                show_work_years(
                    "関係者情報・勤務年数",
                    relation_work_years
                )


        # ----------------------------------------------------
        # 銀行
        # ----------------------------------------------------

        with st.spinner(
            "① 銀行口座を確認中..."
        ):

            bank = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

E：銀行口座情報。

ゆうちょ銀行側、
または
ゆうちょ銀行以外の銀行側、

どちらか一方に
口座情報の記入が存在すればOKです。

両方を必須にしないでください。

さらに下部の
「口座名義人」のフリガナ欄に
手書き記入があるか確認してください。
""",
                BankResult
            )


        if bank:

            st.subheader("銀行口座")

            if bank.uncertain:

                st.warning(
                    "🔍 銀行口座：要確認"
                )

            elif (
                bank.japan_post_side_has_entry
                or bank.other_bank_side_has_entry
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


        # ----------------------------------------------------
        # 契約情報
        # ----------------------------------------------------

        with st.spinner(
            "① 契約情報を確認中..."
        ):

            contract_info = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【対象】

F：契約関連情報。

次の正確な欄だけを確認：

1.
「役務提供期間」

2.
「特定商取引法第42条第2項
又は第3項書面の受領年月日」

2については
年・月・日が指定欄に
記入されている必要があります。

似た日付を流用しないでください。
""",
                ContractInfoResult
            )


        if contract_info:

            st.subheader("契約情報")

            show_field(
                "役務提供期間",
                contract_info.service_period
            )

            show_field(
                "特定商取引法第42条第2項又は第3項書面の受領年月日",
                contract_info.article42_receipt_date
            )


    # ========================================================
    # PAGE 2
    # ========================================================

    if page2_file:

        st.header(
            "② 役務申込書・指導内容"
        )

        p2_image = Image.open(
            page2_file
        )

        p2_bytes = prepare_image(
            p2_image
        )


        # ----------------------------------------------------
        # 保護者フリガナ
        # ----------------------------------------------------

        with st.spinner(
            "② 保護者情報を確認中..."
        ):

            guardian = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

保護者氏名に対応する
「保護者氏名フリガナ」欄だけ。

その指定欄に
手書き文字が存在するか確認。

読み方が正しいかは審査しません。

他の氏名フリガナを
使用してはいけません。
""",
                GuardianResult
            )


        if guardian:

            st.subheader("保護者情報")

            show_field(
                "保護者氏名フリガナ",
                guardian.guardian_name_furigana
            )


        # ----------------------------------------------------
        # 住所
        # ----------------------------------------------------

        with st.spinner(
            "② ご住所・連絡先を確認中..."
        ):

            p2_address = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

「ご住所・連絡先」の住所欄。

次の両方を確認してください。

1.
住所の手書き文字列に
都道府県名が明示されている。

市区町村から推測禁止。

2.
住所欄付近に印刷された
「都・道・府・県」のうち、
実際の都道府県に対応するものに
手書き○がある。

住所文字列と
○の両方が必要です。
""",
                Page2AddressResult
            )


        if p2_address:

            st.subheader(
                "ご住所・連絡先"
            )

            if p2_address.uncertain:

                st.warning(
                    "🔍 ご住所：要確認"
                )

            elif not p2_address.address_has_entry:

                st.error(
                    "❌ ご住所：未記入"
                )

            else:

                if p2_address.prefecture_name_explicit:

                    st.success(
                        "✅ ご住所：都道府県名あり"
                    )

                else:

                    st.error(
                        "❌ ご住所：都道府県名の記入なし"
                    )


                if (
                    not p2_address.prefecture_mark_field_located
                ):

                    st.warning(
                        "🔍 都・道・府・県の○：要確認"
                    )

                elif (
                    p2_address.correct_prefecture_mark_circled
                ):

                    st.success(
                        "✅ 都・道・府・県：○あり"
                    )

                else:

                    st.error(
                        "❌ 都・道・府・県：適切な○なし"
                    )


        # ----------------------------------------------------
        # 指導対象A
        # ----------------------------------------------------

        with st.spinner(
            "② 指導対象Aを確認中..."
        ):

            target_a = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

右上にある
「指導対象A」の
「有」という印刷選択肢。

「有」に実際に
手書き○がある場合のみ
yes_circled=true。

他の○を流用禁止。
""",
                TargetAResult
            )


        if target_a:

            st.subheader("指導対象A")

            if (
                target_a.uncertain
                or not target_a.field_located
            ):

                st.warning(
                    "🔍 指導対象A「有」：要確認"
                )

            elif target_a.yes_circled:

                st.success(
                    "✅ 指導対象A：「有」に○あり"
                )

            else:

                st.error(
                    "❌ 指導対象A：「有」に○なし"
                )


        # ----------------------------------------------------
        # 公・国・私
        # ----------------------------------------------------

        with st.spinner(
            "② 学校区分を確認中..."
        ):

            school = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

右上の学校情報にある
「公・国・私」の3選択肢だけ。

それぞれに
実際の手書き○があるかを確認。

性別、
指導対象Aの「有」、
学校種別等の別の○を
使用してはいけません。
""",
                SchoolCategoryResult
            )


        if school:

            st.subheader("学校区分")

            school_selected = [
                name
                for name, value in [
                    ("公", school.public_circled),
                    ("国", school.national_circled),
                    ("私", school.private_circled),
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

            elif len(school_selected) == 0:

                st.error(
                    "❌ 公・国・私：選択なし"
                )

            elif len(school_selected) > 1:

                st.error(
                    "⚠️ 公・国・私：複数選択 "
                    + " / ".join(school_selected)
                )

            else:

                st.success(
                    "✅ 公・国・私："
                    + school_selected[0]
                )


        # ----------------------------------------------------
        # コース
        # ----------------------------------------------------

        with st.spinner(
            "② コース名を確認中..."
        ):

            course = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

印刷された「コース名」の
すぐ横にある指定記入欄だけ。

この欄に

週1
かつ
90分

という意味の記入が必要です。

近くにある
「4回/月」だけでは
条件を満たしません。

必ずコース名の
指定欄そのものを確認してください。
""",
                CourseResult
            )


        if course:

            st.subheader("コース名")

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
                course.weekly_once_present
                and course.ninety_minutes_present
            ):

                st.success(
                    "✅ コース名：週1・90分"
                )

            else:

                st.error(
                    "❌ コース名："
                    "「週1・90分」を確認できません"
                )


        # ----------------------------------------------------
        # 日付・期間
        # ----------------------------------------------------

        with st.spinner(
            "② 日付・期間を確認中..."
        ):

            p2_dates = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

次の指定欄だけ。

・初回指導日
・役務提供期間 A

役務提供期間については
A行に記入があればよく、
B行の空欄を
記入漏れとしてはいけません。
""",
                Page2DatesResult
            )


        if p2_dates:

            st.subheader("日付・期間")

            show_field(
                "初回指導日",
                p2_dates.first_instruction_date
            )

            show_field(
                "役務提供期間 A",
                p2_dates.service_period_a
            )


        # ----------------------------------------------------
        # 受領サイン
        # ----------------------------------------------------

        with st.spinner(
            "② 受領サインを確認中..."
        ):

            receipt = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

書類の最上部右側。

「書面交付日」と同じ上部バーにある

「受領サイン →」

という印刷文字を探してください。

その矢印のすぐ右側にある
指定欄だけを確認。

そこに手書き署名が存在する場合だけ
has_signature=true。

書類内にある
保護者氏名、
契約者氏名、
指導対象者氏名、
その他の署名を
絶対に使用しないでください。
""",
                ReceiptResult
            )


        if receipt:

            st.subheader("受領サイン")

            if (
                receipt.uncertain
                or not receipt.field_located
            ):

                st.warning(
                    "🔍 受領サイン：要確認"
                )

            elif receipt.has_signature:

                st.success(
                    "✅ 受領サイン：記入あり"
                )

            else:

                st.error(
                    "❌ 受領サイン：未記入"
                )


        # ----------------------------------------------------
        # 数量
        # ----------------------------------------------------

        with st.spinner(
            "② 数量を確認中..."
        ):

            quantity = safe_analysis(
                p2_bytes,

                COMMON
                + PAGE2_STRUCTURE
                + """
【対象】

教材・数量表だけを確認してください。

まず印刷された
「数量」
という列見出しを発見してください。

各適用行について、

1.
数量列より左側の
同じ行にある手書き整数を
horizontal_values に入れる。

例：
1、1、1
なら
[1,1,1]

2.
同じ行の
「数量」列セルそのものを確認。

そのセルに書かれた数字だけを
written_quantity に入れる。

数量セルが空欄なら、

written_quantity=""

quantity_box_has_handwriting=false

とする。


【絶対禁止】

数量列より右側の

・各単価
・小計
・合計
・金額

を数量として使用禁止。

特に、

36000
108000
648000
712800

などの金額を
数量として読み取ってはいけません。

横の数字から
正しい数量を計算して
written_quantity に補完することも禁止。

written_quantity は
実際の数量セルに
書かれているものだけ。

適用行に手書き選択が見えるのに
行を特定できない場合は
uncertain=true。
""",
                QuantityResult
            )


        if quantity:

            st.subheader("数量")

            if quantity.uncertain:

                st.warning(
                    "🔍 数量：要確認"
                )

            elif not quantity.table_located:

                st.warning(
                    "🔍 数量表：要確認"
                )

            elif not quantity.applicable_rows_detected:

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

                    if (
                        not row.quantity_box_has_handwriting
                        or row.written_quantity.strip() == ""
                    ):

                        st.error(
                            f"❌ {row.row_label}："
                            f"横合計 {expected} / 数量欄 未記入"
                        )

                        continue

                    try:

                        written = int(
                            row.written_quantity
                            .replace(",", "")
                            .strip()
                        )

                    except:

                        st.warning(
                            f"🔍 {row.row_label}："
                            "数量欄を正確に読み取れません"
                        )

                        continue

                    if written >= 1000:

                        st.warning(
                            f"🔍 {row.row_label}："
                            f"数量欄を「{written}」と検出。"
                            "金額列の誤読の可能性があるため要確認"
                        )

                        continue

                    if written == expected:

                        st.success(
                            f"✅ {row.row_label}："
                            f"横合計 {expected} / 数量 {written}"
                        )

                    else:

                        st.error(
                            f"❌ {row.row_label}："
                            f"横合計 {expected} / 数量 {written}"
                        )


    st.divider()

    st.info(
        "AIが「要確認」とした項目や、"
        "提出前の最終確認は人が確認してください。"
    )
