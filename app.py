import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
import re
from openai import OpenAI


# =========================================================
# 基本設定
# =========================================================

st.set_page_config(
    page_title="契約書AIチェック",
    page_icon="✅",
    layout="centered"
)

st.title("契約書 AI記入漏れチェック")

st.caption(
    "全体写真でも、分割したアップ写真でも使えます。"
    "写真ごとに書類の場所を特定してから、その場所専用の判定を行います。"
)

st.warning(
    "提出前の補助チェック用です。最終確認は必ず人が行ってください。"
)


try:
    client = OpenAI(
        api_key=st.secrets["OPENAI_API_KEY"]
    )
except Exception:
    st.error("OPENAI_API_KEY が設定されていません。")
    st.stop()


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


PAGE1_GROUPS = [
    "applicant",
    "employment",
    "household",
    "relation_top",
    "relation_bottom",
    "bank",
    "contract_bottom"
]


PAGE2_GROUPS = [
    "guardian_address",
    "target_school",
    "course_dates",
    "quantity",
    "receipt"
]


# =========================================================
# 画像
# =========================================================

def pil_to_data_url(img, quality=95):

    buf = BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=quality
    )

    encoded = base64.b64encode(
        buf.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


def prepare_basic_image(uploaded):

    img = Image.open(uploaded)

    img = ImageOps.exif_transpose(
        img
    ).convert("RGB")

    max_side = 3200

    if max(img.size) > max_side:

        scale = max_side / max(img.size)

        img = img.resize(
            (
                int(img.width * scale),
                int(img.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

    return img


# =========================================================
# 向き判定
# =========================================================

def orientation_schema():

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "orientation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "rotation": {
                        "type": "integer",
                        "enum": [0, 90, 180, 270]
                    }
                },
                "required": ["rotation"],
                "additionalProperties": False
            }
        }
    }


def detect_orientation(img):

    preview = img.copy()

    if max(preview.size) > 1000:

        scale = 1000 / max(preview.size)

        preview = preview.resize(
            (
                int(preview.width * scale),
                int(preview.height * scale)
            ),
            Image.Resampling.LANCZOS
        )


    versions = {
        0: preview,
        90: preview.rotate(90, expand=True),
        180: preview.rotate(180, expand=True),
        270: preview.rotate(270, expand=True)
    }


    content = [
        {
            "type": "text",
            "text": """
同じ日本語の契約書、または契約書の一部分を、
0度・90度・180度・270度に回転した画像です。

日本語の印刷文字が普通に読める向きを1つ選んでください。

契約書全体ではなく、
一部分だけが写っている場合もあります。

記入内容は判定しません。

rotation は必ず
0 / 90 / 180 / 270
のどれかです。
"""
        }
    ]


    for angle, version in versions.items():

        content.append({
            "type": "text",
            "text": f"【{angle}度版】"
        })

        content.append({
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(
                    version,
                    quality=80
                ),
                "detail": "low"
            }
        })


    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        response_format=orientation_schema()
    )


    return json.loads(
        response.choices[0].message.content
    )["rotation"]


def prepare_image(uploaded):

    img = prepare_basic_image(
        uploaded
    )

    rotation = detect_orientation(
        img
    )

    if rotation != 0:

        img = img.rotate(
            rotation,
            expand=True
        )

    return img, rotation


# =========================================================
# 画像がどの部分か判定
# =========================================================

def region_schema(page):

    allowed = (
        PAGE1_GROUPS + ["full_document", "unknown"]
        if page == 1
        else
        PAGE2_GROUPS + ["full_document", "unknown"]
    )

    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"page{page}_region",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "regions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": allowed
                        }
                    },
                    "reason": {
                        "type": "string"
                    }
                },
                "required": [
                    "regions",
                    "reason"
                ],
                "additionalProperties": False
            }
        }
    }


def classify_page1_image(img):

    prompt = """
これは「① クレジット申込書」の写真です。

書類全体の場合もあれば、
書類の一部分だけを近くから撮った写真の場合もあります。

写真の位置ではなく、
必ず印刷された見出し・項目名を見て判断してください。

該当する領域をすべて返してください。

applicant
= ご契約者氏名、ご住所、フリガナなど契約者本人情報

employment
= 勤務先、会社名、雇用形態、派遣先・出向先など

household
= 世帯主、世帯状況、世帯主年収、
  世帯主のクレジットの月あたりのお支払額など

relation_top
= 関係者情報の上側。
  氏名、フリガナ、性別、生年月日、
  ご契約者との関係、ご住所、ご住居、
  電話番号、携帯電話、税込年収など

relation_bottom
= 関係者情報の勤務先側。
  雇用形態、勤務年数、給料日、
  会社名、所在地、所在地郵便番号、
  所在地電話番号など

bank
= ゆうちょ銀行、ゆうちょ銀行以外、
  口座名義人フリガナなど銀行口座部分

contract_bottom
= 役務提供期間、
  特定商取引法第42条第2項又は第3項書面の受領年月日、
  ヶ月など契約下部の項目

full_document
= 書類全体が十分に写っている

unknown
= 見出しが少なすぎて判断できない


重要：

1枚の写真に複数領域が写っていれば、
複数返して構いません。

例えば関係者情報の上から下まで写っていれば

["relation_top", "relation_bottom"]

としてください。

full_document の場合は、
full_document だけ返してください。
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
                            "url": pil_to_data_url(img),
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        response_format=region_schema(1)
    )

    return json.loads(
        response.choices[0].message.content
    )


def classify_page2_image(img):

    prompt = """
これは「② 役務申込書・指導内容」の写真です。

書類全体の場合もあれば、
一部分だけを近くから撮った写真の場合もあります。

写真の位置ではなく、
印刷された見出しから判断してください。

guardian_address
= 保護者氏名、氏名フリガナ、
  ご住所・連絡先、都・道・府・県など

target_school
= 指導対象Aの「有」、
  公・国・私など学校情報

course_dates
= コース名、初回指導日、
  役務提供期間Aなど

quantity
= 商品表、数量、各単価、小計などがある部分

receipt
= 右上の書面交付日、
  「受領サイン →」の部分

full_document
= 書類全体が十分写っている

unknown
= 判定できない


1枚の写真に複数領域が写っていれば
複数返してください。

full_document の場合は
full_document のみ返してください。
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
                            "url": pil_to_data_url(img),
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        response_format=region_schema(2)
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 汎用フィールドSchema
# =========================================================

