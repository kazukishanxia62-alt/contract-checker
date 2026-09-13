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
    "全体写真・分割写真・アップ写真のどれでも使用できます。"
    "AIが写真内の印刷見出しから、書類のどの部分かを判断します。"
)

st.warning(
    "提出前の補助チェック用です。"
    "最終確認は必ず人が行ってください。"
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


# =========================================================
# 画像処理
# =========================================================

def pil_to_data_url(img):

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


def prepare_basic_image(uploaded):

    img = Image.open(uploaded)

    img = ImageOps.exif_transpose(
        img
    ).convert("RGB")

    max_side = 3000

    if max(img.size) > max_side:

        ratio = max_side / max(img.size)

        img = img.resize(
            (
                int(img.width * ratio),
                int(img.height * ratio)
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
                        "enum": [
                            0,
                            90,
                            180,
                            270
                        ]
                    }
                },

                "required": [
                    "rotation"
                ],

                "additionalProperties": False
            }
        }
    }


def detect_orientation(img):

    preview = img.copy()

    max_side = 1000

    if max(preview.size) > max_side:

        ratio = max_side / max(preview.size)

        preview = preview.resize(
            (
                int(preview.width * ratio),
                int(preview.height * ratio)
            ),
            Image.Resampling.LANCZOS
        )


    versions = {
        0: preview,
        90: preview.rotate(
            90,
            expand=True
        ),
        180: preview.rotate(
            180,
            expand=True
        ),
        270: preview.rotate(
            270,
            expand=True
        )
    }


    content = [
        {
            "type": "text",
            "text": """
同じ日本語契約書または契約書の一部分を
0度・90度・180度・270度に回転した画像です。

日本語の印刷文字が通常通り読める向きを選んでください。

写真が契約書全体ではなく、
一部分だけでも構いません。

内容のチェックは不要です。
文字が正しい方向になる回転角度だけ返してください。
"""
        }
    ]


    for angle, version in versions.items():

        content.append(
            {
                "type": "text",
                "text": f"【{angle}度版】"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": pil_to_data_url(version),
                    "detail": "low"
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

        response_format=orientation_schema()
    )


    data = json.loads(
        response.choices[0].message.content
    )

    return data["rotation"]


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
# 共通AI出力Schema
# =========================================================

def extraction_schema():

    return {
        "type": "json_schema",

        "json_schema": {
            "name": "contract_extraction",

            "strict": True,

            "schema": {
                "type": "object",

                "properties": {

                    "detected_regions": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {
                                "image_index": {
                                    "type": "integer"
                                },

                                "region": {
                                    "type": "string"
                                },

                                "description": {
                                    "type": "string"
                                }
                            },

                            "required": [
                                "image_index",
                                "region",
                                "description"
                            ],

                            "additionalProperties": False
                        }
                    },


                    "fields": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {

                                "key": {
                                    "type": "string"
                                },

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
                                "key",
                                "visible",
                                "has_entry",
                                "selected",
                                "text",
                                "uncertain"
                            ],

                            "additionalProperties": False
                        }
                    },


                    "quantity_rows": {
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
                    "detected_regions",
                    "fields",
                    "quantity_rows"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# AIに複数画像を送る
# =========================================================

def send_images_to_ai(images, prompt):

    content = [
        {
            "type": "text",
            "text": prompt
        }
    ]


    for index, img in enumerate(
        images,
        start=1
    ):

        content.append(
            {
                "type": "text",
                "text": (
                    f"【画像{index}】\n"
                    "この画像が書類のどの部分なのかも、"
                    "印刷されている項目名から判定してください。"
                )
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": pil_to_data_url(img),
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

        response_format=extraction_schema()
    )


    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 1枚目プロンプト
# =========================================================

PAGE1_PROMPT = """
あなたは日本語のクレジット申込書を確認する担当です。

複数の画像が送られます。

画像は、

・書類全体
・上半分
・下半分
・左上
・右上
・左下
・右下
・特定欄のアップ

など、どの撮り方でも構いません。

同じ書類を複数枚に分けて撮影している場合があります。


==================================================
最初に画像の場所を特定
==================================================

各画像について、
印刷されている見出しや項目名から、

・契約者情報
・勤務先
・雇用形態
・世帯状況
・関係者情報
・銀行口座
・契約情報
・その他

など、どの部分かを判断してください。

写真が一部分だけでも、
見出しから判断してください。

位置だけで判断してはいけません。

「左上にあるから契約者情報」
のような推測は禁止です。


==================================================
最重要ルール
==================================================

1.
指定欄が画像に写っていない場合、

visible=false

にしてください。

写っていない項目を
「空欄」と判断してはいけません。


2.
指定欄自体が見えていて、
その欄に手書きがない場合だけ

visible=true
has_entry=false

としてください。


3.
他の欄の文字を代用しない。


4.
印刷文字は手書き記入として扱わない。


5.
○については、
対象の文字そのものに
明確な手書きの○・囲み・選択印がある場合だけ

selected=true。


6.
不鮮明なら

uncertain=true。


==================================================
必ず返すfield key
==================================================

以下のkeyをすべて1回ずつ返してください。


applicant_name
applicant_name_furigana
applicant_address
applicant_prefecture
applicant_address_furigana

employment_regular
employment_dispatch
employment_contract
employment_parttime
employment_other
dispatch_company

household_credit_monthly

relation_applicable
relation_name
relation_name_furigana
relation_sex
relation_birthdate
relation_relationship
relation_address
relation_residence
relation_home_phone
relation_mobile
relation_income
relation_employment
relation_years_service
relation_payday
relation_employer_name
relation_location
relation_location_postal
relation_location_phone

bank_yucho
bank_other
bank_account_furigana

page1_service_period
legal_receipt_date
payment_months


==================================================
契約者住所
==================================================

applicant_address：

契約者本人の「ご住所」欄そのもの。

住所が手書きされているか。


applicant_prefecture：

住所の中に実際に

北海道
東京都
大阪府
兵庫県

などの都道府県名が書かれているか。

書かれていれば text に
都道府県名だけ入れてください。

例：

兵庫県神戸市～

なら

text="兵庫県"


神戸市～

しかなければ

text=""


市区町村から推測してはいけません。


applicant_address_furigana：

住所に対応するフリガナ欄そのもの。

氏名フリガナを代用しない。


==================================================
雇用形態
==================================================

employment_regular
employment_dispatch
employment_contract
employment_parttime
employment_other

はそれぞれ、

対象文字そのものに
○があるかだけを見る。

「派遣社員」という印刷文字が見えるだけでは
selected=trueにしてはいけません。


dispatch_company：

派遣先・出向先の会社名欄そのもの。


==================================================
世帯主クレジット月額
==================================================

household_credit_monthly は必ず

「世帯主のクレジットの月あたりのお支払額」

という欄そのものだけを見る。

近くの

「世帯主の年収(税込)」
「税込年収」

の数字を絶対に使わない。

金額が読めた場合だけ text に記入する。


==================================================
関係者情報
==================================================

「関係者情報」と印刷された枠内だけを見る。


relation_name：
関係者本人の氏名欄。


relation_name_furigana：
その氏名に対応するフリガナ。


relation_sex：
性別の必要な○。


relation_birthdate：
生年月日。


relation_relationship：
ご契約者との関係。


relation_address：
「ご住所」欄。


relation_residence：
「ご住居」の選択肢の○。


relation_home_phone：
本人の固定電話。


relation_mobile：
本人の携帯番号。


relation_income：
税込年収。


relation_employment：
関係者側の雇用形態。


relation_years_service：
勤務年数。


relation_payday：
給料日。


relation_employer_name：
会社名。


relation_location：
勤務先等の「所在地」。

実住所または「同上」があれば
has_entry=true。

「同上」の場合は text="同上"。


relation_location_postal：
所在地に付属する郵便番号。

本人住所側の郵便番号を使わない。


relation_location_phone：
所在地・勤務先側の電話番号。

本人携帯を代用しない。


==================================================
銀行口座
==================================================

bank_yucho：
ゆうちょ銀行側に記入があるか。


bank_other：
ゆうちょ銀行以外側に記入があるか。


bank_account_furigana：
口座名義人フリガナ。


==================================================
その他
==================================================

page1_service_period：

クレジット申込書側の
「役務提供期間」欄そのもの。


legal_receipt_date：

「特定商取引法第42条第2項又は第3項書面の受領年月日」

の欄そのもの。

別の日付を使わない。


payment_months：

指定された「ヶ月」欄そのもの。

近くの別の数字を使わない。


quantity_rows は1枚目では空配列 [] にしてください。
"""


# =========================================================
# 2枚目プロンプト
# =========================================================

PAGE2_PROMPT = """
あなたは日本語の
役務申込書・指導内容の確認担当です。

複数画像が送られます。

書類全体でも、
4分割画像でも、
特定箇所だけのアップでも構いません。


==================================================
画像の場所を特定
==================================================

印刷されている見出しから、

・保護者情報
・ご住所・連絡先
・指導対象A
・公・国・私
・コース名
・初回指導日
・役務提供期間
・商品表
・数量
・受領サイン

など、何の部分かを判断してください。


画像の位置だけで判断してはいけません。


==================================================
最重要
==================================================

項目自体が写っていないなら

visible=false。


項目が見えているが空欄なら

visible=true
has_entry=false。


別欄から補完禁止。


==================================================
必ず返すfield key
==================================================

以下をすべて1回ずつ返してください。

guardian_name
guardian_furigana

page2_address
page2_prefecture
prefecture_mark_to
prefecture_mark_do
prefecture_mark_fu
prefecture_mark_ken

target_a_yes

school_public
school_national
school_private

course_name

initial_instruction_date

service_period_a

receipt_signature


==================================================
保護者氏名
==================================================

guardian_name：
保護者氏名欄。


guardian_furigana：
その氏名に対応するフリガナ欄。


==================================================
住所
==================================================

page2_address：
住所欄そのもの。


page2_prefecture：

住所内に実際に都道府県名が書かれている場合だけ
text に都道府県名を入れる。

市区町村から推測禁止。


prefecture_mark_to
prefecture_mark_do
prefecture_mark_fu
prefecture_mark_ken

は、

「都・道・府・県」

の各文字に○があるか。

それぞれselectedで返す。


==================================================
指導対象A
==================================================

target_a_yes：

指導対象Aの

「有」

という文字そのものに
○がある場合だけ selected=true。


==================================================
公・国・私
==================================================

school_public
school_national
school_private

について、

公
国
私

の各文字そのものに○があるか。


==================================================
コース名
==================================================

course_name：

「コース名」と印刷された欄そのもの。

近くの

4回/月

などを使わない。


==================================================
初回指導日
==================================================

initial_instruction_date：

「初回指導日」の欄そのもの。


==================================================
役務提供期間
==================================================

service_period_a：

役務提供期間のA行だけ。

B行は不要。


==================================================
受領サイン
==================================================

receipt_signature：

右上にある

「書面交付日」

の右側の

「受領サイン →」

の直後の横長欄だけを見る。


保護者氏名
指導対象氏名
販売担当者氏名
その他の氏名

は絶対に受領サインとして使わない。


==================================================
数量
==================================================

quantity_rows を使用してください。

中央の商品表について、
記入されている各対象行を別々に返してください。


まず印刷された列見出し

「数量」

を探してください。


その真下のセルだけが
数量欄です。


数量列より右にある

各単価
小計
商品定価
消費税
税込価格
合計金額

などは数量ではありません。


例えば横方向が

1
1
1

なら

horizontal_values=[1,1,1]


同じ行の数量欄に3とあれば

written_quantity="3"

quantity_has_entry=true。


数量欄が空欄なら

written_quantity=""
quantity_has_entry=false。


数量欄そのものが画像に写っていなければ

quantity_visible=false。


金額を数量として絶対に読まない。
"""


# =========================================================
# AI読取
# =========================================================

def read_page1(images):

    return send_images_to_ai(
        images,
        PAGE1_PROMPT
    )


def read_page2(images):

    return send_images_to_ai(
        images,
        PAGE2_PROMPT
    )


# =========================================================
# field取得
# =========================================================

def field_dict(data):

    result = {}

    for item in data["fields"]:
        result[item["key"]] = item

    return result


def blank_field(key):

    return {
        "key": key,
        "visible": False,
        "has_entry": False,
        "selected": False,
        "text": "",
        "uncertain": True
    }


def get_field(fields, key):

    return fields.get(
        key,
        blank_field(key)
    )


# =========================================================
# 結果用
# =========================================================

def make_result(
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


def required_entry_result(
    fields,
    key,
    display_name
):

    f = get_field(
        fields,
        key
    )


    if not f["visible"]:

        return make_result(
            display_name,
            "uncertain",
            "この欄が写真に写っていません",
            "該当欄を確認できる写真がありません。"
        )


    if f["uncertain"]:

        return make_result(
            display_name,
            "uncertain",
            "判定できず",
            "画像から確実に判定できません。"
        )


    if f["has_entry"]:

        return make_result(
            display_name,
            "ok",
            "記入あり",
            "指定欄に記入があります。"
        )


    return make_result(
        display_name,
        "missing",
        "空欄",
        f"「{display_name}」の指定欄が空欄です。"
    )


def required_selection_result(
    fields,
    key,
    display_name
):

    f = get_field(
        fields,
        key
    )


    if not f["visible"]:

        return make_result(
            display_name,
            "uncertain",
            "この欄が写真に写っていません",
            "該当する選択欄を確認できません。"
        )


    if f["uncertain"]:

        return make_result(
            display_name,
            "uncertain",
            "判定できず",
            "○を確実に判定できません。"
        )


    if f["selected"]:

        return make_result(
            display_name,
            "ok",
            "○あり",
            "必要な選択を確認しました。"
        )


    return make_result(
        display_name,
        "missing",
        "○なし",
        f"「{display_name}」に必要な○がありません。"
    )


# =========================================================
# 1枚目判定
# =========================================================

def page1_results(data):

    fields = field_dict(
        data
    )

    results = []


    results.append(
        required_entry_result(
            fields,
            "applicant_name",
            "ご契約者氏名"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "applicant_name_furigana",
            "ご契約者氏名フリガナ"
        )
    )


    # 契約者住所
    address = get_field(
        fields,
        "applicant_address"
    )

    pref = get_field(
        fields,
        "applicant_prefecture"
    )


    if (
        not address["visible"]
        or
        not pref["visible"]
    ):

        results.append(
            make_result(
                "ご契約者住所",
                "uncertain",
                "住所欄を確認できず",
                "ご契約者住所が写っている写真が必要です。"
            )
        )

    elif address["uncertain"] or pref["uncertain"]:

        results.append(
            make_result(
                "ご契約者住所",
                "uncertain",
                "判定できず",
                "住所または都道府県を確実に読み取れません。"
            )
        )

    elif (
        address["has_entry"]
        and
        pref["text"].strip() in PREFECTURES
    ):

        results.append(
            make_result(
                "ご契約者住所",
                "ok",
                f"都道府県：{pref['text'].strip()}",
                "都道府県から住所が記入されています。"
            )
        )

    else:

        results.append(
            make_result(
                "ご契約者住所",
                "missing",
                (
                    "住所記入あり・都道府県なし"
                    if address["has_entry"]
                    else "住所欄が空欄"
                ),
                "ご住所は都道府県から記入する必要があります。"
            )
        )


    results.append(
        required_entry_result(
            fields,
            "applicant_address_furigana",
            "ご契約者住所フリガナ"
        )
    )


    # 雇用形態
    employment_keys = [
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


    employment_visible = False
    employment_uncertain = False
    selected = []


    for key, label in employment_keys:

        f = get_field(
            fields,
            key
        )

        if f["visible"]:
            employment_visible = True

        if f["uncertain"]:
            employment_uncertain = True

        if f["selected"]:
            selected.append(
                label
            )


    if not employment_visible:

        results.append(
            make_result(
                "雇用形態",
                "uncertain",
                "雇用形態欄が写真に写っていません",
                "雇用形態欄の写真が必要です。"
            )
        )

    elif employment_uncertain:

        results.append(
            make_result(
                "雇用形態",
                "uncertain",
                "○を判定できず",
                "雇用形態の○を確実に判別できません。"
            )
        )

    elif len(selected) == 1:

        results.append(
            make_result(
                "雇用形態",
                "ok",
                selected[0],
                "雇用形態の選択を確認しました。"
            )
        )

    elif len(selected) == 0:

        results.append(
            make_result(
                "雇用形態",
                "missing",
                "○なし",
                "雇用形態に○がありません。"
            )
        )

    else:

        results.append(
            make_result(
                "雇用形態",
                "warning",
                "・".join(selected),
                "雇用形態が複数選択されています。"
            )
        )


    # 派遣先
    dispatch = get_field(
        fields,
        "employment_dispatch"
    )

    dispatch_company = get_field(
        fields,
        "dispatch_company"
    )


    if dispatch["selected"]:

        if not dispatch_company["visible"]:

            results.append(
                make_result(
                    "派遣先・出向先",
                    "uncertain",
                    "派遣先欄が写真に写っていません",
                    "派遣社員の場合は派遣先会社名の確認が必要です。"
                )
            )

        elif dispatch_company["has_entry"]:

            results.append(
                make_result(
                    "派遣先・出向先",
                    "ok",
                    "記入あり",
                    "派遣社員のため派遣先会社名を確認しました。"
                )
            )

        else:

            results.append(
                make_result(
                    "派遣先・出向先",
                    "missing",
                    "空欄",
                    "派遣社員ですが、派遣先会社名が空欄です。"
                )
            )

    else:

        results.append(
            make_result(
                "派遣先・出向先",
                "not_applicable",
                "対象外",
                "派遣社員が選択されていないため対象外です。"
            )
        )


    # 世帯主クレジット
    monthly = get_field(
        fields,
        "household_credit_monthly"
    )


    if not monthly["visible"]:

        results.append(
            make_result(
                "世帯主クレジット月額",
                "uncertain",
                "該当欄が写真に写っていません",
                "月あたりのお支払額欄を確認できません。"
            )
        )

    elif monthly["uncertain"]:

        results.append(
            make_result(
                "世帯主クレジット月額",
                "uncertain",
                "読取不能",
                "金額を確実に読み取れません。"
            )
        )

    elif not monthly["has_entry"]:

        results.append(
            make_result(
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
                make_result(
                    "世帯主クレジット月額",
                    "uncertain",
                    monthly["text"],
                    "金額を数値として判定できません。"
                )
            )

        elif amount > 100000:

            results.append(
                make_result(
                    "世帯主クレジット月額",
                    "warning",
                    f"{amount:,}円",
                    "100,000円を超えています。"
                )
            )

        else:

            results.append(
                make_result(
                    "世帯主クレジット月額",
                    "ok",
                    f"{amount:,}円",
                    "100,000円以下です。"
                )
            )


    # =====================================================
    # 関係者情報
    # =====================================================

    relation_items = [
        (
            "relation_name",
            "関係者情報・氏名",
            "entry"
        ),
        (
            "relation_name_furigana",
            "関係者情報・氏名フリガナ",
            "entry"
        ),
        (
            "relation_sex",
            "関係者情報・性別",
            "selection"
        ),
        (
            "relation_birthdate",
            "関係者情報・生年月日",
            "entry"
        ),
        (
            "relation_relationship",
            "関係者情報・ご契約者との関係",
            "selection"
        ),
        (
            "relation_address",
            "関係者情報・ご住所",
            "entry"
        ),
        (
            "relation_residence",
            "関係者情報・ご住居",
            "selection"
        ),
        (
            "relation_income",
            "関係者情報・税込年収",
            "entry"
        ),
        (
            "relation_employment",
            "関係者情報・雇用形態",
            "selection"
        ),
        (
            "relation_years_service",
            "関係者情報・勤務年数",
            "entry"
        ),
        (
            "relation_payday",
            "関係者情報・給料日",
            "entry"
        ),
        (
            "relation_employer_name",
            "関係者情報・会社名",
            "entry"
        ),
        (
            "relation_location_postal",
            "関係者情報・所在地の郵便番号",
            "entry"
        ),
        (
            "relation_location_phone",
            "関係者情報・所在地の電話番号",
            "entry"
        )
    ]


    for key, name, kind in relation_items:

        if kind == "entry":

            results.append(
                required_entry_result(
                    fields,
                    key,
                    name
                )
            )

        else:

            results.append(
                required_selection_result(
                    fields,
                    key,
                    name
                )
            )


    # 所在地
    location = get_field(
        fields,
        "relation_location"
    )


    if not location["visible"]:

        results.append(
            make_result(
                "関係者情報・所在地",
                "uncertain",
                "所在地欄が写真に写っていません",
                "所在地欄を確認できません。"
            )
        )

    elif location["uncertain"]:

        results.append(
            make_result(
                "関係者情報・所在地",
                "uncertain",
                "判定できず",
                "所在地欄を確実に判定できません。"
            )
        )

    elif location["has_entry"]:

        results.append(
            make_result(
                "関係者情報・所在地",
                "ok",
                (
                    "同上"
                    if "同上" in location["text"]
                    else "記入あり"
                ),
                "所在地の記入を確認しました。"
            )
        )

    else:

        results.append(
            make_result(
                "関係者情報・所在地",
                "missing",
                "空欄",
                "関係者情報の所在地欄が空欄です。"
            )
        )


    # 連絡先
    home_phone = get_field(
        fields,
        "relation_home_phone"
    )

    mobile = get_field(
        fields,
        "relation_mobile"
    )


    if (
        not home_phone["visible"]
        and
        not mobile["visible"]
    ):

        results.append(
            make_result(
                "関係者情報・連絡先",
                "uncertain",
                "連絡先欄が写真に写っていません",
                "固定電話または携帯番号の確認が必要です。"
            )
        )

    elif (
        home_phone["has_entry"]
        or
        mobile["has_entry"]
    ):

        results.append(
            make_result(
                "関係者情報・連絡先",
                "ok",
                (
                    "固定電話あり"
                    if home_phone["has_entry"]
                    else "携帯番号あり"
                ),
                "固定電話または携帯番号を確認しました。"
            )
        )

    else:

        results.append(
            make_result(
                "関係者情報・連絡先",
                "missing",
                "固定電話・携帯番号ともに空欄",
                "固定電話または携帯番号の記入が必要です。"
            )
        )


    # 銀行口座
    yucho = get_field(
        fields,
        "bank_yucho"
    )

    other_bank = get_field(
        fields,
        "bank_other"
    )


    if (
        not yucho["visible"]
        and
        not other_bank["visible"]
    ):

        results.append(
            make_result(
                "銀行口座",
                "uncertain",
                "銀行口座欄が写真に写っていません",
                "銀行口座欄を確認できません。"
            )
        )

    elif (
        yucho["has_entry"]
        or
        other_bank["has_entry"]
    ):

        results.append(
            make_result(
                "銀行口座",
                "ok",
                "記入あり",
                "ゆうちょまたはゆうちょ以外の記入があります。"
            )
        )

    else:

        results.append(
            make_result(
                "銀行口座",
                "missing",
                "両方空欄",
                "銀行口座情報が記入されていません。"
            )
        )


    results.append(
        required_entry_result(
            fields,
            "bank_account_furigana",
            "口座名義人フリガナ"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "page1_service_period",
            "役務提供期間"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "legal_receipt_date",
            "第42条書面の受領年月日"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "payment_months",
            "支払ヶ月"
        )
    )


    return results


# =========================================================
# 2枚目判定
# =========================================================

def expected_prefecture_mark(prefecture):

    if prefecture == "東京都":
        return "都"

    if prefecture == "北海道":
        return "道"

    if prefecture in [
        "大阪府",
        "京都府"
    ]:
        return "府"

    if prefecture.endswith("県"):
        return "県"

    return None


def page2_results(data):

    fields = field_dict(
        data
    )

    results = []


    results.append(
        required_entry_result(
            fields,
            "guardian_name",
            "保護者氏名"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "guardian_furigana",
            "保護者氏名フリガナ"
        )
    )


    # 住所＋都道府県
    address = get_field(
        fields,
        "page2_address"
    )

    pref_field = get_field(
        fields,
        "page2_prefecture"
    )


    pref = pref_field[
        "text"
    ].strip()


    marks = {
        "都": get_field(
            fields,
            "prefecture_mark_to"
        ),
        "道": get_field(
            fields,
            "prefecture_mark_do"
        ),
        "府": get_field(
            fields,
            "prefecture_mark_fu"
        ),
        "県": get_field(
            fields,
            "prefecture_mark_ken"
        )
    }


    if (
        not address["visible"]
        or
        not pref_field["visible"]
    ):

        results.append(
            make_result(
                "ご住所・連絡先",
                "uncertain",
                "住所欄が写真に写っていません",
                "住所・都道府県の確認ができません。"
            )
        )

    elif pref not in PREFECTURES:

        results.append(
            make_result(
                "ご住所・連絡先",
                "missing",
                "都道府県を確認できず",
                "住所は都道府県から記入する必要があります。"
            )
        )

    else:

        expected = expected_prefecture_mark(
            pref
        )

        selected_marks = [
            mark
            for mark, value in marks.items()
            if value["selected"]
        ]


        if (
            len(selected_marks) == 1
            and
            selected_marks[0] == expected
        ):

            results.append(
                make_result(
                    "ご住所・連絡先",
                    "ok",
                    f"{pref} / {expected}に○",
                    "都道府県名と○を確認しました。"
                )
            )

        elif len(selected_marks) == 0:

            results.append(
                make_result(
                    "ご住所・連絡先",
                    "missing",
                    f"{pref} / 都道府県の○なし",
                    "都・道・府・県の対応する文字に○がありません。"
                )
            )

        else:

            results.append(
                make_result(
                    "ご住所・連絡先",
                    "warning",
                    f"{pref} / ○：{'・'.join(selected_marks)}",
                    "都道府県名と○の位置を確認してください。"
                )
            )


    results.append(
        required_selection_result(
            fields,
            "target_a_yes",
            "指導対象A・有"
        )
    )


    # 公国私
    school_keys = [
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


    visible = False
    uncertain = False
    selected = []


    for key, label in school_keys:

        f = get_field(
            fields,
            key
        )

        if f["visible"]:
            visible = True

        if f["uncertain"]:
            uncertain = True

        if f["selected"]:
            selected.append(
                label
            )


    if not visible:

        results.append(
            make_result(
                "公・国・私",
                "uncertain",
                "該当欄が写真に写っていません",
                "公・国・私の欄を確認できません。"
            )
        )

    elif uncertain:

        results.append(
            make_result(
                "公・国・私",
                "uncertain",
                "判定できず",
                "○を確実に判定できません。"
            )
        )

    elif len(selected) == 1:

        results.append(
            make_result(
                "公・国・私",
                "ok",
                selected[0],
                "1つだけ○があります。"
            )
        )

    elif len(selected) == 0:

        results.append(
            make_result(
                "公・国・私",
                "missing",
                "○なし",
                "公・国・私のいずれにも○がありません。"
            )
        )

    else:

        results.append(
            make_result(
                "公・国・私",
                "warning",
                "・".join(selected),
                "複数に○があります。"
            )
        )


    # コース名
    course = get_field(
        fields,
        "course_name"
    )


    if not course["visible"]:

        results.append(
            make_result(
                "コース名",
                "uncertain",
                "コース名欄が写真に写っていません",
                "コース名を確認できません。"
            )
        )

    elif not course["has_entry"]:

        results.append(
            make_result(
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
            make_result(
                "コース名",
                "ok" if ok else "missing",
                course["text"],
                (
                    "『週1 90分』を確認しました。"
                    if ok
                    else
                    "コース名欄に『週1 90分』を確認できません。"
                )
            )
        )


    results.append(
        required_entry_result(
            fields,
            "initial_instruction_date",
            "初回指導日"
        )
    )


    results.append(
        required_entry_result(
            fields,
            "service_period_a",
            "役務提供期間A"
        )
    )


    # 数量
    rows = data[
        "quantity_rows"
    ]

    quantity_lines = []

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
            row["row_label"]
            or f"{checked}行目"
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

            quantity_lines.append(
                f"{label}：{calc} / 数量欄が写真に写っていません"
            )

            continue


        if row[
            "uncertain"
        ]:

            has_uncertain = True

            quantity_lines.append(
                f"{label}：{calc} / 数量欄：判定不能"
            )

            continue


        if not row[
            "quantity_has_entry"
        ]:

            has_missing = True

            quantity_lines.append(
                f"{label}：{calc} / 数量欄：空欄"
            )

            continue


        number_match = re.search(
            r"\d+",
            row[
                "written_quantity"
            ]
        )


        if not number_match:

            has_uncertain = True

            quantity_lines.append(
                f"{label}：{calc} / 数量欄：読取不能"
            )

            continue


        written = int(
            number_match.group()
        )


        if written >= 1000:

            has_uncertain = True

            quantity_lines.append(
                f"{label}：{calc} / 数量欄：{written}"
                "（金額誤読の可能性）"
            )

        elif written != expected:

            has_warning = True

            quantity_lines.append(
                f"{label}：{calc} / 数量欄：{written}"
            )

        else:

            quantity_lines.append(
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
        q_reason = "数量欄を確認できない行があります。"

    elif checked > 0:

        q_status = "ok"
        q_reason = "各行の数量を確認しました。"

    else:

        q_status = "uncertain"
        q_reason = "数量表が写っている画像を確認できません。"


    results.append(
        make_result(
            "数量",
            q_status,
            (
                " / ".join(
                    quantity_lines
                )
                if quantity_lines
                else "数量表を確認できず"
            ),
            q_reason
        )
    )


    results.append(
        required_entry_result(
            fields,
            "receipt_signature",
            "受領サイン"
        )
    )


    return results


# =========================================================
# 結果表示
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


    icon, label = mapping.get(
        item["status"],
        (
            "🔍",
            "要確認"
        )
    )


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


# =========================================================
# 複数ファイル準備
# =========================================================

def prepare_multiple_files(files):

    images = []

    rotation_infos = []


    for index, uploaded in enumerate(
        files,
        start=1
    ):

        img, rotation = prepare_image(
            uploaded
        )

        images.append(
            img
        )

        rotation_infos.append(
            {
                "index": index,
                "rotation": rotation
            }
        )


    return images, rotation_infos


# =========================================================
# アップロード
# =========================================================

st.divider()

st.markdown(
    "## 📷 写真を選択"
)

st.info(
    "1枚の全体写真でもOK。"
    "4分割して近くから撮った写真でもOK。"
    "全体＋アップ写真を一緒に入れてもOKです。"
)


st.markdown(
    "### ① クレジット申込書"
)

files1 = st.file_uploader(
    "1枚目の写真を1〜6枚選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    accept_multiple_files=True,
    key="page1"
)


st.markdown(
    "### ② 役務申込書・指導内容"
)

files2 = st.file_uploader(
    "2枚目の写真を1〜6枚選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    accept_multiple_files=True,
    key="page2"
)


st.caption(
    "分割して撮る場合は、"
    "項目名や見出しが少し入るように撮ると精度が上がります。"
)


# =========================================================
# チェック実行
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


    total_missing = 0
    total_warning = 0
    total_uncertain = 0


    try:

        # =====================================================
        # 1枚目
        # =====================================================

        if files1:

            if len(files1) > 6:

                st.error(
                    "1枚目は最大6枚までにしてください。"
                )

                st.stop()


            with st.spinner(
                "① 写真の向きと各領域を確認しています…"
            ):

                images1, rotations1 = (
                    prepare_multiple_files(
                        files1
                    )
                )

                data1 = read_page1(
                    images1
                )

                results1 = page1_results(
                    data1
                )


            st.divider()

            st.header(
                "① クレジット申込書"
            )


            # AIがどこだと判断したか表示
            with st.expander(
                "📍 AIが判断した写真の場所"
            ):

                for region in data1[
                    "detected_regions"
                ]:

                    st.write(
                        f"画像{region['image_index']}："
                        f"**{region['region']}**"
                    )

                    if region[
                        "description"
                    ]:

                        st.caption(
                            region[
                                "description"
                            ]
                        )


            with st.expander(
                "📷 使用した写真"
            ):

                for i, img in enumerate(
                    images1,
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


        # =====================================================
        # 2枚目
        # =====================================================

        if files2:

            if len(files2) > 6:

                st.error(
                    "2枚目は最大6枚までにしてください。"
                )

                st.stop()


            with st.spinner(
                "② 写真の向きと各領域を確認しています…"
            ):

                images2, rotations2 = (
                    prepare_multiple_files(
                        files2
                    )
                )

                data2 = read_page2(
                    images2
                )

                results2 = page2_results(
                    data2
                )


            st.divider()

            st.header(
                "② 役務申込書・指導内容"
            )


            with st.expander(
                "📍 AIが判断した写真の場所"
            ):

                for region in data2[
                    "detected_regions"
                ]:

                    st.write(
                        f"画像{region['image_index']}："
                        f"**{region['region']}**"
                    )

                    if region[
                        "description"
                    ]:

                        st.caption(
                            region[
                                "description"
                            ]
                        )


            with st.expander(
                "📷 使用した写真"
            ):

                for i, img in enumerate(
                    images2,
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


        # =====================================================
        # まとめ
        # =====================================================

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
                "✅ 現在のチェック項目では"
                "問題は見つかりませんでした。"
            )

        else:

            if total_missing > 0:

                st.error(
                    f"❌ 記入漏れ："
                    f"{total_missing}件"
                )


            if total_warning > 0:

                st.warning(
                    f"⚠️ 要注意："
                    f"{total_warning}件"
                )


            if total_uncertain > 0:

                st.info(
                    f"🔍 要確認："
                    f"{total_uncertain}件"
                )


            st.caption(
                "「この欄が写真に写っていません」は、"
                "空欄という意味ではありません。"
                "その部分の写真を追加すると判定できます。"
            )


    except Exception as e:

        st.error(
            "AI判定中にエラーが発生しました。"
        )

        st.code(
            str(e)
        )
