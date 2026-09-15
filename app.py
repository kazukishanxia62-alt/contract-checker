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
# 共通 Schema
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
# PAGE1 勤務先
# ============================================================

class WorkResult(BaseModel):
    company_name: FieldCheck
    company_address: FieldCheck
    company_postal_code: FieldCheck
    company_phone: FieldCheck
    payday: FieldCheck


# ============================================================
# PAGE1 勤務年数
# 数字は読まない
# ============================================================

class WorkYearsPresenceResult(BaseModel):
    field_located: bool

    year_marker_located: bool
    year_entry_has_handwriting: bool

    months_marker_located: bool
    months_entry_has_handwriting: bool

    uncertain: bool


# ============================================================
# PAGE1 業種
# ============================================================

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
# 雇用形態は完全削除
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
# PAGE2 数量
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
# 共通プロンプト
# ============================================================

COMMON = """
あなたは日本の契約書を提出する前に、
記入漏れ・選択漏れを確認する視覚チェック担当です。

このアプリの目的は、
契約書に必要な記入や選択が存在するかを
提出前に確認することです。

記載された情報が事実として正しいかを
審査するものではありません。


【最重要ルール】

別の場所にある文字・数字・○を、
対象欄の記入として流用してはいけません。

必ず、

1. 書類全体を見る
2. 対象となる大きなブロックを探す
3. 印刷された対象ラベルを探す
4. そのラベルに直接対応する記入領域を見る
5. その領域の手書き記入・○だけを見る

という順番で判断してください。


【存在チェック】

氏名
フリガナ
会社名
勤務年数
給料日

などは、

内容そのものの正しさではなく、
指定された欄に手書き記入が存在するかを確認します。


【選択チェック】

性別
住居
業種
公・国・私

などは、

指定された選択肢の位置に
手書き○が存在するかを確認します。


【内容まで確認する項目】

住所の都道府県
月あたりクレジット支払額
週1・90分
数量
公・国・私

だけは指定されたルールまで確認します。


【重要】

対象欄に手書き筆跡が見えるのに、
文字や数字の内容だけ判別できない場合、

未記入にしてはいけません。

その場合は、

uncertain=true

にしてください。


【フリガナ】

フリガナ欄に手書き文字が存在すれば
原則として記入ありです。

氏名との読みの一致確認は不要です。


【会社名】

会社名欄に記入が存在すればOKです。

実在性・正式名称の確認は不要です。


【○】

文字認識だけで判断せず、

印刷された選択肢と
手書き○の位置関係を確認してください。
"""


# ============================================================
# PAGE1 構造
# ============================================================

PAGE1 = """
【1枚目：クレジット申込書】

帳票全体は概ね、

A：ご契約者本人
B：ご契約者勤務先
C：世帯主・世帯状況
D：関係者情報
E：銀行口座
F：契約関連

という構造です。


【重要】

本人情報と関係者情報を
絶対に混同しないでください。

本人勤務先と関係者勤務先も別です。


【B：本人勤務先】

本人情報の下側にあります。

主な項目は、

会社名
所在地
郵便番号
電話番号
勤務年数
給料日
業種

などです。


【雇用形態について】

雇用形態は今回のチェック対象外です。

本人の雇用形態も、
関係者の雇用形態も、

一切判定しないでください。

雇用形態の○を
他の項目の○として利用することも禁止です。


【派遣先・出向先について】

今回のチェック対象外です。


【勤務年数】

勤務年数については、

何年何ヶ月かという
数字の内容を読み取る必要はありません。

必要なのは、

「年」の前の記入欄に手書きが存在するか

および

「ヶ月」の前の記入欄に手書きが存在するか

だけです。

0ヶ月も完全に有効な記入です。


【世帯状況】

「世帯主の年収(税込)」

と

「世帯主のクレジットの
月あたりのお支払額」

は別の欄です。

絶対に混同しないでください。


【関係者情報】

関係者情報はDブロック内だけで判断。

本人情報から記入を流用禁止。


【銀行】

ゆうちょ銀行側と
ゆうちょ銀行以外の銀行側があります。

どちらか一方に必要事項が記入されていれば
銀行情報は記入ありです。
"""


# ============================================================
# PAGE2 構造
# ============================================================