def field_object_schema():

    return {
        "type": "object",
        "properties": {
            "visible": {
                "type": "boolean"
            },
            "has_entry": {
                "type": "boolean"
            },
            "selected": {
                "type": "boolean"
            },
            "text": {
                "type": "string"
            },
            "uncertain": {
                "type": "boolean"
            }
        },
        "required": [
            "visible",
            "has_entry",
            "selected",
            "text",
            "uncertain"
        ],
        "additionalProperties": False
    }


def fields_schema(name, keys):

    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    key: field_object_schema()
                    for key in keys
                },
                "required": keys,
                "additionalProperties": False
            }
        }
    }


def blank_field():

    return {
        "visible": False,
        "has_entry": False,
        "selected": False,
        "text": "",
        "uncertain": False
    }


# =========================================================
# 専用領域の読取
# =========================================================

def read_field_group(images, prompt, keys, schema_name):

    if not images:

        return {
            key: blank_field()
            for key in keys
        }


    content = [
        {
            "type": "text",
            "text": prompt
        }
    ]


    for i, img in enumerate(
        images,
        start=1
    ):

        content.append({
            "type": "text",
            "text": f"【この領域の参考画像{i}】"
        })

        content.append({
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(img),
                "detail": "high"
            }
        })


    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        response_format=fields_schema(
            schema_name,
            keys
        )
    )


    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 1枚目：契約者
# =========================================================

def read_page1_applicant(images):

    keys = [
        "applicant_name",
        "applicant_name_furigana",
        "applicant_address",
        "applicant_prefecture",
        "applicant_address_furigana"
    ]

    prompt = """
①クレジット申込書の
「ご契約者本人情報」だけを確認してください。

他の欄は一切判定しません。

同じ部分を複数枚撮影している場合があります。
より近く、より鮮明に写っている画像を優先してください。

共通ルール：

visible:
その指定欄自体を画像上で確認できるか。

has_entry:
指定欄そのものに手書き・入力があるか。

selected:
このグループでは使用しないので false。

uncertain:
指定欄は見えるが、手書きかどうか等を
本当に判定できない場合だけ true。

「写っていない」と「判定不能」を混同しない。


applicant_name
= ご契約者の氏名欄。

applicant_name_furigana
= 氏名に対応するフリガナ欄。

applicant_address
= ご契約者本人のご住所欄。

applicant_prefecture
= 上記住所に実際に書かれている都道府県名。

兵庫県神戸市～
なら text="兵庫県"

神戸市～
だけなら text=""

市区町村から県名を推測しない。

applicant_address_furigana
= ご契約者住所に対応する住所用フリガナ欄。

氏名フリガナを代用禁止。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_applicant"
    )


# =========================================================
# 1枚目：雇用形態
# =========================================================

def read_page1_employment(images):

    keys = [
        "employment_regular",
        "employment_dispatch",
        "employment_contract",
        "employment_parttime",
        "employment_other",
        "dispatch_company"
    ]

    prompt = """
①クレジット申込書の
勤務先・雇用形態部分だけを確認してください。

employment_regular
= 正社員

employment_dispatch
= 派遣社員

employment_contract
= 契約社員

employment_parttime
= パート・アルバイト

employment_other
= その他


これら5項目は、

対象となる印刷文字に
実際の手書き○・囲み・選択印がある場合だけ

selected=true

にしてください。

印刷された丸、
枠線、
文字の形、

だけで selected=true にしないでください。

選択肢そのものが見えていれば visible=true。


dispatch_company
= 「派遣先・出向先」の会社名欄そのもの。

他の会社名や勤務先会社名を
派遣先として流用しない。

明確に空欄なら

visible=true
has_entry=false
uncertain=false

です。

見えるのに何でも uncertain に逃げないでください。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_employment"
    )


# =========================================================
# 1枚目：世帯状況
# =========================================================

def read_page1_household(images):

    keys = [
        "household_credit_monthly"
    ]

    prompt = """
①クレジット申込書の世帯状況部分です。

確認するのは1項目だけです。

household_credit_monthly

必ず、

「世帯主のクレジットの月あたりのお支払額」

と印刷された欄そのものを探してください。

近くにある

・世帯主の年収(税込)
・税込年収
・400万円
・その他の金額

を絶対に流用しないでください。


対象欄が見えていて空欄なら

visible=true
has_entry=false
text=""
uncertain=false


数字が記入されていて読めるなら

has_entry=true

text に、その欄の金額だけ入れてください。


欄が見えていて、
本当に数字が潰れて読めない場合だけ

uncertain=true。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_household"
    )


# =========================================================
# 1枚目：関係者上側
# =========================================================

def read_page1_relation_top(images):

    keys = [
        "relation_name",
        "relation_name_furigana",
        "relation_sex",
        "relation_birthdate",
        "relation_relationship",
        "relation_address",
        "relation_address_same",
        "relation_address_postal",
        "relation_residence",
        "relation_home_phone",
        "relation_mobile",
        "relation_income"
    ]

    prompt = """
①クレジット申込書の
「関係者情報」の上側だけを確認してください。

他の欄は使わないでください。

relation_name
= 関係者本人の氏名。

relation_name_furigana
= その氏名に対応するフリガナ。

relation_sex
= 性別の必要な選択。
○がある場合 selected=true。

relation_birthdate
= 生年月日。

relation_relationship
= ご契約者との関係。
必要な○・選択・記入があれば selected=true。

relation_address
= 関係者本人の「ご住所」。

relation_address_same
= 関係者本人住所欄に
「同上」と明確に書かれている場合のみ
has_entry=true。

relation_address_postal
= 関係者本人住所側の郵便番号。

勤務先所在地側の郵便番号を
流用しない。

relation_residence
= 「ご住居」の選択。
必要な○があれば selected=true。

relation_home_phone
= 関係者本人の固定電話番号。

relation_mobile
= 関係者本人の携帯電話番号。

relation_income
= 関係者本人の税込年収。


重要：

印刷文字だけでは記入ありにしない。

欄が明確に見えていて空欄なら
uncertainではなく

visible=true
has_entry=false

としてください。

○が明確にない場合も
uncertainではなく selected=false。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_relation_top"
    )


# =========================================================
# 1枚目：関係者勤務先側
# =========================================================

