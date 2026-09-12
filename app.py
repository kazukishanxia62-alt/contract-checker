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
    "契約書の写真をAIで読み取り、"
    "記入漏れ・選択漏れ・条件違反をチェックします。"
)

st.warning(
    "提出前の補助チェック用です。"
    "最終確認は必ず人が行ってください。"
)


# =========================================================
# OpenAI
# =========================================================

try:
    client = OpenAI(
        api_key=st.secrets["OPENAI_API_KEY"]
    )
except Exception:
    st.error("OPENAI_API_KEY が設定されていません。")
    st.stop()


MODEL = "gpt-5.4-mini"


# =========================================================
# 都道府県
# =========================================================

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
# 書類情報
# =========================================================

DOCUMENT_INFO = {

    "1枚目": {
        "display_name": "① クレジット申込書",
        "description": (
            "申込者情報、勤務先、世帯状況、関係者情報、"
            "銀行口座などが載っている書類"
        )
    },

    "2枚目": {
        "display_name": "② 役務申込書・指導内容",
        "description": (
            "保護者氏名、指導対象、公・国・私、コース名、"
            "初回指導日、役務提供期間、数量、受領サイン"
            "などが載っている書類"
        )
    }
}


# =========================================================
# 画像処理
# =========================================================

def prepare_image(uploaded):

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
            )
        )

    return img


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


def crop_by_ratio(
    img,
    left,
    top,
    right,
    bottom
):

    w, h = img.size

    return img.crop(
        (
            int(w * left),
            int(h * top),
            int(w * right),
            int(h * bottom)
        )
    )


# =========================================================
# 1枚目 クロップ
# =========================================================

def create_page1_crops(img):

    return {

        "申込者情報": crop_by_ratio(
            img,
            0.00,
            0.05,
            0.58,
            0.38
        ),

        "勤務先": crop_by_ratio(
            img,
            0.00,
            0.28,
            1.00,
            0.60
        ),

        "世帯主・世帯状況": crop_by_ratio(
            img,
            0.00,
            0.45,
            1.00,
            0.72
        ),

        "関係者情報": crop_by_ratio(
            img,
            0.00,
            0.56,
            1.00,
            0.88
        ),

        "銀行口座": crop_by_ratio(
            img,
            0.00,
            0.78,
            1.00,
            1.00
        )
    }


# =========================================================
# 2枚目 クロップ
# =========================================================

def create_page2_crops(img):

    return {

        "住所": crop_by_ratio(
            img,
            0.00,
            0.03,
            0.56,
            0.35
        ),

        "指導対象・公国私": crop_by_ratio(
            img,
            0.42,
            0.03,
            1.00,
            0.36
        ),

        "コース名": crop_by_ratio(
            img,
            0.00,
            0.30,
            0.50,
            0.70
        ),

        "数量表": crop_by_ratio(
            img,
            0.35,
            0.28,
            0.78,
            0.78
        ),

        # 右上の書面交付日・受領サイン付近だけ
        "受領サイン": crop_by_ratio(
            img,
            0.58,
            0.12,
            1.00,
            0.30
        )
    }


# =========================================================
# 1枚目 Schema
# =========================================================

