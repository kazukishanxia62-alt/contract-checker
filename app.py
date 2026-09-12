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
    "記入漏れ・条件違反・要注意項目をチェックします。"
)

st.warning(
    "これは提出前の補助チェック用です。"
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
    st.error(
        "OPENAI_API_KEY が設定されていません。"
    )
    st.stop()


MODEL = "gpt-5.4-mini"


# =========================================================
# 書類情報
# =========================================================

DOCUMENT_INFO = {

    "1枚目": {
        "display_name": "① クレジット申込書",
        "description":
            "「クレジットお申込の内容」があり、"
            "申込者・勤務先・世帯状況・関係者情報・"
            "銀行口座などがある書類"
    },

    "2枚目": {
        "display_name": "② 役務申込書・指導内容",
        "description":
            "保護者氏名・指導対象・コース名・"
            "初回指導日・役務提供期間・商品数量・"
            "受領サインなどがある書類"
    }
}


# =========================================================
# 通常AI判定するチェック項目
# 厳格5項目はここには入れず、後でPython判定
# =========================================================

CHECK_ITEMS = {

    "1枚目": [

        (
            "お申込年月日",
            "上部の『お申込年月日』の年・月・日が記入されているか"
        ),

        (
            "申込者フリガナ",
            "申込者本人のフリガナ欄に記入があるか"
        ),

        (
            "申込者氏名",
            "申込者本人の姓・名が記入されているか"
        ),

        (
            "生年月日",
            "申込者本人の生年月日が記入されているか"
        ),

        (
            "申込者住所",
            """
            申込者の住所欄を確認する。
            都道府県まで記入され、
            都・道・府・県の適切なものに○があること。
            """
        ),

        (
            "勤務先名称",
            "勤務先名称欄に記入があるか"
        ),

        (
            "勤務先電話番号",
            "勤務先電話番号欄に記入があるか"
        ),

        (
            "雇用形態",
            "雇用形態のいずれかが選択されているか"
        ),

        (
            "派遣先・出向先",
            """
            派遣社員に○がある場合だけ、
            派遣先・出向先会社名が必要。
            派遣社員以外なら not_applicable。
            """
        ),

        (
            "世帯主の確認",
            """
            世帯主の確認欄の必要な選択があるか。
            右側の「連絡先」は空欄でもよい。
            """
        ),

        (
            "世帯状況",
            "縦書き『世帯状況』欄の必要事項を確認する"
        ),

        (
            "世帯主クレジット月額",
            """
            世帯主のクレジットの月あたり支払額を見る。
            100,000円を超えていれば warning。
            """
        ),

        (
            "関係者情報",
            """
            申込者が夫なら妻、
            妻なら夫の情報が記入されているか確認する。
            """
        ),

        (
            "クレジット側役務提供期間",
            """
            クレジット申込書側の役務提供期間欄に
            必要な期間が記入されているか。
            """
        ),

        (
            "特定商取引法42条受領年月日",
            """
            特定商取引法第42条第2項又は第3項書面の
            受領年月日の年・月・日がすべて記入されているか。
            """
        ),

        (
            "支払ヶ月",
            """
            指定されている「ヶ月」欄に
            月数が記入されているか。
            """
        ),

        (
            "銀行口座",
            """
            ゆうちょ銀行または
            ゆうちょ銀行以外の銀行の
            どちらか一方に必要事項が記入されているか。
            """
        ),

        (
            "口座名義人フリガナ",
            """
            一番下の口座名義人フリガナ欄に
            記入があるか。
            """
        ),
    ],


    "2枚目": [

        (
            "保護者氏名フリガナ",
            """
            保護者氏名に対応するフリガナ欄だけを確認。
            他のフリガナを代用しない。
            """
        ),

        (
            "保護者氏名",
            "保護者氏名欄に氏名があるか"
        ),

        (
            "初回指導日",
            """
            『初回指導日』欄そのものに
            年月日が記入されているか。
            """
        ),

        (
            "役務提供期間A",
            """
            役務提供期間のA行だけを確認する。
            A行が埋まっていればOK。
            B行は空欄でもよい。
            """
        ),
    ]
}


# =========================================================
# 都道府県一覧
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
        quality=94
    )

    b64 = base64.b64encode(
        buf.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{b64}"


def crop_by_ratio(img, left, top, right, bottom):

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
# 2枚目の重要欄を切り出す
#
# 同じ帳票テンプレートを使う前提。
# 写真に多少余白があっても周辺を広めに切る。
# =========================================================

def create_page2_crops(img):

    return {

        # 左上：保護者住所付近
        "住所・都道府県": crop_by_ratio(
            img,
            0.02, 0.08,
            0.52, 0.37
        ),

        # 右上：A/B/C指導対象
        "指導対象A": crop_by_ratio(
            img,
            0.48, 0.05,
            0.98, 0.33
        ),

        # 左下：コース名、初回指導日、役務提供期間
        "コース名・初回指導日・役務提供期間": crop_by_ratio(
            img,
            0.02, 0.34,
            0.48, 0.83
        ),

        # 中央の商品数量表
        "数量表": crop_by_ratio(
            img,
            0.40, 0.28,
            0.79, 0.92
        ),

        # 上部：書面交付・受領関連
        "受領サイン": crop_by_ratio(
            img,
            0.30, 0.00,
            0.98, 0.20
        ),
    }


# =========================================================
# 厳格5項目用のSchema
# =========================================================

def strict_page2_schema():

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "strict_page2_read",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    "course_name": {

                        "type": "object",

                        "properties": {

                            "written_text": {
                                "type": "string"
                            },

                            "has_handwriting_in_target_box": {
                                "type": "boolean"
                            }
                        },

                        "required": [
                            "written_text",
                            "has_handwriting_in_target_box"
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
                            },

                            "visible_mark_description": {
                                "type": "string"
                            }
                        },

                        "required": [
                            "yes_is_circled",
                            "visible_mark_description"
                        ],

                        "additionalProperties": False
                    },


                    "quantity": {

                        "type": "object",

                        "properties": {

                            "quantity_values": {

                                "type": "array",

                                "items": {
                                    "type": "integer"
                                }
                            },

                            "written_quantity_total": {
                                "type": "string"
                            },

                            "quantity_total_box_has_handwriting": {
                                "type": "boolean"
                            }
                        },

                        "required": [
                            "quantity_values",
                            "written_quantity_total",
                            "quantity_total_box_has_handwriting"
                        ],

                        "additionalProperties": False
                    },


                    "receipt_signature": {

                        "type": "object",

                        "properties": {

                            "written_text": {
                                "type": "string"
                            },

                            "signature_box_has_handwriting": {
                                "type": "boolean"
                            }
                        },

                        "required": [
                            "written_text",
                            "signature_box_has_handwriting"
                        ],

                        "additionalProperties": False
                    }

                },

                "required": [
                    "course_name",
                    "address",
                    "target_a",
                    "quantity",
                    "receipt_signature"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 2枚目の厳格読み取り
# =========================================================

def strict_read_page2(img):

    crops = create_page2_crops(img)

    content = [

        {
            "type": "text",
            "text": """
あなたは契約書の指定欄を読むだけの担当です。

重要：
今回はOK/NGを判断しません。

指定した欄に
「実際に見える手書き文字・数字・○」
だけを忠実に返してください。

絶対に推測しないでください。

たとえば住所に
「神戸市」
としか書かれていないなら、
兵庫県だと推測してはいけません。

written_prefecture は空文字にしてください。

また、
数量欄の数字を足して数量計を推測してはいけません。

数量計欄そのものが空欄なら、
written_quantity_total は空文字、
quantity_total_box_has_handwriting は false。

受領サインも、
別の氏名・販売担当者名・保護者氏名を
代用してはいけません。

コース名も、
別の欄にある「4回/月」等を
コース名として代用してはいけません。

指導対象Aも、
Aの「有」の文字そのものに
明確な○が付いている場合だけ
yes_is_circled=true にしてください。
"""
        }

    ]

    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text": f"以下は【{name}】周辺の拡大画像です。"
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

        response_format=strict_page2_schema()
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# Python側で厳格5項目を判定
# =========================================================

def expected_prefecture_mark(prefecture):

    if prefecture == "東京都":
        return "都"

    if prefecture == "北海道":
        return "道"

    if prefecture in [
        "京都府",
        "大阪府"
    ]:
        return "府"

    if prefecture.endswith("県"):
        return "県"

    return None


def strict_results_page2(data):

    results = []


    # -----------------------------------------------------
    # コース名
    # 必須：「週1」と「90分」
    # -----------------------------------------------------

    course = data["course_name"]

    course_text = course[
        "written_text"
    ].replace(" ", "")

    course_has_text = course[
        "has_handwriting_in_target_box"
    ]


    has_week1 = (
        "週1" in course_text
        or "週１" in course_text
    )

    has_90 = (
        "90分" in course_text
        or "９０分" in course_text
    )


    if (
        course_has_text
        and has_week1
        and has_90
    ):

        course_status = "ok"

        course_reason = (
            "コース名欄に「週1」と「90分」の記載を確認。"
        )

    else:

        course_status = "missing"

        course_reason = (
            "指定されたコース名欄に"
            "「週1 90分」の必要な記載を確認できません。"
        )


    results.append(
        {
            "name": "コース名",
            "status": course_status,
            "observed_value":
                course["written_text"],
            "reason": course_reason
        }
    )


    # -----------------------------------------------------
    # ご住所・連絡先
    # 都道府県の実記載＋丸
    # -----------------------------------------------------

    address = data["address"]

    written_prefecture = address[
        "written_prefecture"
    ].strip()

    mark = address[
        "circle_mark"
    ]


    valid_prefecture = (
        written_prefecture
        in PREFECTURES
    )

    required_mark = None

    if valid_prefecture:

        required_mark = expected_prefecture_mark(
            written_prefecture
        )


    if (
        valid_prefecture
        and mark == required_mark
    ):

        address_status = "ok"

        address_reason = (
            f"{written_prefecture}の記載と"
            f"「{mark}」への○を確認。"
        )

    else:

        address_status = "missing"

        if not valid_prefecture:

            address_reason = (
                "住所欄に都道府県名までの"
                "明確な記載を確認できません。"
            )

        elif mark in [
            "none",
            "uncertain"
        ]:

            address_reason = (
                f"{written_prefecture}の記載はありますが、"
                "都・道・府・県の対応箇所への"
                "明確な○を確認できません。"
            )

        else:

            address_reason = (
                f"{written_prefecture}に対して"
                f"○が「{mark}」となっており一致しません。"
            )


    observed_address = (
        f"都道府県："
        f"{written_prefecture if written_prefecture else '確認できず'}"
        f" / ○：{mark}"
    )


    results.append(
        {
            "name": "ご住所・連絡先",
            "status": address_status,
            "observed_value":
                observed_address,
            "reason": address_reason
        }
    )


    # -----------------------------------------------------
    # 指導対象A
    # -----------------------------------------------------

    target = data["target_a"]


    if target["yes_is_circled"]:

        target_status = "ok"

        target_reason = (
            "指導対象Aの「有」に"
            "明確な○を確認。"
        )

    else:

        target_status = "missing"

        target_reason = (
            "指導対象Aの「有」に"
            "明確な○を確認できません。"
        )


    results.append(
        {
            "name": "指導対象A",
            "status": target_status,
            "observed_value":
                target["visible_mark_description"],
            "reason": target_reason
        }
    )


    # -----------------------------------------------------
    # 数量計
    # -----------------------------------------------------

    quantity = data["quantity"]

    values = quantity[
        "quantity_values"
    ]

    total_text = quantity[
        "written_quantity_total"
    ].strip()

    total_has_handwriting = quantity[
        "quantity_total_box_has_handwriting"
    ]


    calculated_total = (
        sum(values)
        if values
        else None
    )


    written_total_number = None

    if total_text:

        match = re.search(
            r"\d+",
            total_text
        )

        if match:

            written_total_number = int(
                match.group()
            )


    if not total_has_handwriting:

        quantity_status = "missing"

        quantity_reason = (
            "数量計欄そのものに"
            "数値の記載を確認できません。"
        )

    elif written_total_number is None:

        quantity_status = "uncertain"

        quantity_reason = (
            "数量計欄に記入はありますが、"
            "数値を確実に読み取れません。"
        )

    elif calculated_total is None:

        quantity_status = "uncertain"

        quantity_reason = (
            "各商品の数量を確実に読み取れないため、"
            "数量計との照合ができません。"
        )

    elif (
        written_total_number
        != calculated_total
    ):

        quantity_status = "warning"

        quantity_reason = (
            f"数量欄の合計は{calculated_total}ですが、"
            f"数量計欄は{written_total_number}です。"
        )

    else:

        quantity_status = "ok"

        quantity_reason = (
            "数量欄の合計と"
            "数量計欄が一致しています。"
        )


    if values:

        calculation_text = (
            " + ".join(
                str(v)
                for v in values
            )
            + f" = {calculated_total}"
        )

    else:

        calculation_text = (
            "数量を確実に読み取れず"
        )


    total_display = (
        total_text
        if total_text
        else "空欄"
    )


    results.append(
        {
            "name": "数量計",
            "status": quantity_status,
            "observed_value":
                f"{calculation_text} / 数量計欄：{total_display}",
            "reason": quantity_reason
        }
    )


    # -----------------------------------------------------
    # 受領サイン
    # -----------------------------------------------------

    sign = data[
        "receipt_signature"
    ]


    if sign[
        "signature_box_has_handwriting"
    ]:

        sign_status = "ok"

        sign_reason = (
            "受領サイン指定欄の中に"
            "手書き記入を確認。"
        )

    else:

        sign_status = "missing"

        sign_reason = (
            "受領サイン指定欄に"
            "手書き署名・記名を確認できません。"
        )


    results.append(
        {
            "name": "受領サイン",
            "status": sign_status,
            "observed_value":
                sign["written_text"],
            "reason": sign_reason
        }
    )


    return results


# =========================================================
# 通常項目用Schema
# =========================================================

def normal_schema(active_pages):

    item_names = []

    for page in active_pages:

        for name, _ in CHECK_ITEMS[
            page
        ]:

            item_names.append(name)


    return {

        "type": "json_schema",

        "json_schema": {

            "name": "normal_contract_check",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    "pages": {

                        "type": "array",

                        "items": {

                            "type": "object",

                            "properties": {

                                "page_name": {
                                    "type": "string",
                                    "enum": active_pages
                                },

                                "document_type_status": {
                                    "type": "string",
                                    "enum": [
                                        "match",
                                        "wrong_document",
                                        "uncertain"
                                    ]
                                },

                                "document_quality": {
                                    "type": "string",
                                    "enum": [
                                        "good",
                                        "usable",
                                        "poor"
                                    ]
                                },

                                "items": {

                                    "type": "array",

                                    "items": {

                                        "type": "object",

                                        "properties": {

                                            "name": {
                                                "type": "string",
                                                "enum": item_names
                                            },

                                            "status": {
                                                "type": "string",
                                                "enum": [
                                                    "ok",
                                                    "missing",
                                                    "warning",
                                                    "uncertain",
                                                    "not_applicable"
                                                ]
                                            },

                                            "observed_value": {
                                                "type": "string"
                                            },

                                            "reason": {
                                                "type": "string"
                                            }
                                        },

                                        "required": [
                                            "name",
                                            "status",
                                            "observed_value",
                                            "reason"
                                        ],

                                        "additionalProperties": False
                                    }
                                }
                            },

                            "required": [
                                "page_name",
                                "document_type_status",
                                "document_quality",
                                "items"
                            ],

                            "additionalProperties": False
                        }
                    }
                },

                "required": [
                    "pages"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 通常AIチェック
# =========================================================

def normal_ai_check(files, prepared_images):

    active_pages = [
        page
        for page, uploaded
        in files.items()
        if uploaded is not None
    ]


    sections = []

    content = []


    for page in active_pages:

        checklist = "\n".join(
            [
                f"■ {name}\n{description}"
                for name, description
                in CHECK_ITEMS[page]
            ]
        )

        sections.append(
            f"""
【{page}】

{DOCUMENT_INFO[page]["description"]}

{checklist}
"""
        )


        content.append(
            {
                "type": "text",
                "text":
                    f"次の画像は【{page}】です。"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url":
                        pil_to_data_url(
                            prepared_images[page]
                        ),
                    "detail": "high"
                }
            }
        )


    prompt = f"""
あなたは日本語契約書の記入漏れ確認担当です。

以下のチェック項目を確認してください。

{"".join(sections)}

ルール：

・別ページの項目を混ぜない。
・今回アップロードされていないページは返さない。
・印刷文字だけでは記入済みにしない。
・指定された欄だけを見る。
・別欄の数字や氏名を代用しない。
・推測しない。
・判断できなければ uncertain。
・条件上不要なら not_applicable。
・問題なければ ok。
・未記入なら missing。
・内容上注意が必要なら warning。
"""


    content.insert(
        0,
        {
            "type": "text",
            "text": prompt
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

        response_format=
            normal_schema(active_pages)
    )


    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 結果表示
# =========================================================

def display_item(item):

    status = item["status"]


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

        if item[
            "observed_value"
        ]:

            st.write(
                "読み取った内容："
                f"**{item['observed_value']}**"
            )

        st.caption(
            item["reason"]
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

st.info(
    "「クレジットお申込の内容」、"
    "世帯状況、関係者情報、銀行口座などがある書類"
)

file1 = st.file_uploader(
    "① クレジット申込書の写真を選択",
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

st.info(
    "保護者氏名、指導対象A/B/C、"
    "コース名、初回指導日、役務提供期間、"
    "商品数量、受領サインなどがある書類"
)

file2 = st.file_uploader(
    "② 役務申込書・指導内容の写真を選択",
    type=[
        "jpg",
        "jpeg",
        "png"
    ],
    key="page2"
)


st.caption(
    "契約書全体が入るように、"
    "できるだけ真上から撮影してください。"
)


# =========================================================
# チェック開始
# =========================================================

if st.button(
    "🤖 AIでチェックする",
    type="primary",
    use_container_width=True
):

    if not file1 and not file2:

        st.error(
            "写真を1枚以上選んでください。"
        )

    else:

        try:

            files = {
                "1枚目": file1,
                "2枚目": file2
            }


            prepared_images = {}


            if file1:

                prepared_images[
                    "1枚目"
                ] = prepare_image(file1)


            if file2:

                prepared_images[
                    "2枚目"
                ] = prepare_image(file2)


            with st.spinner(
                "契約書を確認しています…"
            ):

                # 通常項目
                normal_result = normal_ai_check(
                    files,
                    prepared_images
                )


                # 2枚目の厳格5項目
                strict_items = []

                if file2:

                    strict_data = strict_read_page2(
                        prepared_images["2枚目"]
                    )

                    strict_items = strict_results_page2(
                        strict_data
                    )


            total_missing = 0
            total_warning = 0
            total_uncertain = 0


            # =================================================
            # ページ別表示
            # =================================================

            for page in normal_result[
                "pages"
            ]:

                page_name = page[
                    "page_name"
                ]


                st.subheader(
                    DOCUMENT_INFO[
                        page_name
                    ]["display_name"]
                )


                st.image(
                    prepared_images[
                        page_name
                    ],
                    use_container_width=True
                )


                if page[
                    "document_type_status"
                ] == "match":

                    st.success(
                        "✅ 書類の種類：正しい書類と判定"
                    )

                elif page[
                    "document_type_status"
                ] == "wrong_document":

                    st.error(
                        "❌ 書類の種類が違う可能性があります。"
                    )

                else:

                    st.warning(
                        "⚠️ 書類種類を確実に判定できません。"
                    )


                quality = page[
                    "document_quality"
                ]


                if quality == "good":

                    st.caption(
                        "✅ 画像品質：良好"
                    )

                elif quality == "usable":

                    st.caption(
                        "🟡 画像品質：判定可能"
                    )

                else:

                    st.caption(
                        "🔴 画像品質：不十分"
                    )


                page_items = list(
                    page["items"]
                )


                # 2枚目だけ厳格5項目を追加
                if page_name == "2枚目":

                    # 表示順
                    wanted_order = [
                        "保護者氏名フリガナ",
                        "保護者氏名",
                        "ご住所・連絡先",
                        "指導対象A",
                        "コース名",
                        "初回指導日",
                        "役務提供期間A",
                        "受領サイン",
                        "数量計"
                    ]


                    combined = {}


                    for item in page_items:

                        combined[
                            item["name"]
                        ] = item


                    for item in strict_items:

                        combined[
                            item["name"]
                        ] = item


                    page_items = []


                    for name in wanted_order:

                        if name in combined:

                            page_items.append(
                                combined[name]
                            )


                for item in page_items:

                    display_item(item)


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
            # 最終結果
            # =================================================

            st.divider()

            st.markdown(
                "## 📋 チェック結果まとめ"
            )


            if (
                total_missing == 0
                and total_warning == 0
                and total_uncertain == 0
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


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