def read_page1_relation_bottom(images):

    keys = [
        "relation_employment",
        "relation_years_service",
        "relation_payday",
        "relation_employer_name",
        "relation_location",
        "relation_location_same",
        "relation_location_postal",
        "relation_location_phone"
    ]

    prompt = """
①クレジット申込書の
「関係者情報」の勤務先側だけを確認してください。

relation_employment
= 関係者情報内の雇用形態。
必要な選択に○がある場合 selected=true。

relation_years_service
= 勤務年数。

relation_payday
= 給料日。

relation_employer_name
= 会社名。

relation_location
= 勤務先等の所在地。

実住所が書かれているなら
has_entry=true。

relation_location_same
= 所在地欄に「同上」と書かれている場合だけ
has_entry=true。

relation_location_postal
= 所在地に付属する郵便番号。

relation_location_phone
= 所在地・勤務先側の電話番号。


本人の携帯電話番号を
所在地電話番号として使わない。

欄が見えているのに空欄なら、
要確認ではなく空欄として返してください。

○がない場合も、
見えているなら selected=false にしてください。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_relation_bottom"
    )


# =========================================================
# 1枚目：銀行口座
# =========================================================

def read_page1_bank(images):

    keys = [
        "bank_yucho",
        "bank_other",
        "bank_account_furigana"
    ]

    prompt = """
①クレジット申込書の銀行口座部分だけを確認してください。

bank_yucho
= ゆうちょ銀行側に口座情報の記入があるか。

bank_other
= ゆうちょ銀行以外の銀行側に口座情報の記入があるか。

どちらか片側のみ記入でも問題ありません。

bank_account_furigana
= 口座名義人に対応するフリガナ欄。

氏名の別フリガナを使わない。

対象欄が見えていて空欄なら、
uncertainではなく has_entry=false。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_bank"
    )


# =========================================================
# 1枚目：契約下部
# =========================================================

def read_page1_contract_bottom(images):

    keys = [
        "page1_service_period",
        "legal_receipt_date",
        "payment_months"
    ]

    prompt = """
①クレジット申込書の契約下部だけ確認してください。

page1_service_period
= 「役務提供期間」欄そのもの。

legal_receipt_date
= 正確に

「特定商取引法第42条第2項又は第3項書面の受領年月日」

と書かれた欄そのもの。

近くの別の日付を代用禁止。

年・月・日の記入をこの指定欄で確認してください。


payment_months
= 指定された「ヶ月」の欄そのもの。

別の数字を流用しない。


欄が見えていて空欄なら
has_entry=false。

本当に画像が不鮮明な場合だけ uncertain=true。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page1_contract_bottom"
    )


# =========================================================
# 2枚目：保護者・住所
# =========================================================

def read_page2_guardian(images):

    keys = [
        "guardian_name",
        "guardian_furigana",
        "page2_address",
        "page2_prefecture",
        "prefecture_to",
        "prefecture_do",
        "prefecture_fu",
        "prefecture_ken"
    ]

    prompt = """
②役務申込書・指導内容の
保護者氏名・ご住所部分だけ確認してください。

guardian_name
= 保護者氏名。

guardian_furigana
= 保護者氏名に対応するフリガナ。

page2_address
= ご住所・連絡先の住所欄。

page2_prefecture
= 住所内に実際に書かれている都道府県名。

大阪府大阪市～
なら text="大阪府"

大阪市～
なら text=""

推測禁止。


prefecture_to
= 「都」に○があるか。

prefecture_do
= 「道」に○があるか。

prefecture_fu
= 「府」に○があるか。

prefecture_ken
= 「県」に○があるか。


対象文字そのものに手書き○がある場合だけ
selected=true。

印刷文字・枠線は○ではありません。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page2_guardian"
    )


# =========================================================
# 2枚目：指導対象、公国私
# =========================================================

def read_page2_target_school(images):

    keys = [
        "target_a_yes",
        "school_public",
        "school_national",
        "school_private"
    ]

    prompt = """
②役務申込書・指導内容の
指導対象A・公国私部分だけ確認してください。

target_a_yes
= 指導対象Aにある「有」の文字そのもの。

「有」に手書き○がある場合だけ selected=true。


school_public
= 「公」

school_national
= 「国」

school_private
= 「私」


公・国・私の各文字そのものについて
○があるかを別々に判定してください。

性別、
指導対象Aの有、
学校種別など、

別の○を流用しない。

見えていて○が明確にないなら
uncertainではなく selected=false。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page2_target_school"
    )


# =========================================================
# 2枚目：コース・日付
# =========================================================

def read_page2_course_dates(images):

    keys = [
        "course_name",
        "initial_instruction_date",
        "service_period_a"
    ]

    prompt = """
②役務申込書・指導内容の
コース名・初回指導日・役務提供期間だけ確認してください。

course_name
= 「コース名」の指定欄そのもの。

ここに書かれている文字を text に入れてください。

必要なのは「週1 90分」です。

近くの
「4回/月」
などはコース名として使わない。


initial_instruction_date
= 「初回指導日」欄そのもの。


service_period_a
= 「役務提供期間」のA行だけ。

B行は確認不要。


欄が見えていて空欄なら
has_entry=false。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page2_course_dates"
    )


# =========================================================
# 2枚目：受領サイン
# =========================================================

def read_page2_receipt(images):

    keys = [
        "receipt_signature"
    ]

    prompt = """
②役務申込書・指導内容の
受領サインだけを確認してください。

写真内でまず

「書面交付日」

を探してください。

その右側付近にある

「受領サイン →」

という印刷文字を探してください。

確認するのは、

「受領サイン →」の矢印の直後にある
横長の指定欄だけです。

その指定欄の中に手書きがある場合だけ

receipt_signature.has_entry=true。


以下は絶対に受領サインとして使わない：

・保護者氏名
・指導対象氏名
・担当者氏名
・他の欄の氏名


受領サイン欄がはっきり見えていて空欄なら

visible=true
has_entry=false
uncertain=false

にしてください。
"""

    return read_field_group(
        images,
        prompt,
        keys,
        "page2_receipt"
    )


# =========================================================
# 数量専用
# =========================================================

def quantity_schema():

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "page2_quantity",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "row_label": {
                                    "type": "string"
                                },
                                "horizontal_values": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    }
                                },
                                "quantity_visible": {
                                    "type": "boolean"
                                },
                                "quantity_has_entry": {
                                    "type": "boolean"
                                },
                                "written_quantity": {
                                    "type": "string"
                                },
                                "uncertain": {
                                    "type": "boolean"
                                }
                            },
                            "required": [
                                "row_label",
                                "horizontal_values",
                                "quantity_visible",
                                "quantity_has_entry",
                                "written_quantity",
                                "uncertain"
                            ],
                            "additionalProperties": False
                        }
                    }
                },
                "required": [
                    "rows"
                ],
                "additionalProperties": False
            }
        }
    }