def page1_schema():

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "page1_read",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    "application_date": {
                        "type": "object",
                        "properties": {
                            "has_year": {"type": "boolean"},
                            "has_month": {"type": "boolean"},
                            "has_day": {"type": "boolean"}
                        },
                        "required": [
                            "has_year",
                            "has_month",
                            "has_day"
                        ],
                        "additionalProperties": False
                    },

                    "applicant_name": {
                        "type": "object",
                        "properties": {
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "applicant_name_furigana": {
                        "type": "object",
                        "properties": {
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "applicant_address": {
                        "type": "object",
                        "properties": {
                            "written_prefecture": {
                                "type": "string"
                            },
                            "address_has_handwriting": {
                                "type": "boolean"
                            },
                            "address_furigana_has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "written_prefecture",
                            "address_has_handwriting",
                            "address_furigana_has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "employment": {
                        "type": "object",
                        "properties": {
                            "regular_employee_circled": {
                                "type": "boolean"
                            },
                            "dispatch_employee_circled": {
                                "type": "boolean"
                            },
                            "contract_employee_circled": {
                                "type": "boolean"
                            },
                            "part_time_circled": {
                                "type": "boolean"
                            },
                            "other_circled": {
                                "type": "boolean"
                            },
                            "dispatch_company_has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "regular_employee_circled",
                            "dispatch_employee_circled",
                            "contract_employee_circled",
                            "part_time_circled",
                            "other_circled",
                            "dispatch_company_has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "household_credit_monthly": {
                        "type": "object",
                        "properties": {
                            "written_amount": {
                                "type": "string"
                            },
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "written_amount",
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "related_person": {
                        "type": "object",
                        "properties": {

                            "applicable": {
                                "type": "boolean"
                            },

                            "name_has_handwriting": {
                                "type": "boolean"
                            },

                            "address_has_handwriting": {
                                "type": "boolean"
                            },

                            "residence_circle_present": {
                                "type": "boolean"
                            },

                            "location_has_handwriting": {
                                "type": "boolean"
                            },

                            "location_is_same_as_above": {
                                "type": "boolean"
                            },

                            "postal_code_has_handwriting": {
                                "type": "boolean"
                            },

                            "telephone_has_handwriting": {
                                "type": "boolean"
                            },

                            "mobile_has_handwriting": {
                                "type": "boolean"
                            },

                            "other_required_blank": {
                                "type": "boolean"
                            },

                            "required_circle_missing": {
                                "type": "boolean"
                            }
                        },

                        "required": [
                            "applicable",
                            "name_has_handwriting",
                            "address_has_handwriting",
                            "residence_circle_present",
                            "location_has_handwriting",
                            "location_is_same_as_above",
                            "postal_code_has_handwriting",
                            "telephone_has_handwriting",
                            "mobile_has_handwriting",
                            "other_required_blank",
                            "required_circle_missing"
                        ],

                        "additionalProperties": False
                    },

                    "bank_account": {
                        "type": "object",
                        "properties": {
                            "yucho_has_handwriting": {
                                "type": "boolean"
                            },
                            "other_bank_has_handwriting": {
                                "type": "boolean"
                            },
                            "account_name_furigana_has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "yucho_has_handwriting",
                            "other_bank_has_handwriting",
                            "account_name_furigana_has_handwriting"
                        ],
                        "additionalProperties": False
                    }
                },

                "required": [
                    "application_date",
                    "applicant_name",
                    "applicant_name_furigana",
                    "applicant_address",
                    "employment",
                    "household_credit_monthly",
                    "related_person",
                    "bank_account"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 1枚目 AI読取
# =========================================================

def strict_read_page1(img):

    crops = create_page1_crops(img)

    content = [

        {
            "type": "text",
            "text": """
あなたはクレジット申込書の指定欄を
正確に読み取る担当です。

OK/NGは判断しません。

実際にその欄に見える
手書き記入・○・数字だけを返してください。

絶対に別の欄から補完してはいけません。

==================================================
最重要
==================================================

・印刷文字は手書き記入として扱わない

・空欄は空欄として返す

・○は対象文字そのものに明確に付いている場合だけ true

・住所から都道府県を推測しない

・別の人物の住所、電話、フリガナを代用しない

・画像が不鮮明でも勝手に true にしない


==================================================
申込者住所
==================================================

ご契約者・申込者本人の住所欄を見る。

都道府県が実際に書かれている場合だけ
written_prefecture に入れる。

例：

神戸市灘区～

だけなら、

written_prefecture = ""

兵庫県とは推測しない。

住所用フリガナ欄も
別項目として確認する。

氏名フリガナを住所フリガナとして使わない。


==================================================
雇用形態
==================================================

各雇用形態の文字そのものに
○が付いているかを別々に確認する。

特に「派遣社員」は、
その文字自体に明確な○がある場合だけ

dispatch_employee_circled = true

にする。

近くの○を誤認しない。

派遣先・出向先会社名についても、
その指定欄そのものだけを見る。


==================================================
世帯主クレジット月額
==================================================

「世帯主のクレジットの月あたりのお支払額」
の金額だけを読む。

別の金額を代用しない。


==================================================
関係者情報
==================================================

関係者情報欄を確認する。

夫が申込者なら妻、
妻が申込者なら夫の情報。

対象外なら applicable = false。


【氏名】

関係者情報の氏名欄そのもの。


【ご住所】

「ご住所」と印刷された欄そのもの。

記入がなければ false。


【ご住居】

ご住居の選択肢に
実際に○があるか。

必要な○がなければ
residence_circle_present = false。


【所在地】

所在地欄そのものを見る。

住所が書かれている
または
「同上」

なら有効。

「同上」の場合だけ

location_is_same_as_above = true。

所在地欄が完全な空欄なら false。


【所在地の郵便番号】

所在地内の郵便番号欄そのものを見る。

別の住所の郵便番号を使わない。


【所在地の電話番号】

所在地内の電話番号欄だけを見る。


【携帯番号】

関係者情報内の携帯番号欄を見る。

固定電話とは別。


【その他】

関係者情報内で、
記入必須と思われる通常の欄が
明らかに空欄なら

other_required_blank = true。

選択式で必要な○が
明らかに付いていない場合は

required_circle_missing = true。


==================================================
銀行口座
==================================================

ゆうちょ銀行と
ゆうちょ銀行以外の銀行を区別する。

どちらに記入があるかだけを返す。

口座名義人フリガナは
その指定欄だけを見る。
"""
        },

        {
            "type": "text",
            "text": "以下は1枚目全体です。"
        },

        {
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(img),
                "detail": "high"
            }
        }
    ]


    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text": f"以下は【{name}】周辺です。"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": pil_to_data_url(crop),
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

        response_format=page1_schema()
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 1枚目 Python判定
# =========================================================

def page1_results(data):

    results = []


    # -----------------------------------------------------
    # お申込年月日
    # -----------------------------------------------------

    d = data["application_date"]

    ok = (
        d["has_year"]
        and d["has_month"]
        and d["has_day"]
    )

    results.append(
        {
            "name": "お申込年月日",
            "status": "ok" if ok else "missing",
            "observed_value": "年月日記入あり" if ok else "一部または全部空欄",
            "reason": (
                "年・月・日を確認しました。"
                if ok
                else "お申込年月日の必要箇所が不足しています。"
            )
        }
    )


    # -----------------------------------------------------
    # 氏名
    # -----------------------------------------------------

    ok = data["applicant_name"]["has_handwriting"]

    results.append(
        {
            "name": "ご契約者氏名",
            "status": "ok" if ok else "missing",
            "observed_value": "記入あり" if ok else "空欄",
            "reason": (
                "氏名欄に記入があります。"
                if ok
                else "氏名欄に記入を確認できません。"
            )
        }
    )


    # -----------------------------------------------------
    # 氏名フリガナ
    # -----------------------------------------------------

    ok = data[
        "applicant_name_furigana"
    ][
        "has_handwriting"
    ]

    results.append(
        {
            "name": "ご契約者氏名フリガナ",
            "status": "ok" if ok else "missing",
            "observed_value": "記入あり" if ok else "空欄",
            "reason": (
                "氏名フリガナ欄に記入があります。"
                if ok
                else "氏名フリガナ欄が空欄です。"
            )
        }
    )


    # -----------------------------------------------------
    # ご契約者住所
    # -----------------------------------------------------

    address = data["applicant_address"]

    prefecture = address[
        "written_prefecture"
    ].strip()

    prefecture_ok = prefecture in PREFECTURES

    address_ok = (
        address["address_has_handwriting"]
        and prefecture_ok
    )

    results.append(
        {
            "name": "ご契約者住所",
            "status": "ok" if address_ok else "missing",
            "observed_value": (
                f"都道府県：{prefecture}"
                if prefecture
                else "都道府県：確認できず"
            ),
            "reason": (
                "都道府県から住所が記入されています。"
                if address_ok
                else "ご住所は都道府県から記入する必要があります。"
            )
        }
    )


    # -----------------------------------------------------
    # 住所フリガナ
    # -----------------------------------------------------

    furigana_ok = address[
        "address_furigana_has_handwriting"
    ]

    results.append(
        {
            "name": "ご契約者住所フリガナ",
            "status": "ok" if furigana_ok else "missing",
            "observed_value": "記入あり" if furigana_ok else "空欄",
            "reason": (
                "住所用フリガナ欄に記入があります。"
                if furigana_ok
                else "住所用フリガナ欄に記入がありません。"
            )
        }
    )


    # -----------------------------------------------------
    # 雇用形態
    # -----------------------------------------------------

    emp = data["employment"]

    selected = []

    if emp["regular_employee_circled"]:
        selected.append("正社員")

    if emp["dispatch_employee_circled"]:
        selected.append("派遣社員")

    if emp["contract_employee_circled"]:
        selected.append("契約社員")

    if emp["part_time_circled"]:
        selected.append("パート・アルバイト")

    if emp["other_circled"]:
        selected.append("その他")


    if len(selected) == 1:

        status = "ok"
        reason = "雇用形態の選択を確認しました."

    elif len(selected) == 0:

        status = "missing"
        reason = "雇用形態の○を確認できません。"

    else:

        status = "warning"
        reason = "雇用形態が複数選択されています。"


    results.append(
        {
            "name": "雇用形態",
            "status": status,
            "observed_value": (
                "・".join(selected)
                if selected
                else "○なし"
            ),
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # 派遣先
    # -----------------------------------------------------

    if emp["dispatch_employee_circled"]:

        if emp["dispatch_company_has_handwriting"]:

            status = "ok"
            reason = "派遣社員のため、派遣先会社名を確認しました。"

        else:

            status = "missing"
            reason = "派遣社員ですが、派遣先・出向先の会社名が空欄です。"

    else:

        status = "not_applicable"
        reason = "派遣社員ではないため、この欄は対象外です。"


    results.append(
        {
            "name": "派遣先・出向先",
            "status": status,
            "observed_value": (
                "記入あり"
                if emp["dispatch_company_has_handwriting"]
                else "空欄"
            ),
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # 世帯主クレジット月額
    # -----------------------------------------------------

    household = data[
        "household_credit_monthly"
    ]

    amount_text = household[
        "written_amount"
    ]

    amount = None

    if household[
        "has_handwriting"
    ]:

        digits = re.sub(
            r"[^\d]",
            "",
            amount_text
        )

        if digits:
            amount = int(digits)


    if amount is None:

        status = "uncertain"
        reason = "月あたりのお支払額を確実に読み取れません。"

    elif amount > 100000:

        status = "warning"
        reason = "月あたりのお支払額が100,000円を超えています。"

    else:

        status = "ok"
        reason = "月あたりのお支払額は100,000円以下です。"


    results.append(
        {
            "name": "世帯主クレジット月額",
            "status": status,
            "observed_value": (
                f"{amount:,}円"
                if amount is not None
                else "読取不能"
            ),
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # 関係者情報
    # -----------------------------------------------------

    rel = data[
        "related_person"
    ]


    if not rel["applicable"]:

        relation_items = [
            {
                "name": "関係者情報",
                "status": "not_applicable",
                "observed_value": "",
                "reason": "関係者情報の記入対象外と判定しました。"
            }
        ]

    else:

        relation_items = []


        # 氏名
        ok = rel["name_has_handwriting"]

        relation_items.append(
            {
                "name": "関係者情報・氏名",
                "status": "ok" if ok else "missing",
                "observed_value": "記入あり" if ok else "空欄",
                "reason": (
                    "氏名欄に記入があります。"
                    if ok
                    else "関係者氏名が空欄です。"
                )
            }
        )


        # ご住所
        ok = rel["address_has_handwriting"]

        relation_items.append(
            {
                "name": "関係者情報・ご住所",
                "status": "ok" if ok else "missing",
                "observed_value": "記入あり" if ok else "空欄",
                "reason": (
                    "ご住所欄に記入があります。"
                    if ok
                    else "関係者情報のご住所欄が空欄です。"
                )
            }
        )


        # ご住居
        ok = rel[
            "residence_circle_present"
        ]

        relation_items.append(
            {
                "name": "関係者情報・ご住居",
                "status": "ok" if ok else "missing",
                "observed_value": "○あり" if ok else "○なし",
                "reason": (
                    "ご住居の選択を確認しました。"
                    if ok
                    else "ご住居の必要な選択に○がありません。"
                )
            }
        )


        # 所在地
        location_ok = (
            rel["location_has_handwriting"]
            or
            rel["location_is_same_as_above"]
        )

        relation_items.append(
            {
                "name": "関係者情報・所在地",
                "status": "ok" if location_ok else "missing",
                "observed_value": (
                    "同上"
                    if rel["location_is_same_as_above"]
                    else
                    "記入あり"
                    if rel["location_has_handwriting"]
                    else
                    "空欄"
                ),
                "reason": (
                    "所在地を確認しました。"
                    if location_ok
                    else "所在地が空欄です。"
                )
            }
        )


        # 郵便番号
        ok = rel[
            "postal_code_has_handwriting"
        ]

        relation_items.append(
            {
                "name": "関係者情報・郵便番号",
                "status": "ok" if ok else "missing",
                "observed_value": "記入あり" if ok else "空欄",
                "reason": (
                    "所在地の郵便番号を確認しました。"
                    if ok
                    else "所在地の郵便番号が空欄です。"
                )
            }
        )


        # 電話番号
        telephone_ok = (
            rel["telephone_has_handwriting"]
            or
            rel["mobile_has_handwriting"]
        )

        relation_items.append(
            {
                "name": "関係者情報・電話番号",
                "status": "ok" if telephone_ok else "missing",
                "observed_value": (
                    "固定電話あり"
                    if rel["telephone_has_handwriting"]
                    else
                    "携帯番号あり"
                    if rel["mobile_has_handwriting"]
                    else
                    "両方空欄"
                ),
                "reason": (
                    "固定電話または携帯番号を確認しました。"
                    if telephone_ok
                    else "固定電話・携帯番号の両方が空欄です。"
                )
            }
        )


        # その他の空欄
        if rel[
            "other_required_blank"
        ]:

            relation_items.append(
                {
                    "name": "関係者情報・その他必要項目",
                    "status": "missing",
                    "observed_value": "空欄あり",
                    "reason": "関係者情報内にその他の必要な空欄があります。"
                }
            )


        # その他の○
        if rel[
            "required_circle_missing"
        ]:

            relation_items.append(
                {
                    "name": "関係者情報・その他選択項目",
                    "status": "missing",
                    "observed_value": "○なし",
                    "reason": "関係者情報内の必要な選択に○がありません。"
                }
            )


    results.extend(
        relation_items
    )


    # -----------------------------------------------------
    # 銀行口座
    # -----------------------------------------------------

    bank = data[
        "bank_account"
    ]

    account_ok = (
        bank["yucho_has_handwriting"]
        or
        bank["other_bank_has_handwriting"]
    )

    results.append(
        {
            "name": "銀行口座",
            "status": "ok" if account_ok else "missing",
            "observed_value": (
                "ゆうちょ記入あり"
                if bank["yucho_has_handwriting"]
                else
                "ゆうちょ以外記入あり"
                if bank["other_bank_has_handwriting"]
                else
                "両方空欄"
            ),
            "reason": (
                "どちらか一方の銀行口座情報を確認しました。"
                if account_ok
                else "銀行口座情報が記入されていません。"
            )
        }
    )


    # -----------------------------------------------------
    # 口座名義人フリガナ
    # -----------------------------------------------------

    ok = bank[
        "account_name_furigana_has_handwriting"
    ]

    results.append(
        {
            "name": "口座名義人フリガナ",
            "status": "ok" if ok else "missing",
            "observed_value": "記入あり" if ok else "空欄",
            "reason": (
                "口座名義人フリガナを確認しました。"
                if ok
                else "口座名義人フリガナが空欄です。"
            )
        }
    )


    return results


# =========================================================
# 2枚目 Schema
# =========================================================

def page2_schema():

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "page2_read",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    "guardian_name": {
                        "type": "object",
                        "properties": {
                            "has_handwriting": {
                                "type": "boolean"
                            },
                            "furigana_has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "has_handwriting",
                            "furigana_has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "address": {
                        "type": "object",
                        "properties": {
                            "written_prefecture": {
                                "type": "string"
                            },
                            "circle_mark": {
                                "type": "string",
                                "enum": [
                                    "都",
                                    "道",
                                    "府",
                                    "県",
                                    "none",
                                    "uncertain"
                                ]
                            }
                        },
                        "required": [
                            "written_prefecture",
                            "circle_mark"
                        ],
                        "additionalProperties": False
                    },

                    "target_a": {
                        "type": "object",
                        "properties": {
                            "yes_is_circled": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "yes_is_circled"
                        ],
                        "additionalProperties": False
                    },

                    "school_type": {
                        "type": "object",
                        "properties": {
                            "public_circled": {
                                "type": "boolean"
                            },
                            "national_circled": {
                                "type": "boolean"
                            },
                            "private_circled": {
                                "type": "boolean"
                            },
                            "uncertain": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "public_circled",
                            "national_circled",
                            "private_circled",
                            "uncertain"
                        ],
                        "additionalProperties": False
                    },

                    "course_name": {
                        "type": "object",
                        "properties": {
                            "written_text": {
                                "type": "string"
                            },
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "written_text",
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "initial_instruction_date": {
                        "type": "object",
                        "properties": {
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "service_period_a": {
                        "type": "object",
                        "properties": {
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    },

                    "quantity": {
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
                                        "written_quantity": {
                                            "type": "string"
                                        },
                                        "quantity_box_has_handwriting": {
                                            "type": "boolean"
                                        }
                                    },
                                    "required": [
                                        "row_label",
                                        "horizontal_values",
                                        "written_quantity",
                                        "quantity_box_has_handwriting"
                                    ],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": [
                            "rows"
                        ],
                        "additionalProperties": False
                    },

                    "receipt_signature": {
                        "type": "object",
                        "properties": {
                            "written_text": {
                                "type": "string"
                            },
                            "has_handwriting": {
                                "type": "boolean"
                            }
                        },
                        "required": [
                            "written_text",
                            "has_handwriting"
                        ],
                        "additionalProperties": False
                    }
                },

                "required": [
                    "guardian_name",
                    "address",
                    "target_a",
                    "school_type",
                    "course_name",
                    "initial_instruction_date",
                    "service_period_a",
                    "quantity",
                    "receipt_signature"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 2枚目 AI読取
# =========================================================

def strict_read_page2(img):

    crops = create_page2_crops(img)

    content = [

        {
            "type": "text",
            "text": """
あなたは役務申込書の指定欄を
正確に読み取る担当です。

OK/NGは判断しません。

指定欄そのものに見える
手書き文字・数字・○だけを返してください。

別の欄の情報を代用してはいけません。

==================================================
住所
==================================================

「ご住所・連絡先」の住所欄を見る。

都道府県名が実際に書かれている場合だけ
written_prefecture に入れる。

神戸市と書かれているだけなら
兵庫県と推測しない。

また、

都
道
府
県

のどの文字に実際に○が付いているかを見る。


==================================================
指導対象A
==================================================

指導対象Aの

「有」

そのものに明確な○がある場合だけ
yes_is_circled = true。

近くの別の○を使わない。


==================================================
公・国・私
==================================================

公
国
私

の3文字そのものだけを見る。

それぞれに○があるかを確認する。

別の○を混同しない。


==================================================
コース名
==================================================

「コース名」の指定欄だけを見る。

必要なのは

週1 90分

という内容。

4回/月などの別欄を代用しない。


==================================================
初回指導日
==================================================

「初回指導日」欄そのものだけを見る。

別の日付を代用しない。


==================================================
役務提供期間
==================================================

A行だけを見る。

B行は判定しない。


==================================================
数量
==================================================

中央の商品表を行ごとに確認する。

同じ行の学年等の欄に

1
1
1

とあれば

horizontal_values = [1, 1, 1]

とする。

その同じ行の
「数量」列だけを見る。

数量欄が空欄なら

written_quantity = ""

quantity_box_has_handwriting = false。


各単価
小計
商品定価合計
税込価格
消費税
お申込合計

などの金額は絶対に数量として読まない。

648000
712800
108000
36000

などを数量として使わない。


==================================================
受領サイン
==================================================

ここは非常に重要。

2枚目右上の

「書面交付日」

の右側に印刷されている

「受領サイン →」

という文字の
さらに右側にある横長の署名欄だけを見る。

その欄に手書き文字がある場合だけ
has_handwriting = true。

それ以外の場所の氏名は
絶対に受領サインとして使わない。

特に、

保護者氏名
指導対象Aの氏名
申込者氏名
担当者氏名
販売担当者氏名

は受領サインではない。

この指定欄が空欄なら

written_text = ""

has_handwriting = false
"""
        },

        {
            "type": "text",
            "text": "以下は2枚目全体です。"
        },

        {
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(img),
                "detail": "high"
            }
        }
    ]


    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text": f"以下は【{name}】周辺です。"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": pil_to_data_url(crop),
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

        response_format=page2_schema()
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 都道府県の○
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


# =========================================================
# 2枚目 Python判定
# =========================================================

def page2_results(data):

    results = []


    # -----------------------------------------------------
    # 保護者氏名
    # -----------------------------------------------------

    guardian = data["guardian_name"]

    results.append(
        {
            "name": "保護者氏名",
            "status": (
                "ok"
                if guardian["has_handwriting"]
                else "missing"
            ),
            "observed_value": (
                "記入あり"
                if guardian["has_handwriting"]
                else "空欄"
            ),
            "reason": (
                "保護者氏名を確認しました。"
                if guardian["has_handwriting"]
                else "保護者氏名が空欄です。"
            )
        }
    )


    results.append(
        {
            "name": "保護者氏名フリガナ",
            "status": (
                "ok"
                if guardian[
                    "furigana_has_handwriting"
                ]
                else "missing"
            ),
            "observed_value": (
                "記入あり"
                if guardian[
                    "furigana_has_handwriting"
                ]
                else "空欄"
            ),
            "reason": (
                "保護者氏名フリガナを確認しました。"
                if guardian[
                    "furigana_has_handwriting"
                ]
                else
                "保護者氏名に対応するフリガナ欄が空欄です。"
            )
        }
    )


    # -----------------------------------------------------
    # 住所
    # -----------------------------------------------------

    address = data["address"]

    prefecture = address[
        "written_prefecture"
    ].strip()

    mark = address[
        "circle_mark"
    ]

    valid_prefecture = (
        prefecture in PREFECTURES
    )

    expected = (
        expected_prefecture_mark(prefecture)
        if valid_prefecture
        else None
    )


    if (
        valid_prefecture
        and mark == expected
    ):

        status = "ok"
        reason = "都道府県名と対応する○を確認しました。"

    elif not valid_prefecture:

        status = "missing"
        reason = "住所欄に都道府県名まで記入されていません。"

    elif mark in [
        "none",
        "uncertain"
    ]:

        status = "missing"
        reason = "都・道・府・県の対応箇所に○がありません。"

    else:

        status = "warning"
        reason = "都道府県と○の位置が一致していません。"


    results.append(
        {
            "name": "ご住所・連絡先",
            "status": status,
            "observed_value": (
                f"都道府県："
                f"{prefecture if prefecture else '確認できず'}"
                f" / ○：{mark}"
            ),
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # 指導対象A
    # -----------------------------------------------------

    ok = data[
        "target_a"
    ][
        "yes_is_circled"
    ]

    results.append(
        {
            "name": "指導対象A",
            "status": "ok" if ok else "missing",
            "observed_value": "有に○あり" if ok else "有に○なし",
            "reason": (
                "指導対象Aの「有」に○があります。"
                if ok
                else "指導対象Aの「有」に○がありません。"
            )
        }
    )


    # -----------------------------------------------------
    # 公・国・私
    # -----------------------------------------------------

    school = data[
        "school_type"
    ]

    if school["uncertain"]:

        status = "uncertain"
        observed = "判定不能"
        reason = "公・国・私の○を確実に判定できません。"

    else:

        selected = []

        if school["public_circled"]:
            selected.append("公")

        if school["national_circled"]:
            selected.append("国")

        if school["private_circled"]:
            selected.append("私")


        if len(selected) == 1:

            status = "ok"
            observed = selected[0]
            reason = "公・国・私のうち1つに○があります。"

        elif len(selected) == 0:

            status = "missing"
            observed = "○なし"
            reason = "公・国・私のいずれにも○がありません。"

        else:

            status = "warning"
            observed = "・".join(selected)
            reason = "公・国・私に複数の○があります。"


    results.append(
        {
            "name": "公・国・私",
            "status": status,
            "observed_value": observed,
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # コース名
    # -----------------------------------------------------

    course = data[
        "course_name"
    ]

    text = (
        course[
            "written_text"
        ]
        .replace(" ", "")
        .replace("　", "")
    )

    week_ok = (
        "週1" in text
        or "週１" in text
    )

    minute_ok = (
        "90分" in text
        or "９０分" in text
    )

    ok = (
        course["has_handwriting"]
        and week_ok
        and minute_ok
    )

    results.append(
        {
            "name": "コース名",
            "status": "ok" if ok else "missing",
            "observed_value": course["written_text"],
            "reason": (
                "コース名欄に「週1 90分」の記載があります。"
                if ok
                else "コース名欄に「週1 90分」の記載がありません。"
            )
        }
    )


    # -----------------------------------------------------
    # 初回指導日
    # -----------------------------------------------------

    ok = data[
        "initial_instruction_date"
    ][
        "has_handwriting"
    ]

    results.append(
        {
            "name": "初回指導日",
            "status": "ok" if ok else "missing",
            "observed_value": "記入あり" if ok else "空欄",
            "reason": (
                "初回指導日を確認しました。"
                if ok
                else "初回指導日が空欄です。"
            )
        }
    )


    # -----------------------------------------------------
    # 役務提供期間A
    # -----------------------------------------------------

    ok = data[
        "service_period_a"
    ][
        "has_handwriting"
    ]

    results.append(
        {
            "name": "役務提供期間A",
            "status": "ok" if ok else "missing",
            "observed_value": "記入あり" if ok else "空欄",
            "reason": (
                "役務提供期間Aを確認しました。"
                if ok
                else "役務提供期間Aが空欄です。"
            )
        }
    )


    # -----------------------------------------------------
    # 数量
    # -----------------------------------------------------

    rows = data[
        "quantity"
    ][
        "rows"
    ]

    row_results = []

    has_missing = False
    has_warning = False
    has_uncertain = False

    checked_rows = 0


    for row in rows:

        values = row[
            "horizontal_values"
        ]

        if not values:
            continue

        checked_rows += 1

        label = (
            row["row_label"].strip()
            or f"{checked_rows}行目"
        )

        expected_quantity = sum(
            values
        )

        written_text = row[
            "written_quantity"
        ].strip()

        written_number = None

        if written_text:

            match = re.search(
                r"\d+",
                written_text
            )

            if match:
                written_number = int(
                    match.group()
                )


        calculation = (
            " + ".join(
                str(v)
                for v in values
            )
            +
            f" = {expected_quantity}"
        )


        if not row[
            "quantity_box_has_handwriting"
        ]:

            has_missing = True

            row_results.append(
                f"{label}：{calculation}"
                " / 数量欄：空欄"
            )

        elif written_number is None:

            has_uncertain = True

            row_results.append(
                f"{label}：{calculation}"
                " / 数量欄：読取不能"
            )

        elif written_number != expected_quantity:

            has_warning = True

            row_results.append(
                f"{label}：{calculation}"
                f" / 数量欄：{written_number}"
            )

        else:

            row_results.append(
                f"{label}：{calculation}"
                f" / 数量欄：{written_number}"
            )


    if has_missing:

        status = "missing"
        reason = "横方向の数字合計に対して数量欄が空欄の行があります。"

    elif has_warning:

        status = "warning"
        reason = "横方向の数字合計と数量欄が一致しない行があります。"

    elif has_uncertain:

        status = "uncertain"
        reason = "数量欄を確実に読み取れない行があります。"

    elif checked_rows > 0:

        status = "ok"
        reason = "各行の合計と数量欄が一致しています。"

    else:

        status = "uncertain"
        reason = "数量判定対象の行を確認できませんでした。"


    results.append(
        {
            "name": "数量",
            "status": status,
            "observed_value": " / ".join(row_results),
            "reason": reason
        }
    )


    # -----------------------------------------------------
    # 受領サイン
    # -----------------------------------------------------

    sign = data[
        "receipt_signature"
    ]

    ok = sign[
        "has_handwriting"
    ]

    results.append(
        {
            "name": "受領サイン",
            "status": "ok" if ok else "missing",
            "observed_value": (
                "記入あり"
                if ok
                else "空欄"
            ),
            "reason": (
                "右上の「受領サイン →」直後の欄に記入があります。"
                if ok
                else
                "右上の「受領サイン →」直後の欄が空欄です。"
            )
        }
    )


    return results


# =========================================================
# 表示
# =========================================================

def display_item(item):

    status = item[
        "status"
    ]

    if status == "ok":

        icon = "✅"
        label = "問題なし"

    elif status == "missing":

        icon = "❌"
        label = "記入漏れ"

    elif status == "warning":

        icon = "⚠️"
        label = "要注意"

    elif status == "not_applicable":

        icon = "➖"
        label = "対象外"

    else:

        icon = "🔍"
        label = "要確認"


    with st.container(
        border=True
    ):

        st.markdown(
            f"### {icon} "
            f"{item['name']}：{label}"
        )

        if item.get(
            "observed_value"
        ):

            st.write(
                "読み取った内容："
                f"**{item['observed_value']}**"
            )

        st.caption(
            item.get(
                "reason",
                ""
            )
        )


# =========================================================
# アップロード
# =========================================================

st.divider()

st.markdown(
    "## 📷 契約書の写真を選択"
)


st.markdown(
    "### ① クレジット申込書"
)

file1 = st.file_uploader(
    "1枚目の写真を選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    key="page1"
)


st.markdown(
    "### ② 役務申込書・指導内容"
)

file2 = st.file_uploader(
    "2枚目の写真を選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    key="page2"
)


st.caption(
    "書類全体が入るように、"
    "できるだけ真上から撮影してください。"
)


# =========================================================
# チェック
# =========================================================

if st.button(
    "🤖 AIでチェックする",
    type="primary",
    use_container_width=True
):

    if not file1 and not file2:

        st.error(
            "写真を1枚以上選択してください。"
        )

    else:

        try:

            total_missing = 0
            total_warning = 0
            total_uncertain = 0


            # =================================================
            # 1枚目
            # =================================================

            if file1:

                img1 = prepare_image(
                    file1
                )

                with st.spinner(
                    "1枚目を確認しています…"
                ):

                    data1 = strict_read_page1(
                        img1
                    )

                    results1 = page1_results(
                        data1
                    )


                st.divider()

                st.subheader(
                    "① クレジット申込書"
                )

                st.image(
                    img1,
                    use_container_width=True
                )


                for item in results1:

                    display_item(
                        item
                    )

                    if item["status"] == "missing":
                        total_missing += 1

                    elif item["status"] == "warning":
                        total_warning += 1

                    elif item["status"] == "uncertain":
                        total_uncertain += 1


            # =================================================
            # 2枚目
            # =================================================

            if file2:

                img2 = prepare_image(
                    file2
                )

                with st.spinner(
                    "2枚目を確認しています…"
                ):

                    data2 = strict_read_page2(
                        img2
                    )

                    results2 = page2_results(
                        data2
                    )


                st.divider()

                st.subheader(
                    "② 役務申込書・指導内容"
                )

                st.image(
                    img2,
                    use_container_width=True
                )


                for item in results2:

                    display_item(
                        item
                    )

                    if item["status"] == "missing":
                        total_missing += 1

                    elif item["status"] == "warning":
                        total_warning += 1

                    elif item["status"] == "uncertain":
                        total_uncertain += 1


            # =================================================
            # 結果まとめ
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

                    st.warning(
                        f"🔍 要確認："
                        f"{total_uncertain}件"
                    )

                st.info(
                    "該当箇所を人の目でも確認してください。"
                )


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
