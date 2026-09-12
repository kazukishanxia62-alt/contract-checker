import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
import re
from openai import OpenAI

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


def enlarge_image(
    img,
    min_long_side=2200
):
    long_side = max(img.size)

    if long_side >= min_long_side:
        return img

    scale = min_long_side / long_side

    return img.resize(
        (
            int(img.width * scale),
            int(img.height * scale)
        ),
        Image.Resampling.LANCZOS
    )


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

    return (
        "data:image/jpeg;base64,"
        + encoded
    )


# =========================================================
# 1枚目
# 自動分割＋拡大
# =========================================================

def create_page1_crops(img):

    return {

        "上半分":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.00,
                    1.00,
                    0.55
                )
            ),

        "下半分":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.45,
                    1.00,
                    1.00
                )
            ),

        "契約者氏名・住所・住所フリガナ":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.05,
                    0.58,
                    0.34
                ),
                2400
            ),

        "勤務先・雇用形態・派遣先":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.24,
                    0.70,
                    0.50
                ),
                2400
            ),

        "世帯主・世帯状況":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.43,
                    0.72,
                    0.64
                ),
                2400
            ),

        "関係者情報":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.51,
                    0.58,
                    0.84
                ),
                2600
            ),

        "銀行口座":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.76,
                    0.58,
                    1.00
                ),
                2400
            ),
    }


# =========================================================
# 2枚目
# 自動分割＋拡大
# =========================================================

def create_page2_crops(img):

    return {

        "上半分":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.00,
                    1.00,
                    0.58
                )
            ),

        "下半分":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.42,
                    1.00,
                    1.00
                )
            ),

        "住所・保護者氏名":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.03,
                    0.58,
                    0.34
                ),
                2400
            ),

        "指導対象A・公国私":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.40,
                    0.03,
                    1.00,
                    0.36
                ),
                2400
            ),

        "コース名":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.00,
                    0.28,
                    0.52,
                    0.70
                ),
                2400
            ),

        "数量表":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.34,
                    0.30,
                    0.67,
                    0.72
                ),
                2600
            ),

        "受領サイン":
            enlarge_image(
                crop_by_ratio(
                    img,
                    0.58,
                    0.12,
                    1.00,
                    0.30
                ),
                2400
            ),
    }