def read_page2_quantity(images):

    if not images:
        return {
            "rows": []
        }


    prompt = """
②役務申込書・指導内容の商品表の
「数量」だけを確認します。

最重要：

印刷された列見出し

「数量」

を最初に特定してください。


その列の真下のセルだけが
数量欄です。


「数量」より右側にある、

・各単価
・小計
・商品定価
・消費税
・税込金額
・合計金額

などの金額を、
絶対に数量として読み取らないでください。


例えば同じ行の横方向に

1
1
1

と記入されていれば

horizontal_values=[1,1,1]


その行の数量欄に

3

と書かれていれば

written_quantity="3"

quantity_has_entry=true


数量欄が空欄なら

written_quantity=""
quantity_has_entry=false


36000
108000
648000

のような金額は数量ではありません。


記入対象になっている行だけを rows に入れてください。


数量セル自体が写真に写っていなければ

quantity_visible=false。


セルがはっきり見えて空欄なら

quantity_visible=true
quantity_has_entry=false
uncertain=false。
"""


    content = [
        {
            "type": "text",
            "text": prompt
        }
    ]


    for i, img in enumerate(
        images,
        start=1
    ):

        content.append({
            "type": "text",
            "text": f"【数量表画像{i}】"
        })

        content.append({
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(img),
                "detail": "high"
            }
        })


    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        response_format=quantity_schema()
    )


    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 画像を領域に振り分ける
# =========================================================

def prepare_and_route(files, page):

    prepared = []
    routes = {
        group: []
        for group in (
            PAGE1_GROUPS
            if page == 1
            else PAGE2_GROUPS
        )
    }

    infos = []


    for index, uploaded in enumerate(
        files,
        start=1
    ):

        img, rotation = prepare_image(
            uploaded
        )


        if page == 1:

            classification = classify_page1_image(
                img
            )

            groups = PAGE1_GROUPS

        else:

            classification = classify_page2_image(
                img
            )

            groups = PAGE2_GROUPS


        regions = classification[
            "regions"
        ]


        if "full_document" in regions:

            for group in groups:

                routes[group].append(
                    img
                )

        else:

            for region in regions:

                if region in routes:

                    routes[region].append(
                        img
                    )


        prepared.append(
            img
        )

        infos.append({
            "index": index,
            "rotation": rotation,
            "regions": regions,
            "reason": classification[
                "reason"
            ]
        })


    return prepared, routes, infos


# =========================================================
# 1枚目まとめて読む
# =========================================================

def read_page1_all(routes):

    fields = {}

    fields.update(
        read_page1_applicant(
            routes["applicant"]
        )
    )

    fields.update(
        read_page1_employment(
            routes["employment"]
        )
    )

    fields.update(
        read_page1_household(
            routes["household"]
        )
    )

    fields.update(
        read_page1_relation_top(
            routes["relation_top"]
        )
    )

    fields.update(
        read_page1_relation_bottom(
            routes["relation_bottom"]
        )
    )

    fields.update(
        read_page1_bank(
            routes["bank"]
        )
    )

    fields.update(
        read_page1_contract_bottom(
            routes["contract_bottom"]
        )
    )

    return fields


# =========================================================
# 2枚目まとめて読む
# =========================================================

def read_page2_all(routes):

    fields = {}

    fields.update(
        read_page2_guardian(
            routes["guardian_address"]
        )
    )

    fields.update(
        read_page2_target_school(
            routes["target_school"]
        )
    )

    fields.update(
        read_page2_course_dates(
            routes["course_dates"]
        )
    )

    fields.update(
        read_page2_receipt(
            routes["receipt"]
        )
    )

    quantity = read_page2_quantity(
        routes["quantity"]
    )

    return fields, quantity


# =========================================================
# 結果作成
# =========================================================

def result(
    name,
    status,
    observed,
    reason
):

    return {
        "name": name,
        "status": status,
        "observed_value": observed,
        "reason": reason
    }


def getf(fields, key):

    return fields.get(
        key,
        blank_field()
    )


def entry_result(
    fields,
    key,
    name
):

    f = getf(
        fields,
        key
    )


    if not f["visible"]:

        return result(
            name,
            "uncertain",
            "この欄が写真に写っていません",
            "この項目を確認できる写真がありません。"
        )


    if f["uncertain"]:

        return result(
            name,
            "uncertain",
            "判定できず",
            "画像から確実に判定できません。"
        )


    if f["has_entry"]:

        return result(
            name,
            "ok",
            "記入あり",
            "指定欄に記入があります。"
        )


    return result(
        name,
        "missing",
        "空欄",
        f"「{name}」の指定欄が空欄です。"
    )


def selection_result(
    fields,
    key,
    name
):

    f = getf(
        fields,
        key
    )


    if not f["visible"]:

        return result(
            name,
            "uncertain",
            "この欄が写真に写っていません",
            "この選択欄を確認できません。"
        )


    if f["uncertain"]:

        return result(
            name,
            "uncertain",
            "○を判定できず",
            "画像から○を確実に判定できません。"
        )


    if f["selected"]:

        return result(
            name,
            "ok",
            "○あり",
            "必要な選択を確認しました。"
        )


    return result(
        name,
        "missing",
        "○なし",
        f"「{name}」に必要な○がありません。"
    )


# =========================================================
# 1枚目 Python判定
# =========================================================