PAGE2 = """
【2枚目：役務申込書・指導内容】

帳票全体は概ね、

左上：
契約者・保護者

右上：
指導対象A/B/C・学校

中央～下：
コース・指導内容・期間

中央～右下：
教材・数量・各単価・小計

最上部右側：
書面交付日・受領サイン

という構造です。


【受領サイン】

最上部右側にある

「受領サイン →」

の矢印直後の指定欄だけを確認してください。

別の氏名・署名を使用禁止。


【数量】

数量表は、

横方向の選択欄
→ 数量
→ 各単価
→ 小計

という構造です。

各単価、小計、合計などの金額を
数量として使用してはいけません。
"""


# ============================================================
# 画像
# ============================================================

def prepare_image(image):

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    buf = io.BytesIO()

    image.save(
        buf,
        format="JPEG",
        quality=98,
        subsampling=0
    )

    return buf.getvalue()


# ============================================================
# Gemini
# ============================================================

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
# 表示
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


st.subheader(
    "① クレジット申込書"
)

page1_file = st.file_uploader(
    "1枚目を選択",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],
    key="page1"
)


st.subheader(
    "② 役務申込書・指導内容"
)

page2_file = st.file_uploader(
    "2枚目を選択",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],
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
            "写真を選択してください。"
        )

        st.stop()


    # ========================================================
    # PAGE1
    # ========================================================

    if page1_file:

        p1 = prepare_image(
            Image.open(page1_file)
        )

        st.header(
            "① クレジット申込書"
        )


        # ====================================================
        # 本人
        # ====================================================

        with st.spinner(
            "ご契約者情報を確認中..."
        ):

            applicant = safe_ask(

                p1,

                COMMON + PAGE1 + """
A：ご契約者本人情報だけを確認してください。

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


【住所フリガナ】

本人住所に直接対応する
住所フリガナ欄だけを確認。

氏名フリガナや
関係者フリガナを使用禁止。


【電話番号】

固定電話と携帯電話は
両方必須ではありません。

少なくともどちらか一方に
記入があればOKです。
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
今回確認するのは、

A：ご契約者本人の
「ご住所」

だけです。


住所に実際に書かれた文字列が、
都道府県名から始まっているか確認。


例：

大阪府大阪市...
→ prefecture_explicit=true

兵庫県神戸市...
→ prefecture_explicit=true

大阪市...
→ prefecture_explicit=false

神戸市...
→ prefecture_explicit=false


市区町村名から
都道府県を推測してはいけません。


フォームに元から印刷されている

都・道・府・県

という文字だけでは
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
        # 勤務先
        # 雇用形態・派遣先は対象外
        # ====================================================

        st.subheader(
            "勤務先"
        )

        with st.spinner(
            "勤務先情報を確認中..."
        ):

            work = safe_ask(

                p1,

                COMMON + PAGE1 + """
B：ご契約者本人の勤務先ブロックだけを確認。

確認対象：

会社名
所在地
所在地の郵便番号
所在地の電話番号
給料日


【今回確認しないもの】

雇用形態
派遣先・出向先

この2項目は完全に無視してください。


勤務年数も別判定なので
この判定には含めないでください。


関係者勤務先から
記入を流用禁止。
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


        # ====================================================
        # 勤務年数
        #
        # ★ 数字を読まない
        # ★ 0ヶ月でも記入あり
        # ====================================================

        with st.spinner(
            "勤務年数を確認中..."
        ):

            work_years = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認するのは、

B：ご契約者本人勤務先ブロック内の

「勤務年数」

だけです。


━━━━━━━━━━━━━━━━━━━━━━
【この判定の目的】
━━━━━━━━━━━━━━━━━━━━━━

何年何ヶ月なのかを
読み取る必要はありません。

数字の内容は判定しません。


確認するのは、

① 「年」の前の記入欄に
   手書きの筆跡が存在するか

② 「ヶ月」の前の記入欄に
   手書きの筆跡が存在するか

この2点だけです。


━━━━━━━━━━━━━━━━━━━━━━
【探す順序】
━━━━━━━━━━━━━━━━━━━━━━

数字を先に探してはいけません。

必ず、

1.
B：ご契約者本人勤務先ブロックを確認

2.
印刷された
「勤務年数」
というラベルを確認

3.
その勤務年数欄の中にある
印刷された「年」を確認

4.
「年」の直前の記入スペースを見る

5.
印刷された「ヶ月」を確認

6.
「ヶ月」の直前の記入スペースを見る

という順番で確認してください。


━━━━━━━━━━━━━━━━━━━━━━
【年】
━━━━━━━━━━━━━━━━━━━━━━

印刷された「年」の
直前の記入スペースに、

手書きの数字・筆跡が
少しでも明確に存在するなら、

year_entry_has_handwriting=true

です。

その数字が、

1
19
20

など何なのかは
読み取る必要がありません。


━━━━━━━━━━━━━━━━━━━━━━
【ヶ月】
━━━━━━━━━━━━━━━━━━━━━━

印刷された「ヶ月」の
直前の記入スペースに、

手書きの数字・筆跡が
少しでも明確に存在するなら、

months_entry_has_handwriting=true

です。


━━━━━━━━━━━━━━━━━━━━━━
【0ヶ月は記入あり】
━━━━━━━━━━━━━━━━━━━━━━

特に重要です。

「0」は完全に有効な記入です。

0ヶ月の場合、

0が丸・楕円・小さな輪のように
見える場合があります。


しかし、

印刷された「ヶ月」の直前の
数字記入スペースに存在する
手書きの0は、

必ず

months_entry_has_handwriting=true

として扱ってください。


「0だから空欄」

「丸だから記入なし」

という判断は禁止です。


━━━━━━━━━━━━━━━━━━━━━━
【内容は読まない】
━━━━━━━━━━━━━━━━━━━━━━

例えば、

19年0ヶ月

でも、

2年6ヶ月

でも、

10年3ヶ月

でも、

今回返す結果は同じです。


年の前に記入あり
+
ヶ月の前に記入あり

なら、

両方trueです。


━━━━━━━━━━━━━━━━━━━━━━
【絶対に使ってはいけない数字】
━━━━━━━━━━━━━━━━━━━━━━

生年月日
年齢
西暦
年収
給料日
電話番号
郵便番号
契約日
世帯主情報
関係者情報

など、

勤務年数欄以外にある数字は
絶対に使用禁止です。


━━━━━━━━━━━━━━━━━━━━━━
【判断できない場合】
━━━━━━━━━━━━━━━━━━━━━━

勤務年数欄は特定できた。

しかし、

「ヶ月」の直前に
0らしい筆跡があるものの、
画像上どうしても確信できない。

この場合は、

months_entry_has_handwriting=false

にしてはいけません。

uncertain=true

にしてください。


本当に何も書かれていないことを
確認できた場合だけ、

months_entry_has_handwriting=false
uncertain=false

です。
""",

                WorkYearsPresenceResult
            )


        if work_years:

            if (
                work_years.uncertain
                or not work_years.field_located
            ):

                st.warning(
                    "🔍 勤務年数：要確認"
                )


            elif (
                not work_years.year_marker_located
                or not work_years.months_marker_located
            ):

                st.warning(
                    "🔍 勤務年数：欄を正確に特定できません"
                )


            elif (
                work_years.year_entry_has_handwriting
                and work_years.months_entry_has_handwriting
            ):

                st.success(
                    "✅ 勤務年数：記入あり"
                )


            elif (
                not work_years.year_entry_has_handwriting
                and not work_years.months_entry_has_handwriting
            ):

                st.error(
                    "❌ 勤務年数：年・ヶ月が未記入"
                )


            elif not work_years.year_entry_has_handwriting:

                st.error(
                    "❌ 勤務年数：年が未記入"
                )


            else:

                st.error(
                    "❌ 勤務年数：ヶ月が未記入"
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
「業種」だけを確認。

まず印刷された
「業種」
という項目を特定してください。

その業種に対応する
選択肢領域内に、

手書き○が存在する場合だけ

circle_visible=true

です。


本人の雇用形態の○は
チェック対象外であり、

業種の○として使用してはいけません。

住居
性別
世帯状況
関係者情報

などの○も使用禁止。
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

        st.subheader(
            "世帯状況"
        )

        with st.spinner(
            "世帯状況を確認中..."
        ):

            household = safe_ask(

                p1,

                COMMON + PAGE1 + """
C：世帯主・世帯状況ブロックだけを確認。

必要な記入項目と
必要な選択項目が
記入・選択されているか確認。


ただし、

世帯主確認欄の右側にある
「連絡先」

は空欄でも問題ありません。


月あたりクレジット支払額は
別判定するため、
ここでは金額判定しません。
""",

                HouseholdBasicResult
            )


        if household:

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
        # 月あたりクレジット
        # ====================================================

        with st.spinner(
            "月あたりクレジット支払額を確認中..."
        ):

            monthly_credit = safe_ask(

                p1,

                COMMON + PAGE1 + """
今回確認するのは、

C：世帯状況ブロックの

「世帯主のクレジットの
月あたりのお支払額」

という指定欄だけです。


最初にこの印刷ラベルを
確実に特定してください。

そのラベルに直接対応する
記入欄だけを読みます。


━━━━━━━━━━━━━━━━━━━━━━

近くにある

「世帯主の年収(税込)」

は完全に別項目です。


例えば、

年収欄に

400万円

と記入されていても、

月あたり支払額を

400万円
400000円

などと判断してはいけません。


━━━━━━━━━━━━━━━━━━━━━━

月あたり支払額の指定欄に
手書き記入があれば、

handwriting_visible=true


金額が明確に読める場合だけ、

amount_readable=true

amount_yenに
円単位整数を入れてください。


例：

0円
→ 0

8万円
→ 80000

10万円
→ 100000

12万円
→ 120000


記入はあるが
数字だけ不鮮明な場合、

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
        # 関係者情報
        # ====================================================

        if relation_enabled:

            st.subheader(
                "関係者情報"
            )

            with st.spinner(
                "関係者情報を確認中..."
            ):

                relation = safe_ask(

                    p1,

                    COMMON + PAGE1 + """
D：関係者情報ブロックだけを確認してください。


【重要】

本人情報を
関係者情報として使用禁止。

本人勤務先を
関係者勤務先として使用禁止。


確認対象：

関係者情報・氏名
関係者情報・氏名フリガナ
関係者情報・性別
関係者情報・生年月日
関係者情報・ご契約者との関係
関係者情報・ご住所
関係者情報・ご住所の郵便番号
関係者情報・ご住居
関係者情報・連絡先
関係者情報・税込年収
関係者情報・勤務年数
関係者情報・給料日
関係者情報・会社名
関係者情報・所在地
関係者情報・所在地の郵便番号
関係者情報・所在地の電話番号


【今回チェックしない項目】

関係者情報・雇用形態

雇用形態は完全に対象外です。


【住所】

関係者の住所は、

実際の住所

または

「同上」

のどちらでも
記入ありと判断します。


ただし、

住所の郵便番号は
別途記入が必要です。


【勤務年数】

関係者情報の勤務年数については、

具体的な年数の正しさは確認不要。

指定された勤務年数欄に
手書き記入が存在するかだけ確認。
""",

                    RelationBasicResult
                )


            if relation:

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

                # 雇用形態は表示しない

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

        st.subheader(
            "銀行口座"
        )

        with st.spinner(
            "銀行口座を確認中..."
        ):

            bank = safe_ask(

                p1,

                COMMON + PAGE1 + """
E：銀行口座ブロックだけを確認。

銀行口座には、

ゆうちょ銀行側

と

ゆうちょ銀行以外の銀行側

があります。


両方を記入する必要はありません。

どちらか一方に
必要な口座情報が記入されていればOK。


さらに、

下部にある
「口座名義人」

に対応する
フリガナ欄を確認してください。


別の氏名フリガナを
口座名義人フリガナとして
使用禁止。
""",

                BankResult
            )


        if bank:

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

        st.subheader(
            "契約情報"
        )

        with st.spinner(
            "契約情報を確認中..."
        ):

            contract = safe_ask(

                p1,

                COMMON + PAGE1 + """
F：契約関連項目。

正確に次の2項目だけ確認。


1.
役務提供期間


2.
特定商取引法第42条第2項
又は第3項書面の受領年月日


【受領年月日】

この名称の指定欄にある

年
月
日

が記入されているか確認。


近くにある別の日付、

契約日
申込日
生年月日

などを使用禁止。
""",

                ContractResult
            )


        if contract:

            show_field(
                "役務提供期間",
                contract.service_period
            )

            show_field(
                "特定商取引法第42条第2項又は第3項書面の受領年月日",
                contract.article42_receipt_date
            )


    # ========================================================
    # PAGE2
    # ========================================================

    if page2_file:

        p2 = prepare_image(
            Image.open(page2_file)
        )

        st.header(
            "② 役務申込書・指導内容"
        )


        # ====================================================
        # 保護者氏名フリガナ
        # ====================================================

        st.subheader(
            "保護者情報"
        )

        with st.spinner(
            "保護者情報を確認中..."
        ):

            guardian = safe_ask(

                p2,

                COMMON + PAGE2 + """
「保護者氏名」

に直接対応する
フリガナ欄だけを確認してください。


そのフリガナ欄に
手書き文字が存在すればOK。


別の氏名フリガナを
流用禁止。
""",

                GuardianResult
            )


        if guardian:

            show_field(
                "保護者氏名フリガナ",
                guardian.guardian_name_furigana
            )


        # ====================================================
        # PAGE2 住所
        # ====================================================

        with st.spinner(
            "ご住所・連絡先を確認中..."
        ):

            p2_address = safe_ask(

                p2,

                COMMON + PAGE2 + """
「ご住所・連絡先」

の住所欄だけを確認。


必要条件は2つ。


①

実際に書かれた住所文字列に
都道府県名が明示されている。


市区町村から
都道府県を推測禁止。


②

印刷された

都
道
府
県

のうち、

住所に対応するものに
手書き○が存在する。


この2条件を
別々に確認してください。
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
右上にある

「指導対象A」

を特定してください。


そのAに直接対応する

「有」

という選択肢に、

実際の手書き○が存在するかだけ確認。


性別
学校区分
その他の○

を流用禁止。
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

という3つの選択肢だけを確認。


それぞれに
手書き○があるか判断。


指導対象A
性別
その他の選択欄

の○を流用禁止。
""",

                SchoolResult
            )


        if school:

            selected_school = [

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


            elif len(selected_school) == 0:

                st.error(
                    "❌ 公・国・私：選択なし"
                )


            elif len(selected_school) > 1:

                st.error(
                    "❌ 公・国・私：複数選択 "
                    + " / ".join(selected_school)
                )


            else:

                st.success(
                    "✅ 公・国・私："
                    + selected_school[0]
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

というラベルを特定してください。


そのラベルのすぐ横にある
指定記入欄だけを確認。


この指定欄に、

週1

かつ

90分

という内容の記入が必要です。


近くにある

4回/月

という記載だけを見て、

週1・90分が記入されていると
判断してはいけません。
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
                    "❌ コース名：週1・90分を確認できません"
                )


        # ====================================================
        # 初回指導日 / 役務提供期間
        # ====================================================

        with st.spinner(
            "初回指導日・役務提供期間を確認中..."
        ):

            dates = safe_ask(

                p2,

                COMMON + PAGE2 + """
確認するのは、

初回指導日

と

役務提供期間A

だけです。


役務提供期間については、

A行に記入があればOK。


B行が空欄でも
問題ありません。
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
今回確認するのは、

受領サイン

だけです。


書類の最上部右側を確認。


「書面交付日」

と同じ上部の帯にある、

「受領サイン →」

という印刷文字を探してください。


その矢印の直後にある
指定された署名領域だけを確認。


そこに手書き署名が存在すれば、

signature_visible=true


保護者氏名
契約者氏名
生徒氏名
その他の手書き氏名

を受領サインとして
使用してはいけません。
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

        st.subheader(
            "数量"
        )

        with st.spinner(
            "数量を確認中..."
        ):

            quantity = safe_ask(

                p2,

                COMMON + PAGE2 + """
教材・数量表だけを確認。


━━━━━━━━━━━━━━━━━━━━━━
【最初に数量列を探す】
━━━━━━━━━━━━━━━━━━━━━━

最初に、

印刷された列見出し

「数量」

を必ず特定してください。


数量の数字を先に探してはいけません。


━━━━━━━━━━━━━━━━━━━━━━
【横方向】
━━━━━━━━━━━━━━━━━━━━━━

対象となる各行について、

数量列より左側にある、

同じ行の横方向の
手書き数量要素を読み取ります。


例えば、

1
1
1

と3つ記入されている場合、

horizontal_values

は

[1, 1, 1]

です。


━━━━━━━━━━━━━━━━━━━━━━
【数量セル】
━━━━━━━━━━━━━━━━━━━━━━

次に、

その同じ行の
「数量」列セルそのものを確認。


数量セルに
手書き数字が存在するなら、

quantity_handwriting_visible=true


明確に読める場合だけ、

written_quantity

に数字を入れてください。


━━━━━━━━━━━━━━━━━━━━━━
【空欄】
━━━━━━━━━━━━━━━━━━━━━━

数量セルが本当に空欄なら、

quantity_handwriting_visible=false
written_quantity=null


横方向の数字を足して、

その答えを
written_quantityに補完してはいけません。


━━━━━━━━━━━━━━━━━━━━━━
【絶対禁止】
━━━━━━━━━━━━━━━━━━━━━━

数量列より右側の

各単価
小計
合計
金額

は数量ではありません。


例えば、

36000
108000
648000
712800

などの金額を

written_quantity

として使用禁止。


━━━━━━━━━━━━━━━━━━━━━━
【不鮮明】
━━━━━━━━━━━━━━━━━━━━━━

数量セルに
手書き筆跡が存在する。

しかし数字だけ読めない場合、

quantity_handwriting_visible=true
written_quantity=null
uncertain=true

にしてください。
""",

                QuantityResult
            )


        if quantity:

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


                    # 金額誤読防止
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