# =========================================================
# 1枚目 JSON Schema
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

                    "applicant_name": {

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


                    "applicant_address": {

                        "type": "object",

                        "properties": {

                            "address_has_handwriting": {
                                "type": "boolean"
                            },

                            "written_prefecture": {
                                "type": "string"
                            },

                            "address_furigana_has_handwriting": {
                                "type": "boolean"
                            }

                        },

                        "required": [
                            "address_has_handwriting",
                            "written_prefecture",
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

                            "uncertain": {
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
                            "uncertain",
                            "dispatch_company_has_handwriting"
                        ],

                        "additionalProperties": False
                    },


                    "household_credit_monthly": {

                        "type": "object",

                        "properties": {

                            "has_handwriting": {
                                "type": "boolean"
                            },

                            "written_amount": {
                                "type": "string"
                            },

                            "uncertain": {
                                "type": "boolean"
                            }

                        },

                        "required": [
                            "has_handwriting",
                            "written_amount",
                            "uncertain"
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
                    "applicant_name",
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
あなたはクレジット契約書の
「記入状態だけ」を読み取る担当です。

OK・NGは判断しないでください。

全体画像は位置確認に使い、
細かい文字や○の判定は、
後から与える拡大画像を優先してください。


==================================================
最重要
==================================================

・印刷文字を手書きとして扱わない。

・別の欄の住所、氏名、電話番号、数字、
  ○を流用しない。

・空欄なら空欄。

・分からない場合は推測しない。

・雇用形態などが拡大画像でも
  判別しづらい場合は uncertain=true。


==================================================
契約者住所
==================================================

ご契約者本人の
「ご住所」欄そのものを見る。

住所に実際の手書きがあれば

address_has_handwriting=true。


住所の先頭付近に

北海道
東京都
大阪府
京都府
兵庫県
など、

都道府県名が実際に書かれている場合だけ、

written_prefecture

にその文字列を入れる。


市区町村から推測禁止。

例：

「神戸市灘区〜」

しか見えなければ、

written_prefecture=""

にする。


==================================================
住所フリガナ
==================================================

住所に対応している
住所用フリガナ欄そのものを見る。

そこに手書きのカタカナ等があれば

address_furigana_has_handwriting=true。


氏名フリガナを
住所フリガナとして使わない。


==================================================
雇用形態
==================================================

雇用形態欄だけを見る。

各選択肢の文字そのものに、

手書きの○
囲み
明確な選択印

があるかを確認する。


正社員

派遣社員

契約社員

パート・アルバイト

その他

をそれぞれ別に見る。


近くの○を誤認しない。

印刷された丸や枠線は
○として扱わない。


拡大画像を見ても
どの選択肢か確信できない場合は

uncertain=true。


==================================================
派遣先・出向先
==================================================

「派遣先・出向先」

の会社名記入欄そのものを見る。

別の会社名を代用しない。


==================================================
世帯主クレジット月額
==================================================

必ず、

「世帯主のクレジットの
月あたりのお支払額」

と印刷された欄そのものを見る。


近くにある

世帯主の年収(税込)

税込年収

などの金額は絶対に使わない。


月額欄が読めない場合は

uncertain=true。


==================================================
関係者情報
==================================================

下側の「関係者情報」欄だけを見る。


以下を別々に見る。

・氏名

・ご住所

・ご住居の○

・所在地

・所在地内の郵便番号

・所在地内の電話番号

・携帯番号


所在地は

実住所

または

「同上」

なら記入あり。


ただし、

所在地が「同上」でも
郵便番号は別に確認する。


電話番号については、

固定電話が空欄でも
携帯番号があれば可。


==================================================
銀行口座
==================================================

ゆうちょ銀行

または

ゆうちょ銀行以外

のどちらかに
記入があるかを見る。


口座名義人フリガナは
その指定欄だけを見る。
"""
        },


        {
            "type": "text",
            "text":
                "以下は1枚目全体です。"
                "位置確認だけに使ってください。"
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

                "text":
                    f"以下は【{name}】の拡大画像です。"
                    "細かい文字や○はこちらを優先してください。"
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
    # 契約者氏名フリガナ
    # -----------------------------------------------------

    applicant = data[
        "applicant_name"
    ]

    ok = applicant[
        "furigana_has_handwriting"
    ]

    results.append(
        {
            "name":
                "ご契約者氏名フリガナ",

            "status":
                "ok" if ok else "missing",

            "observed_value":
                "記入あり"
                if ok
                else "空欄",

            "reason":
                "氏名フリガナ欄そのものを確認しました。"
        }
    )


    # -----------------------------------------------------
    # 契約者住所
    # -----------------------------------------------------

    address = data[
        "applicant_address"
    ]

    prefecture = address[
        "written_prefecture"
    ].strip()

    address_ok = (
        address[
            "address_has_handwriting"
        ]
        and
        prefecture in PREFECTURES
    )


    results.append(
        {
            "name":
                "ご契約者住所",

            "status":
                "ok"
                if address_ok
                else "missing",

            "observed_value":
                (
                    f"都道府県：{prefecture}"
                    if prefecture
                    else
                    "都道府県：確認できず"
                ),

            "reason":
                "都道府県から記入されているかを確認しました。"
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
            "name":
                "ご契約者住所フリガナ",

            "status":
                "ok"
                if furigana_ok
                else "missing",

            "observed_value":
                (
                    "記入あり"
                    if furigana_ok
                    else "空欄"
                ),

            "reason":
                "住所用フリガナ欄そのものを確認しました。"
        }
    )


    # -----------------------------------------------------
    # 雇用形態
    # -----------------------------------------------------

    emp = data[
        "employment"
    ]

    selected = []


    if emp[
        "regular_employee_circled"
    ]:
        selected.append(
            "正社員"
        )


    if emp[
        "dispatch_employee_circled"
    ]:
        selected.append(
            "派遣社員"
        )


    if emp[
        "contract_employee_circled"
    ]:
        selected.append(
            "契約社員"
        )


    if emp[
        "part_time_circled"
    ]:
        selected.append(
            "パート・アルバイト"
        )


    if emp[
        "other_circled"
    ]:
        selected.append(
            "その他"
        )


    if emp[
        "uncertain"
    ]:

        emp_status = "uncertain"

        emp_reason = (
            "雇用形態の○を"
            "拡大画像でも確実に判別できません。"
        )


    elif len(
        selected
    ) == 1:

        emp_status = "ok"

        emp_reason = (
            "雇用形態の選択を確認しました。"
        )


    elif len(
        selected
    ) == 0:

        emp_status = "missing"

        emp_reason = (
            "雇用形態の○を確認できません。"
        )


    else:

        emp_status = "warning"

        emp_reason = (
            "雇用形態が複数選択されています。"
        )


    results.append(
        {
            "name":
                "雇用形態",

            "status":
                emp_status,

            "observed_value":
                (
                    "・".join(selected)
                    if selected
                    else "○なし"
                ),

            "reason":
                emp_reason
        }
    )


    # -----------------------------------------------------
    # 派遣先
    # -----------------------------------------------------

    if emp[
        "dispatch_employee_circled"
    ]:

        dispatch_ok = emp[
            "dispatch_company_has_handwriting"
        ]


        results.append(
            {
                "name":
                    "派遣先・出向先",

                "status":
                    (
                        "ok"
                        if dispatch_ok
                        else "missing"
                    ),

                "observed_value":
                    (
                        "記入あり"
                        if dispatch_ok
                        else "空欄"
                    ),

                "reason":
                    "派遣社員の場合のみ必須です。"
            }
        )


    else:

        results.append(
            {
                "name":
                    "派遣先・出向先",

                "status":
                    "not_applicable",

                "observed_value":
                    (
                        "空欄"
                        if not emp[
                            "dispatch_company_has_handwriting"
                        ]
                        else "記入あり"
                    ),

                "reason":
                    "派遣社員ではないため対象外です。"
            }
        )


    # -----------------------------------------------------
    # 世帯主クレジット月額
    # -----------------------------------------------------

    household = data[
        "household_credit_monthly"
    ]


    if (
        household[
            "uncertain"
        ]
        or
        not household[
            "has_handwriting"
        ]
    ):

        amount = None


    else:

        digits = re.sub(
            r"[^\d]",
            "",
            household[
                "written_amount"
            ]
        )

        amount = (
            int(digits)
            if digits
            else None
        )


    if amount is None:

        status = "uncertain"

        reason = (
            "月あたりのお支払額を"
            "確実に読み取れません。"
        )


    elif amount > 100000:

        status = "warning"

        reason = (
            "月あたりのお支払額が"
            "100,000円を超えています。"
        )


    else:

        status = "ok"

        reason = (
            "月あたりのお支払額は"
            "100,000円以下です。"
        )


    results.append(
        {
            "name":
                "世帯主クレジット月額",

            "status":
                status,

            "observed_value":
                (
                    f"{amount:,}円"
                    if amount is not None
                    else "読取不能"
                ),

            "reason":
                reason
        }
    )


    # -----------------------------------------------------
    # 関係者情報
    # -----------------------------------------------------

    rel = data[
        "related_person"
    ]


    if not rel[
        "applicable"
    ]:

        results.append(
            {
                "name":
                    "関係者情報",

                "status":
                    "not_applicable",

                "observed_value":
                    "",

                "reason":
                    "関係者情報の対象外です。"
            }
        )


    else:

        checks = [

            (
                "関係者情報・氏名",
                rel[
                    "name_has_handwriting"
                ],
                "記入あり",
                "空欄"
            ),

            (
                "関係者情報・ご住所",
                rel[
                    "address_has_handwriting"
                ],
                "記入あり",
                "空欄"
            ),

            (
                "関係者情報・ご住居",
                rel[
                    "residence_circle_present"
                ],
                "○あり",
                "○なし"
            ),

            (
                "関係者情報・郵便番号",
                rel[
                    "postal_code_has_handwriting"
                ],
                "記入あり",
                "空欄"
            )

        ]


        for (
            name,
            ok,
            yes_text,
            no_text
        ) in checks:

            results.append(
                {
                    "name":
                        name,

                    "status":
                        (
                            "ok"
                            if ok
                            else "missing"
                        ),

                    "observed_value":
                        (
                            yes_text
                            if ok
                            else no_text
                        ),

                    "reason":
                        "指定欄そのものを確認しました。"
                }
            )


        location_ok = (
            rel[
                "location_has_handwriting"
            ]
            or
            rel[
                "location_is_same_as_above"
            ]
        )


        results.append(
            {
                "name":
                    "関係者情報・所在地",

                "status":
                    (
                        "ok"
                        if location_ok
                        else "missing"
                    ),

                "observed_value":
                    (
                        "同上"
                        if rel[
                            "location_is_same_as_above"
                        ]
                        else
                        "記入あり"
                        if rel[
                            "location_has_handwriting"
                        ]
                        else
                        "空欄"
                    ),

                "reason":
                    "所在地は実住所または『同上』なら可です。"
            }
        )


        contact_ok = (
            rel[
                "telephone_has_handwriting"
            ]
            or
            rel[
                "mobile_has_handwriting"
            ]
        )


        results.append(
            {
                "name":
                    "関係者情報・電話番号",

                "status":
                    (
                        "ok"
                        if contact_ok
                        else "missing"
                    ),

                "observed_value":
                    (
                        "固定電話あり"
                        if rel[
                            "telephone_has_handwriting"
                        ]
                        else
                        "携帯番号あり"
                        if rel[
                            "mobile_has_handwriting"
                        ]
                        else
                        "両方空欄"
                    ),

                "reason":
                    (
                        "携帯番号があれば"
                        "固定電話は空欄でも可です。"
                    )
            }
        )


        if rel[
            "other_required_blank"
        ]:

            results.append(
                {
                    "name":
                        "関係者情報・その他必要項目",

                    "status":
                        "missing",

                    "observed_value":
                        "空欄あり",

                    "reason":
                        "その他の必須欄に空欄があります。"
                }
            )


        if rel[
            "required_circle_missing"
        ]:

            results.append(
                {
                    "name":
                        "関係者情報・その他選択項目",

                    "status":
                        "missing",

                    "observed_value":
                        "○なし",

                    "reason":
                        "必要な選択項目に○がありません。"
                }
            )


    # -----------------------------------------------------
    # 銀行口座
    # -----------------------------------------------------

    bank = data[
        "bank_account"
    ]

    account_ok = (
        bank[
            "yucho_has_handwriting"
        ]
        or
        bank[
            "other_bank_has_handwriting"
        ]
    )


    results.append(
        {
            "name":
                "銀行口座",

            "status":
                (
                    "ok"
                    if account_ok
                    else "missing"
                ),

            "observed_value":
                (
                    "記入あり"
                    if account_ok
                    else "両方空欄"
                ),

            "reason":
                (
                    "ゆうちょ銀行または"
                    "ゆうちょ以外のどちらか一方で可です。"
                )
        }
    )


    results.append(
        {
            "name":
                "口座名義人フリガナ",

            "status":
                (
                    "ok"
                    if bank[
                        "account_name_furigana_has_handwriting"
                    ]
                    else "missing"
                ),

            "observed_value":
                (
                    "記入あり"
                    if bank[
                        "account_name_furigana_has_handwriting"
                    ]
                    else "空欄"
                ),

            "reason":
                "口座名義人フリガナ欄を確認しました。"
        }
    )


    return results


# =========================================================
# 2枚目 Schema
# =========================================================

def page2_schema():

    return {

        "type":
            "json_schema",

        "json_schema": {

            "name":
                "page2_read",

            "strict":
                True,

            "schema": {

                "type":
                    "object",

                "properties": {

                    "guardian_name": {

                        "type":
                            "object",

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

                        "additionalProperties":
                            False
                    },


                    "address": {

                        "type":
                            "object",

                        "properties": {

                            "written_prefecture": {
                                "type": "string"
                            },

                            "circle_mark": {

                                "type":
                                    "string",

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

                        "additionalProperties":
                            False
                    },


                    "target_a": {

                        "type":
                            "object",

                        "properties": {

                            "yes_is_circled": {
                                "type": "boolean"
                            }

                        },

                        "required": [
                            "yes_is_circled"
                        ],

                        "additionalProperties":
                            False
                    },


                    "school_type": {

                        "type":
                            "object",

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

                        "additionalProperties":
                            False
                    },


                    "course_name": {

                        "type":
                            "object",

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

                        "additionalProperties":
                            False
                    },


                    "quantity": {

                        "type":
                            "object",

                        "properties": {

                            "rows": {

                                "type":
                                    "array",

                                "items": {

                                    "type":
                                        "object",

                                    "properties": {

                                        "row_label": {
                                            "type": "string"
                                        },

                                        "horizontal_values": {

                                            "type":
                                                "array",

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

                                    "additionalProperties":
                                        False

                                }

                            }

                        },

                        "required": [
                            "rows"
                        ],

                        "additionalProperties":
                            False
                    },


                    "receipt_signature": {

                        "type":
                            "object",

                        "properties": {

                            "has_handwriting": {
                                "type": "boolean"
                            },

                            "written_text": {
                                "type": "string"
                            }

                        },

                        "required": [
                            "has_handwriting",
                            "written_text"
                        ],

                        "additionalProperties":
                            False
                    }

                },

                "required": [
                    "guardian_name",
                    "address",
                    "target_a",
                    "school_type",
                    "course_name",
                    "quantity",
                    "receipt_signature"
                ],

                "additionalProperties":
                    False

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
            "type":
                "text",

            "text": """
あなたは役務申込書の
記入状態を読み取る担当です。

OK・NGは判断せず、
指定欄そのものの事実だけを返してください。

全体画像は位置確認に使い、
細かい文字や○は
拡大画像を優先してください。


【住所】

都道府県名が実際に
書かれている場合だけ

written_prefecture

に入れる。

市区町村から推測しない。


都
道
府
県

の○は、
その文字そのものの○だけを見る。


【指導対象A】

「有」

そのものに
明確な○がある場合だけ true。


【公・国・私】

公
国
私

の3文字そのものだけを見る。


【コース名】

指定のコース名欄だけを見る。

必要なのは

週1 90分

の記載。

4回/月など別欄を代用しない。


【数量】

印刷された見出し

「数量」

を探す。

その見出しの
真下の列だけを
数量欄として扱う。


数量列より右側の

各単価

小計

商品定価合計

消費税

税込価格

申込合計額

などの金額を
絶対に数量として使わない。


各商品行について、

横方向の手書き数字を

horizontal_values

に入れる。


その同じ行の
数量欄だけを

written_quantity

に入れる。


数量欄が空欄なら

written_quantity=""

quantity_box_has_handwriting=false。


【受領サイン】

右上の

「書面交付日」

の右にある

「受領サイン →」

の直後の横長欄だけを見る。


他の氏名は絶対に使わない。


その欄が空欄なら

has_handwriting=false。
"""
        },


        {
            "type":
                "text",

            "text":
                "以下は2枚目全体です。"
        },


        {
            "type":
                "image_url",

            "image_url": {

                "url":
                    pil_to_data_url(img),

                "detail":
                    "high"
            }
        }

    ]


    for name, crop in crops.items():

        content.append(
            {
                "type":
                    "text",

                "text":
                    f"以下は【{name}】の拡大画像です。"
            }
        )

        content.append(
            {
                "type":
                    "image_url",

                "image_url": {

                    "url":
                        pil_to_data_url(crop),

                    "detail":
                        "high"
                }
            }
        )


    response = client.chat.completions.create(

        model=MODEL,

        messages=[
            {
                "role":
                    "user",

                "content":
                    content
            }
        ],

        response_format=
            page2_schema()

    )


    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 都道府県○
# =========================================================

def expected_prefecture_mark(
    prefecture
):

    if prefecture == "東京都":
        return "都"

    if prefecture == "北海道":
        return "道"

    if prefecture in [
        "大阪府",
        "京都府"
    ]:
        return "府"

    if prefecture.endswith(
        "県"
    ):
        return "県"

    return None


# =========================================================
# 2枚目 Python判定
# =========================================================

def page2_results(data):

    results = []


    guardian = data[
        "guardian_name"
    ]


    results.append(
        {
            "name":
                "保護者氏名フリガナ",

            "status":
                (
                    "ok"
                    if guardian[
                        "furigana_has_handwriting"
                    ]
                    else "missing"
                ),

            "observed_value":
                (
                    "記入あり"
                    if guardian[
                        "furigana_has_handwriting"
                    ]
                    else "空欄"
                ),

            "reason":
                (
                    "保護者氏名に対応する"
                    "フリガナ欄を確認しました。"
                )
        }
    )


    # -----------------------------------------------------
    # 住所
    # -----------------------------------------------------

    address = data[
        "address"
    ]

    pref = address[
        "written_prefecture"
    ].strip()

    mark = address[
        "circle_mark"
    ]

    valid_pref = (
        pref in PREFECTURES
    )

    expected = (
        expected_prefecture_mark(
            pref
        )
        if valid_pref
        else None
    )


    if (
        valid_pref
        and
        mark == expected
    ):

        status = "ok"

        reason = (
            "都道府県名と"
            "対応する○を確認しました。"
        )


    elif not valid_pref:

        status = "missing"

        reason = (
            "住所欄に都道府県名まで"
            "記入されていません。"
        )


    elif mark == "none":

        status = "missing"

        reason = (
            "都・道・府・県の"
            "○を確認できません。"
        )


    elif mark == "uncertain":

        status = "uncertain"

        reason = (
            "都・道・府・県の○を"
            "確実に判定できません。"
        )


    else:

        status = "warning"

        reason = (
            "都道府県と○の位置が"
            "一致していません。"
        )


    results.append(
        {
            "name":
                "ご住所・連絡先",

            "status":
                status,

            "observed_value":
                (
                    f"都道府県："
                    f"{pref if pref else '確認できず'}"
                    f" / ○：{mark}"
                ),

            "reason":
                reason
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
            "name":
                "指導対象A",

            "status":
                (
                    "ok"
                    if ok
                    else "missing"
                ),

            "observed_value":
                (
                    "有に○あり"
                    if ok
                    else "有に○なし"
                ),

            "reason":
                (
                    "指導対象Aの"
                    "『有』そのものを確認しました。"
                )
        }
    )


    # -----------------------------------------------------
    # 公・国・私
    # -----------------------------------------------------

    school = data[
        "school_type"
    ]


    if school[
        "uncertain"
    ]:

        school_status = (
            "uncertain"
        )

        observed = (
            "判定不能"
        )

        reason = (
            "公・国・私の○を"
            "確実に判定できません。"
        )


    else:

        selected = []


        if school[
            "public_circled"
        ]:
            selected.append(
                "公"
            )


        if school[
            "national_circled"
        ]:
            selected.append(
                "国"
            )


        if school[
            "private_circled"
        ]:
            selected.append(
                "私"
            )


        if len(
            selected
        ) == 1:

            school_status = (
                "ok"
            )

            observed = (
                selected[0]
            )

            reason = (
                "公・国・私のうち"
                "1つに○があります。"
            )


        elif len(
            selected
        ) == 0:

            school_status = (
                "missing"
            )

            observed = (
                "○なし"
            )

            reason = (
                "公・国・私のいずれにも"
                "○がありません。"
            )


        else:

            school_status = (
                "warning"
            )

            observed = (
                "・".join(
                    selected
                )
            )

            reason = (
                "公・国・私に"
                "複数の○があります。"
            )


    results.append(
        {
            "name":
                "公・国・私",

            "status":
                school_status,

            "observed_value":
                observed,

            "reason":
                reason
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
        .replace(
            " ",
            ""
        )
        .replace(
            "　",
            ""
        )
    )


    course_ok = (
        course[
            "has_handwriting"
        ]
        and
        (
            "週1"
            in text
            or
            "週１"
            in text
        )
        and
        (
            "90分"
            in text
            or
            "９０分"
            in text
        )
    )


    results.append(
        {
            "name":
                "コース名",

            "status":
                (
                    "ok"
                    if course_ok
                    else "missing"
                ),

            "observed_value":
                (
                    course[
                        "written_text"
                    ]
                    if course[
                        "written_text"
                    ]
                    else "空欄"
                ),

            "reason":
                (
                    "コース名欄に"
                    "『週1 90分』があるか確認しました。"
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

    checked = 0


    for row in rows:

        values = row[
            "horizontal_values"
        ]

        if not values:
            continue


        checked += 1


        expected_q = sum(
            values
        )


        label = (
            row[
                "row_label"
            ].strip()
            or
            f"{checked}行目"
        )


        text_q = row[
            "written_quantity"
        ].strip()


        match = re.search(
            r"\d+",
            text_q
        )


        written_q = (
            int(
                match.group()
            )
            if match
            else None
        )


        calc = (
            " + ".join(
                str(v)
                for v in values
            )
            +
            f" = {expected_q}"
        )


        if not row[
            "quantity_box_has_handwriting"
        ]:

            has_missing = True

            row_results.append(
                f"{label}："
                f"{calc}"
                " / 数量欄：空欄"
            )


        elif written_q is None:

            has_uncertain = True

            row_results.append(
                f"{label}："
                f"{calc}"
                " / 数量欄：読取不能"
            )


        elif written_q >= 1000:

            has_uncertain = True

            row_results.append(
                f"{label}："
                f"{calc}"
                f" / 数量欄：{written_q}"
                "（金額誤読の可能性）"
            )


        elif written_q != expected_q:

            has_warning = True

            row_results.append(
                f"{label}："
                f"{calc}"
                f" / 数量欄：{written_q}"
            )


        else:

            row_results.append(
                f"{label}："
                f"{calc}"
                f" / 数量欄：{written_q}"
            )


    if has_missing:

        q_status = (
            "missing"
        )

        q_reason = (
            "数量欄が空欄の"
            "行があります。"
        )


    elif has_warning:

        q_status = (
            "warning"
        )

        q_reason = (
            "横方向の合計と"
            "数量欄が一致しない"
            "行があります。"
        )


    elif has_uncertain:

        q_status = (
            "uncertain"
        )

        q_reason = (
            "数量欄を確実に"
            "読み取れない行があります。"
        )


    elif checked > 0:

        q_status = (
            "ok"
        )

        q_reason = (
            "各行の合計と"
            "数量欄が一致しています。"
        )


    else:

        q_status = (
            "uncertain"
        )

        q_reason = (
            "数量判定対象の行を"
            "確認できませんでした。"
        )


    results.append(
        {
            "name":
                "数量",

            "status":
                q_status,

            "observed_value":
                (
                    " / ".join(
                        row_results
                    )
                    if row_results
                    else
                    "対象行を確認できず"
                ),

            "reason":
                q_reason
        }
    )


    # -----------------------------------------------------
    # 受領サイン
    # -----------------------------------------------------

    sign = data[
        "receipt_signature"
    ]


    results.append(
        {
            "name":
                "受領サイン",

            "status":
                (
                    "ok"
                    if sign[
                        "has_handwriting"
                    ]
                    else "missing"
                ),

            "observed_value":
                (
                    "記入あり"
                    if sign[
                        "has_handwriting"
                    ]
                    else "空欄"
                ),

            "reason":
                (
                    "右上の"
                    "『受領サイン →』"
                    "直後の欄だけを確認しました。"
                )
        }
    )


    return results


# =========================================================
# 表示
# =========================================================

def display_item(item):

    mapping = {

        "ok":
            (
                "✅",
                "問題なし"
            ),

        "missing":
            (
                "❌",
                "記入漏れ"
            ),

        "warning":
            (
                "⚠️",
                "要注意"
            ),

        "not_applicable":
            (
                "➖",
                "対象外"
            ),

        "uncertain":
            (
                "🔍",
                "要確認"
            )

    }


    icon, label = mapping.get(
        item[
            "status"
        ],
        (
            "🔍",
            "要確認"
        )
    )


    with st.container(
        border=True
    ):

        st.markdown(
            f"### {icon} "
            f"{item['name']}："
            f"{label}"
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
# ファイル選択
# =========================================================

st.divider()

st.markdown(
    "## 📷 契約書の写真を選択"
)


file1 = st.file_uploader(
    "① クレジット申込書",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    key="page1"
)


file2 = st.file_uploader(
    "② 役務申込書・指導内容",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    key="page2"
)


st.caption(
    "写真は1枚のままでOKです。"
    "アプリ側で自動的に上下分割・"
    "重要箇所の拡大を行います。"
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
                    "1枚目を自動分割・"
                    "拡大して確認しています…"
                ):

                    data1 = (
                        strict_read_page1(
                            img1
                        )
                    )

                    results1 = (
                        page1_results(
                            data1
                        )
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


                    if (
                        item[
                            "status"
                        ]
                        == "missing"
                    ):

                        total_missing += 1


                    elif (
                        item[
                            "status"
                        ]
                        == "warning"
                    ):

                        total_warning += 1


                    elif (
                        item[
                            "status"
                        ]
                        == "uncertain"
                    ):

                        total_uncertain += 1


            # =================================================
            # 2枚目
            # =================================================

            if file2:

                img2 = prepare_image(
                    file2
                )


                with st.spinner(
                    "2枚目を自動分割・"
                    "拡大して確認しています…"
                ):

                    data2 = (
                        strict_read_page2(
                            img2
                        )
                    )

                    results2 = (
                        page2_results(
                            data2
                        )
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


                    if (
                        item[
                            "status"
                        ]
                        == "missing"
                    ):

                        total_missing += 1


                    elif (
                        item[
                            "status"
                        ]
                        == "warning"
                    ):

                        total_warning += 1


                    elif (
                        item[
                            "status"
                        ]
                        == "uncertain"
                    ):

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
                    "✅ 現在のチェック項目では"
                    "問題は見つかりませんでした。"
                )


            else:

                if total_missing:

                    st.error(
                        f"❌ 記入漏れ："
                        f"{total_missing}件"
                    )


                if total_warning:

                    st.warning(
                        f"⚠️ 要注意："
                        f"{total_warning}件"
                    )


                if total_uncertain:

                    st.warning(
                        f"🔍 要確認："
                        f"{total_uncertain}件"
                    )


                st.info(
                    "該当箇所を人の目でも"
                    "確認してください。"
                )


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