def page1_results(fields):

    results = []


    results.append(
        entry_result(
            fields,
            "applicant_name",
            "ご契約者氏名"
        )
    )


    results.append(
        entry_result(
            fields,
            "applicant_name_furigana",
            "ご契約者氏名フリガナ"
        )
    )


    # 契約者住所
    address = getf(
        fields,
        "applicant_address"
    )

    pref = getf(
        fields,
        "applicant_prefecture"
    )


    if (
        not address["visible"]
        or
        not pref["visible"]
    ):

        results.append(
            result(
                "ご契約者住所",
                "uncertain",
                "住所欄を確認できず",
                "ご契約者住所が写っている写真が必要です。"
            )
        )

    elif (
        address["uncertain"]
        or
        pref["uncertain"]
    ):

        results.append(
            result(
                "ご契約者住所",
                "uncertain",
                "判定できず",
                "住所または都道府県を確実に判定できません。"
            )
        )

    elif (
        address["has_entry"]
        and
        pref["text"].strip() in PREFECTURES
    ):

        results.append(
            result(
                "ご契約者住所",
                "ok",
                f"都道府県：{pref['text'].strip()}",
                "住所が都道府県から記入されています。"
            )
        )

    else:

        results.append(
            result(
                "ご契約者住所",
                "missing",
                (
                    "都道府県名なし"
                    if address["has_entry"]
                    else "空欄"
                ),
                "ご住所は都道府県名から記入する必要があります。"
            )
        )


    results.append(
        entry_result(
            fields,
            "applicant_address_furigana",
            "ご契約者住所フリガナ"
        )
    )


    # 雇用形態
    employment = [
        (
            "employment_regular",
            "正社員"
        ),
        (
            "employment_dispatch",
            "派遣社員"
        ),
        (
            "employment_contract",
            "契約社員"
        ),
        (
            "employment_parttime",
            "パート・アルバイト"
        ),
        (
            "employment_other",
            "その他"
        )
    ]


    visible_count = 0
    uncertain = False
    selected = []


    for key, label in employment:

        f = getf(
            fields,
            key
        )

        if f["visible"]:
            visible_count += 1

        if f["uncertain"]:
            uncertain = True

        if f["selected"]:
            selected.append(
                label
            )


    if visible_count == 0:

        results.append(
            result(
                "雇用形態",
                "uncertain",
                "雇用形態欄が写真に写っていません",
                "雇用形態部分の写真が必要です。"
            )
        )

    elif uncertain:

        results.append(
            result(
                "雇用形態",
                "uncertain",
                "○を判定できず",
                "雇用形態の○を確実に判定できません。"
            )
        )

    elif len(selected) == 1:

        results.append(
            result(
                "雇用形態",
                "ok",
                selected[0],
                "雇用形態の選択を確認しました。"
            )
        )

    elif len(selected) == 0:

        results.append(
            result(
                "雇用形態",
                "missing",
                "○なし",
                "雇用形態の選択がありません。"
            )
        )

    else:

        results.append(
            result(
                "雇用形態",
                "warning",
                "・".join(selected),
                "複数の雇用形態が選択されています。"
            )
        )


    # 派遣先
    dispatch = getf(
        fields,
        "employment_dispatch"
    )

    dispatch_company = getf(
        fields,
        "dispatch_company"
    )


    if dispatch["selected"]:

        if not dispatch_company["visible"]:

            results.append(
                result(
                    "派遣先・出向先",
                    "uncertain",
                    "派遣先欄が写真に写っていません",
                    "派遣社員の場合は派遣先会社名を確認する必要があります。"
                )
            )

        elif dispatch_company["uncertain"]:

            results.append(
                result(
                    "派遣先・出向先",
                    "uncertain",
                    "判定できず",
                    "派遣先会社名を確実に判定できません。"
                )
            )

        elif dispatch_company["has_entry"]:

            results.append(
                result(
                    "派遣先・出向先",
                    "ok",
                    "記入あり",
                    "派遣先・出向先会社名を確認しました。"
                )
            )

        else:

            results.append(
                result(
                    "派遣先・出向先",
                    "missing",
                    "空欄",
                    "派遣社員が選択されていますが、派遣先・出向先が空欄です。"
                )
            )

    else:

        results.append(
            result(
                "派遣先・出向先",
                "not_applicable",
                "対象外",
                "派遣社員が選択されていないため対象外です。"
            )
        )


    # 世帯主クレジット
    monthly = getf(
        fields,
        "household_credit_monthly"
    )


    if not monthly["visible"]:

        results.append(
            result(
                "世帯主クレジット月額",
                "uncertain",
                "該当欄が写真に写っていません",
                "『世帯主のクレジットの月あたりのお支払額』を確認できません。"
            )
        )

    elif monthly["uncertain"]:

        results.append(
            result(
                "世帯主クレジット月額",
                "uncertain",
                "読取不能",
                "指定欄の金額を確実に読み取れません。"
            )
        )

    elif not monthly["has_entry"]:

        results.append(
            result(
                "世帯主クレジット月額",
                "missing",
                "空欄",
                "月あたりのお支払額欄が空欄です。"
            )
        )

    else:

        digits = re.sub(
            r"[^\d]",
            "",
            monthly["text"]
        )

        amount = (
            int(digits)
            if digits
            else None
        )


        if amount is None:

            results.append(
                result(
                    "世帯主クレジット月額",
                    "uncertain",
                    monthly["text"],
                    "金額を数値として判定できません。"
                )
            )

        elif amount > 100000:

            results.append(
                result(
                    "世帯主クレジット月額",
                    "warning",
                    f"{amount:,}円",
                    "月あたりのお支払額が100,000円を超えています。"
                )
            )

        else:

            results.append(
                result(
                    "世帯主クレジット月額",
                    "ok",
                    f"{amount:,}円",
                    "月あたりのお支払額は100,000円以下です。"
                )
            )


    # =====================================================
    # 関係者情報
    # =====================================================

    results.append(
        entry_result(
            fields,
            "relation_name",
            "関係者情報・氏名"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_name_furigana",
            "関係者情報・氏名フリガナ"
        )
    )

    results.append(
        selection_result(
            fields,
            "relation_sex",
            "関係者情報・性別"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_birthdate",
            "関係者情報・生年月日"
        )
    )

    results.append(
        selection_result(
            fields,
            "relation_relationship",
            "関係者情報・ご契約者との関係"
        )
    )


    # 関係者住所：実住所 or 同上
    rel_address = getf(
        fields,
        "relation_address"
    )

    rel_address_same = getf(
        fields,
        "relation_address_same"
    )


    if (
        not rel_address["visible"]
        and
        not rel_address_same["visible"]
    ):

        results.append(
            result(
                "関係者情報・ご住所",
                "uncertain",
                "住所欄が写真に写っていません",
                "関係者情報のご住所欄を確認できません。"
            )
        )

    elif (
        rel_address["uncertain"]
        or
        rel_address_same["uncertain"]
    ):

        results.append(
            result(
                "関係者情報・ご住所",
                "uncertain",
                "判定できず",
                "関係者住所を確実に判定できません。"
            )
        )

    elif (
        rel_address["has_entry"]
        or
        rel_address_same["has_entry"]
    ):

        results.append(
            result(
                "関係者情報・ご住所",
                "ok",
                (
                    "同上"
                    if rel_address_same["has_entry"]
                    else "記入あり"
                ),
                "ご住所欄に実住所または『同上』があります。"
            )
        )

    else:

        results.append(
            result(
                "関係者情報・ご住所",
                "missing",
                "空欄",
                "関係者情報のご住所欄が空欄です。"
            )
        )


    results.append(
        entry_result(
            fields,
            "relation_address_postal",
            "関係者情報・ご住所の郵便番号"
        )
    )

    results.append(
        selection_result(
            fields,
            "relation_residence",
            "関係者情報・ご住居"
        )
    )


    # 本人連絡先
    home = getf(
        fields,
        "relation_home_phone"
    )

    mobile = getf(
        fields,
        "relation_mobile"
    )


    if (
        not home["visible"]
        and
        not mobile["visible"]
    ):

        results.append(
            result(
                "関係者情報・連絡先",
                "uncertain",
                "電話番号欄が写真に写っていません",
                "固定電話・携帯番号を確認できません。"
            )
        )

    elif (
        home["uncertain"]
        or
        mobile["uncertain"]
    ) and not (
        home["has_entry"]
        or
        mobile["has_entry"]
    ):

        results.append(
            result(
                "関係者情報・連絡先",
                "uncertain",
                "判定できず",
                "固定電話・携帯番号を確実に判定できません。"
            )
        )

    elif (
        home["has_entry"]
        or
        mobile["has_entry"]
    ):

        if (
            home["has_entry"]
            and
            mobile["has_entry"]
        ):

            observed = "固定電話あり・携帯番号あり"

        elif home["has_entry"]:

            observed = "固定電話あり"

        else:

            observed = "携帯番号あり"


        results.append(
            result(
                "関係者情報・連絡先",
                "ok",
                observed,
                "固定電話または携帯番号を確認しました。"
            )
        )

    else:

        results.append(
            result(
                "関係者情報・連絡先",
                "missing",
                "固定電話・携帯番号ともに空欄",
                "固定電話または携帯番号の記入が必要です。"
            )
        )


    results.append(
        entry_result(
            fields,
            "relation_income",
            "関係者情報・税込年収"
        )
    )

    results.append(
        selection_result(
            fields,
            "relation_employment",
            "関係者情報・雇用形態"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_years_service",
            "関係者情報・勤務年数"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_payday",
            "関係者情報・給料日"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_employer_name",
            "関係者情報・会社名"
        )
    )


    # 所在地
    location = getf(
        fields,
        "relation_location"
    )

    location_same = getf(
        fields,
        "relation_location_same"
    )


    if (
        not location["visible"]
        and
        not location_same["visible"]
    ):

        results.append(
            result(
                "関係者情報・所在地",
                "uncertain",
                "所在地欄が写真に写っていません",
                "関係者情報の所在地欄を確認できません。"
            )
        )

    elif (
        location["uncertain"]
        or
        location_same["uncertain"]
    ):

        results.append(
            result(
                "関係者情報・所在地",
                "uncertain",
                "判定できず",
                "所在地を確実に判定できません。"
            )
        )

    elif (
        location["has_entry"]
        or
        location_same["has_entry"]
    ):

        results.append(
            result(
                "関係者情報・所在地",
                "ok",
                (
                    "同上"
                    if location_same["has_entry"]
                    else "記入あり"
                ),
                "所在地欄に実住所または『同上』があります。"
            )
        )

    else:

        results.append(
            result(
                "関係者情報・所在地",
                "missing",
                "空欄",
                "関係者情報の所在地欄が空欄です。"
            )
        )


    results.append(
        entry_result(
            fields,
            "relation_location_postal",
            "関係者情報・所在地の郵便番号"
        )
    )

    results.append(
        entry_result(
            fields,
            "relation_location_phone",
            "関係者情報・所在地の電話番号"
        )
    )


    # 銀行
    yucho = getf(
        fields,
        "bank_yucho"
    )

    other = getf(
        fields,
        "bank_other"
    )


    if (
        not yucho["visible"]
        and
        not other["visible"]
    ):

        results.append(
            result(
                "銀行口座",
                "uncertain",
                "銀行口座欄が写真に写っていません",
                "銀行口座部分の写真が必要です。"
            )
        )

    elif (
        yucho["uncertain"]
        or
        other["uncertain"]
    ) and not (
        yucho["has_entry"]
        or
        other["has_entry"]
    ):

        results.append(
            result(
                "銀行口座",
                "uncertain",
                "判定できず",
                "銀行口座の記入を確実に判定できません。"
            )
        )

    elif (
        yucho["has_entry"]
        or
        other["has_entry"]
    ):

        results.append(
            result(
                "銀行口座",
                "ok",
                "記入あり",
                "ゆうちょまたはゆうちょ以外の銀行口座に記入があります。"
            )
        )

    else:

        results.append(
            result(
                "銀行口座",
                "missing",
                "両方空欄",
                "銀行口座情報が記入されていません。"
            )
        )


    results.append(
        entry_result(
            fields,
            "bank_account_furigana",
            "口座名義人フリガナ"
        )
    )

    results.append(
        entry_result(
            fields,
            "page1_service_period",
            "役務提供期間"
        )
    )

    results.append(
        entry_result(
            fields,
            "legal_receipt_date",
            "第42条書面の受領年月日"
        )
    )

    results.append(
        entry_result(
            fields,
            "payment_months",
            "支払ヶ月"
        )
    )


    return results


# =========================================================
# 2枚目判定
# =========================================================

def expected_prefecture_mark(pref):

    if pref == "東京都":
        return "都"

    if pref == "北海道":
        return "道"

    if pref in [
        "大阪府",
        "京都府"
    ]:
        return "府"

    if pref.endswith(
        "県"
    ):
        return "県"

    return None


def page2_results(fields, quantity_data):

    results = []


    results.append(
        entry_result(
            fields,
            "guardian_name",
            "保護者氏名"
        )
    )

    results.append(
        entry_result(
            fields,
            "guardian_furigana",
            "保護者氏名フリガナ"
        )
    )


    address = getf(
        fields,
        "page2_address"
    )

    pref_field = getf(
        fields,
        "page2_prefecture"
    )

    pref = pref_field[
        "text"
    ].strip()


    marks = {
        "都": getf(
            fields,
            "prefecture_to"
        ),
        "道": getf(
            fields,
            "prefecture_do"
        ),
        "府": getf(
            fields,
            "prefecture_fu"
        ),
        "県": getf(
            fields,
            "prefecture_ken"
        )
    }


    if (
        not address["visible"]
        or
        not pref_field["visible"]
    ):

        results.append(
            result(
                "ご住所・連絡先",
                "uncertain",
                "住所欄が写真に写っていません",
                "住所・都道府県を確認できません。"
            )
        )

    elif (
        address["uncertain"]
        or
        pref_field["uncertain"]
    ):

        results.append(
            result(
                "ご住所・連絡先",
                "uncertain",
                "判定できず",
                "住所を確実に判定できません。"
            )
        )

    elif pref not in PREFECTURES:

        results.append(
            result(
                "ご住所・連絡先",
                "missing",
                "都道府県名なし",
                "住所は都道府県名から記入する必要があります。"
            )
        )

    else:

        expected = expected_prefecture_mark(
            pref
        )

        selected_marks = [
            mark
            for mark, f in marks.items()
            if f["selected"]
        ]


        if (
            len(selected_marks) == 1
            and
            selected_marks[0] == expected
        ):

            results.append(
                result(
                    "ご住所・連絡先",
                    "ok",
                    f"{pref} / {expected}に○",
                    "都道府県名と対応する○を確認しました。"
                )
            )

        elif len(selected_marks) == 0:

            results.append(
                result(
                    "ご住所・連絡先",
                    "missing",
                    f"{pref} / 都・道・府・県の○なし",
                    "都・道・府・県の対応する文字に○がありません。"
                )
            )

        else:

            results.append(
                result(
                    "ご住所・連絡先",
                    "warning",
                    f"{pref} / ○：{'・'.join(selected_marks)}",
                    "都道府県名と○の位置を確認してください。"
                )
            )


    results.append(
        selection_result(
            fields,
            "target_a_yes",
            "指導対象A・有"
        )
    )


    school = [
        (
            "school_public",
            "公"
        ),
        (
            "school_national",
            "国"
        ),
        (
            "school_private",
            "私"
        )
    ]

    visible = 0
    uncertain = False
    selected = []


    for key, label in school:

        f = getf(
            fields,
            key
        )

        if f["visible"]:
            visible += 1

        if f["uncertain"]:
            uncertain = True

        if f["selected"]:
            selected.append(
                label
            )


    if visible == 0:

        results.append(
            result(
                "公・国・私",
                "uncertain",
                "この欄が写真に写っていません",
                "公・国・私を確認できません。"
            )
        )

    elif uncertain:

        results.append(
            result(
                "公・国・私",
                "uncertain",
                "○を判定できず",
                "公・国・私の○を確実に判定できません。"
            )
        )

    elif len(selected) == 1:

        results.append(
            result(
                "公・国・私",
                "ok",
                selected[0],
                "1つだけ○があります。"
            )
        )

    elif len(selected) == 0:

        results.append(
            result(
                "公・国・私",
                "missing",
                "○なし",
                "公・国・私のいずれにも○がありません。"
            )
        )

    else:

        results.append(
            result(
                "公・国・私",
                "warning",
                "・".join(selected),
                "公・国・私に複数の○があります。"
            )
        )


    # コース
    course = getf(
        fields,
        "course_name"
    )


    if not course["visible"]:

        results.append(
            result(
                "コース名",
                "uncertain",
                "コース名欄が写真に写っていません",
                "コース名を確認できません。"
            )
        )

    elif course["uncertain"]:

        results.append(
            result(
                "コース名",
                "uncertain",
                "判定できず",
                "コース名を確実に読めません。"
            )
        )

    elif not course["has_entry"]:

        results.append(
            result(
                "コース名",
                "missing",
                "空欄",
                "コース名欄が空欄です。"
            )
        )

    else:

        text = (
            course["text"]
            .replace(
                " ",
                ""
            )
            .replace(
                "　",
                ""
            )
        )

        ok = (
            (
                "週1" in text
                or
                "週１" in text
            )
            and
            (
                "90分" in text
                or
                "９０分" in text
            )
        )


        results.append(
            result(
                "コース名",
                "ok" if ok else "missing",
                course["text"],
                (
                    "コース名欄に『週1 90分』があります。"
                    if ok
                    else
                    "コース名欄に『週1 90分』を確認できません。"
                )
            )
        )


    results.append(
        entry_result(
            fields,
            "initial_instruction_date",
            "初回指導日"
        )
    )

    results.append(
        entry_result(
            fields,
            "service_period_a",
            "役務提供期間A"
        )
    )


    # 数量
    rows = quantity_data[
        "rows"
    ]

    lines = []

    has_missing = False
    has_warning = False
    has_uncertain = False
    checked = 0


    for row in rows:

        values = row[
            "horizontal_values"
        ]


        if not values:
            continue


        checked += 1

        expected = sum(
            values
        )

        label = (
            row[
                "row_label"
            ].strip()
            or
            f"{checked}行目"
        )

        calc = (
            " + ".join(
                str(v)
                for v in values
            )
            +
            f" = {expected}"
        )


        if not row[
            "quantity_visible"
        ]:

            has_uncertain = True

            lines.append(
                f"{label}：{calc} / 数量欄が写真に写っていません"
            )

            continue


        if row[
            "uncertain"
        ]:

            has_uncertain = True

            lines.append(
                f"{label}：{calc} / 数量欄：判定不能"
            )

            continue


        if not row[
            "quantity_has_entry"
        ]:

            has_missing = True

            lines.append(
                f"{label}：{calc} / 数量欄：空欄"
            )

            continue


        match = re.search(
            r"\d+",
            row[
                "written_quantity"
            ]
        )


        if not match:

            has_uncertain = True

            lines.append(
                f"{label}：{calc} / 数量欄：読取不能"
            )

            continue


        written = int(
            match.group()
        )


        if written >= 1000:

            has_uncertain = True

            lines.append(
                f"{label}：{calc} / 数量欄：{written}"
                "（金額誤読の可能性）"
            )

        elif written != expected:

            has_warning = True

            lines.append(
                f"{label}：{calc} / 数量欄：{written}"
            )

        else:

            lines.append(
                f"{label}：{calc} / 数量欄：{written}"
            )


    if has_missing:

        q_status = "missing"
        q_reason = "数量欄が空欄の行があります。"

    elif has_warning:

        q_status = "warning"
        q_reason = "横方向の合計と数量欄が一致しない行があります。"

    elif has_uncertain:

        q_status = "uncertain"
        q_reason = "数量欄を確実に確認できない行があります。"

    elif checked > 0:

        q_status = "ok"
        q_reason = "各行の横方向の合計と数量欄を確認しました。"

    else:

        q_status = "uncertain"
        q_reason = "数量表を確認できる写真がありません。"


    results.append(
        result(
            "数量",
            q_status,
            (
                " / ".join(lines)
                if lines
                else "数量表を確認できず"
            ),
            q_reason
        )
    )


    results.append(
        entry_result(
            fields,
            "receipt_signature",
            "受領サイン"
        )
    )


    return results


# =========================================================
# 表示
# =========================================================

def display_item(item):

    mapping = {
        "ok": (
            "✅",
            "問題なし"
        ),
        "missing": (
            "❌",
            "記入漏れ"
        ),
        "warning": (
            "⚠️",
            "要注意"
        ),
        "not_applicable": (
            "➖",
            "対象外"
        ),
        "uncertain": (
            "🔍",
            "要確認"
        )
    }


    icon, label = mapping[
        item["status"]
    ]


    with st.container(
        border=True
    ):

        st.markdown(
            f"### {icon} {item['name']}：{label}"
        )

        st.write(
            "読み取った内容："
            f"**{item['observed_value']}**"
        )

        st.caption(
            item["reason"]
        )


def display_routing(infos):

    labels = {
        "applicant": "契約者本人情報",
        "employment": "勤務先・雇用形態",
        "household": "世帯状況",
        "relation_top": "関係者情報・上側",
        "relation_bottom": "関係者情報・勤務先側",
        "bank": "銀行口座",
        "contract_bottom": "契約下部",
        "guardian_address": "保護者氏名・住所",
        "target_school": "指導対象A・公国私",
        "course_dates": "コース名・日付",
        "quantity": "数量表",
        "receipt": "受領サイン",
        "full_document": "書類全体",
        "unknown": "判定できず"
    }


    for info in infos:

        readable = [
            labels.get(
                r,
                r
            )
            for r in info["regions"]
        ]


        st.write(
            f"**画像{info['index']}**："
            +
            " / ".join(readable)
        )

        if info[
            "rotation"
        ] != 0:

            st.caption(
                f"{info['rotation']}°回転して向きを補正"
            )

        st.caption(
            info[
                "reason"
            ]
        )


# =========================================================
# アップロード
# =========================================================

st.divider()

st.markdown(
    "## 📷 写真を選択"
)

st.info(
    "おすすめは「全体1枚＋アップ写真」です。"
    "ただし4分割したアップ写真だけでも使えます。"
)


files1 = st.file_uploader(
    "① クレジット申込書の写真",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    accept_multiple_files=True,
    key="page1"
)


files2 = st.file_uploader(
    "② 役務申込書・指導内容の写真",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    accept_multiple_files=True,
    key="page2"
)


st.caption(
    "各書類1〜6枚まで。"
    "分割写真では項目名・見出しも一緒に写すと精度が上がります。"
)


# =========================================================
# 実行
# =========================================================

if st.button(
    "🤖 AIでチェックする",
    type="primary",
    use_container_width=True
):

    if not files1 and not files2:

        st.error(
            "写真を1枚以上選択してください。"
        )

        st.stop()


    if len(files1) > 6:

        st.error(
            "①は最大6枚までです。"
        )

        st.stop()


    if len(files2) > 6:

        st.error(
            "②は最大6枚までです。"
        )

        st.stop()


    total_missing = 0
    total_warning = 0
    total_uncertain = 0


    try:

        # =================================================
        # 1枚目
        # =================================================

        if files1:

            with st.spinner(
                "① 写真を1枚ずつ分類しています…"
            ):

                prepared1, routes1, infos1 = (
                    prepare_and_route(
                        files1,
                        1
                    )
                )


            with st.spinner(
                "① 各領域を専用AIで確認しています…"
            ):

                fields1 = read_page1_all(
                    routes1
                )

                results1 = page1_results(
                    fields1
                )


            st.divider()

            st.header(
                "① クレジット申込書"
            )


            with st.expander(
                "📍 AIが判断した各写真の場所",
                expanded=True
            ):

                display_routing(
                    infos1
                )


            with st.expander(
                "📷 使用した写真"
            ):

                for i, img in enumerate(
                    prepared1,
                    start=1
                ):

                    st.markdown(
                        f"**画像{i}**"
                    )

                    st.image(
                        img,
                        use_container_width=True
                    )


            for item in results1:

                display_item(
                    item
                )

                if item[
                    "status"
                ] == "missing":

                    total_missing += 1

                elif item[
                    "status"
                ] == "warning":

                    total_warning += 1

                elif item[
                    "status"
                ] == "uncertain":

                    total_uncertain += 1


        # =================================================
        # 2枚目
        # =================================================

        if files2:

            with st.spinner(
                "② 写真を1枚ずつ分類しています…"
            ):

                prepared2, routes2, infos2 = (
                    prepare_and_route(
                        files2,
                        2
                    )
                )


            with st.spinner(
                "② 各領域を専用AIで確認しています…"
            ):

                fields2, quantity2 = read_page2_all(
                    routes2
                )

                results2 = page2_results(
                    fields2,
                    quantity2
                )


            st.divider()

            st.header(
                "② 役務申込書・指導内容"
            )


            with st.expander(
                "📍 AIが判断した各写真の場所",
                expanded=True
            ):

                display_routing(
                    infos2
                )


            with st.expander(
                "📷 使用した写真"
            ):

                for i, img in enumerate(
                    prepared2,
                    start=1
                ):

                    st.markdown(
                        f"**画像{i}**"
                    )

                    st.image(
                        img,
                        use_container_width=True
                    )


            for item in results2:

                display_item(
                    item
                )

                if item[
                    "status"
                ] == "missing":

                    total_missing += 1

                elif item[
                    "status"
                ] == "warning":

                    total_warning += 1

                elif item[
                    "status"
                ] == "uncertain":

                    total_uncertain += 1


        # =================================================
        # まとめ
        # =================================================

        st.divider()

        st.markdown(
            "## 📋 チェック結果まとめ"
        )


        if (
            total_missing == 0
            and
            total_warning == 0
            and
            total_uncertain == 0
        ):

            st.success(
                "✅ 現在のチェック項目では問題は見つかりませんでした。"
            )

        else:

            if total_missing:

                st.error(
                    f"❌ 記入漏れ：{total_missing}件"
                )

            if total_warning:

                st.warning(
                    f"⚠️ 要注意：{total_warning}件"
                )

            if total_uncertain:

                st.info(
                    f"🔍 要確認：{total_uncertain}件"
                )


            st.caption(
                "「写真に写っていません」は記入漏れではありません。"
                "その部分のアップ写真を追加してください。"
            )


    except Exception as e:

        st.error(
            "AI判定中にエラーが発生しました。"
        )

        st.code(
            str(e)
        )
