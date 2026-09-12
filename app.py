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
        "description": (
            "クレジットお申込の内容、申込者情報、勤務先、"
            "世帯状況、関係者情報、銀行口座などがある書類"
        )
    },

    "2枚目": {
        "display_name": "② 役務申込書・指導内容",
        "description": (
            "保護者氏名、指導対象、学校区分、コース名、"
            "初回指導日、役務提供期間、商品数量、受領サイン"
            "などがある書類"
        )
    }
}


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
# 通常チェック項目
# =========================================================

CHECK_ITEMS = {

    # =====================================================
    # 1枚目
    # =====================================================

    "1枚目": [

        (
            "お申込年月日",
            """
            「お申込年月日」欄そのものを見る。
            必要な年・月・日が記入されているか確認する。
            他の日付を代用しない。
            """
        ),

        (
            "申込者フリガナ",
            """
            申込者氏名に対応するフリガナ欄だけを見る。
            他の人物のフリガナを代用しない。
            """
        ),

        (
            "申込者氏名",
            """
            申込者本人の氏名欄が記入されているか確認する。
            """
        ),

        (
            "生年月日",
            """
            申込者本人の生年月日欄を見る。
            必要な年・月・日が記入されているか確認する。
            """
        ),

        (
            "申込者住所",
            """
            申込者本人の住所欄を見る。
            必要な住所が記入されているか確認する。
            """
        ),

        (
            "勤務先名称",
            """
            勤務先名称欄に会社名等が記入されているか確認する。
            """
        ),

        (
            "勤務先電話番号",
            """
            勤務先電話番号欄に番号が記入されているか確認する。
            """
        ),

        (
            "雇用形態",
            """
            雇用形態の選択肢の必要箇所に○があるか確認する。
            """
        ),

        (
            "派遣先・出向先",
            """
            「派遣社員」に○がある場合のみ、
            派遣先・出向先の会社名が必須。

            派遣社員なのに空欄 → missing

            派遣社員でない場合 → not_applicable
            """
        ),

        (
            "世帯主の確認",
            """
            世帯主の確認欄の必要箇所に
            記入または○があるか確認する。

            右側の「連絡先」は空欄でも問題ない。
            そこだけを理由に missing にしない。
            """
        ),

        (
            "世帯状況",
            """
            「世帯状況」欄の必要事項を確認する。

            必要な記入欄が空欄、
            または必要な選択箇所に○がない場合は missing。
            """
        ),

        (
            "世帯主クレジット月額",
            """
            「世帯主のクレジットの月あたりのお支払額」を読む。

            100,000円以下 → ok

            100,000円超 → warning

            100,000円を超える場合は
            要注意であることを理由に書く。
            """
        ),

        (
            "クレジット側役務提供期間",
            """
            クレジット申込書にある
            「役務提供期間」欄そのものを確認する。

            他の年月日を代用しない。
            """
        ),

        (
            "特定商取引法42条受領年月日",
            """
            「特定商取引法第42条第2項又は第3項書面の受領年月日」
            の欄そのものを見る。

            年・月・日がすべて必要。

            他の日付を代用しない。
            """
        ),

        (
            "支払ヶ月",
            """
            指定された「ヶ月」欄そのものを確認する。

            他の数字を代用しない。
            """
        ),

        (
            "銀行口座",
            """
            最下部の銀行口座欄を見る。

            「ゆうちょ銀行」
            または
            「ゆうちょ銀行以外の銀行」

            どちらか片方に必要事項が記入されていればOK。

            両方記入する必要はない。

            両方空欄なら missing。
            """
        ),

        (
            "口座名義人フリガナ",
            """
            使用している銀行口座に対応する
            「口座名義人フリガナ」欄を見る。

            他のフリガナを代用しない。
            """
        ),
    ],


    # =====================================================
    # 2枚目
    # 厳格項目以外
    # =====================================================

    "2枚目": [

        (
            "保護者氏名フリガナ",
            """
            保護者氏名に対応するフリガナ欄だけを見る。
            他のフリガナを代用しない。
            """
        ),

        (
            "保護者氏名",
            """
            保護者氏名欄が記入されているか確認する。
            """
        ),

        (
            "初回指導日",
            """
            「初回指導日」欄そのものを見る。

            他の日付を代用しない。
            """
        ),

        (
            "役務提供期間A",
            """
            役務提供期間のA行を見る。

            A行に必要事項が記入されていればOK。

            B行は空欄でも問題ない。
            """
        ),
    ]
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

        ratio = (
            max_side / max(img.size)
        )

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

    return (
        "data:image/jpeg;base64,"
        + encoded
    )


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
# 1枚目 関係者情報周辺
# =========================================================

def create_page1_crops(img):

    return {

        "関係者情報": crop_by_ratio(
            img,
            0.00,
            0.30,
            1.00,
            0.88
        )
    }


# =========================================================
# 2枚目 厳格チェック部分
# =========================================================

def create_page2_crops(img):

    return {

        "住所・都道府県": crop_by_ratio(
            img,
            0.00,
            0.05,
            0.55,
            0.35
        ),

        "指導対象と学校区分": crop_by_ratio(
            img,
            0.43,
            0.03,
            1.00,
            0.35
        ),

        "コース名": crop_by_ratio(
            img,
            0.00,
            0.32,
            0.48,
            0.72
        ),

        "商品数量表": crop_by_ratio(
            img,
            0.35,
            0.27,
            0.78,
            0.88
        ),

        "受領サイン": crop_by_ratio(
            img,
            0.20,
            0.00,
            1.00,
            0.25
        )
    }


# =========================================================
# 1枚目 関係者情報 Schema
# =========================================================

def relation_schema():

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "relation_information",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    "applicable": {
                        "type": "boolean"
                    },

                    "relationship": {
                        "type": "string"
                    },

                    "name_has_handwriting": {
                        "type": "boolean"
                    },

                    "address_text": {
                        "type": "string"
                    },

                    "address_has_handwriting": {
                        "type": "boolean"
                    },

                    "address_is_same_as_above": {
                        "type": "boolean"
                    },

                    "postal_code": {
                        "type": "string"
                    },

                    "postal_code_has_handwriting": {
                        "type": "boolean"
                    },

                    "mobile_number": {
                        "type": "string"
                    },

                    "mobile_has_handwriting": {
                        "type": "boolean"
                    },

                    "telephone_number": {
                        "type": "string"
                    },

                    "telephone_has_handwriting": {
                        "type": "boolean"
                    },

                    "required_circle_missing": {
                        "type": "boolean"
                    },

                    "other_required_blank": {
                        "type": "boolean"
                    },

                    "notes": {
                        "type": "string"
                    }
                },

                "required": [
                    "applicable",
                    "relationship",
                    "name_has_handwriting",
                    "address_text",
                    "address_has_handwriting",
                    "address_is_same_as_above",
                    "postal_code",
                    "postal_code_has_handwriting",
                    "mobile_number",
                    "mobile_has_handwriting",
                    "telephone_number",
                    "telephone_has_handwriting",
                    "required_circle_missing",
                    "other_required_blank",
                    "notes"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 関係者情報 AI読み取り
# =========================================================

def read_relation_information(img):

    crops = create_page1_crops(
        img
    )

    content = [

        {
            "type": "text",
            "text": """
あなたはクレジット申込書の
「関係者情報」欄だけを読む担当です。

OK/NGを勝手に判断せず、
実際に見える記入・○だけを返してください。


==================================================
対象
==================================================

申込者が夫の場合 → 妻の情報

申込者が妻の場合 → 夫の情報

を確認します。

関係者情報が明らかに対象外の場合は

applicable = false

にしてください。


==================================================
所在地・住所
==================================================

所在地欄は、

実際の住所が記入されている

または

「同上」

と書かれていれば記入ありです。

「同上」は有効です。

address_is_same_as_above は、
「同上」と書かれている場合のみ true。


==================================================
郵便番号
==================================================

関係者情報欄にある
郵便番号欄そのものを見る。

別の場所の郵便番号を代用しない。


==================================================
携帯番号
==================================================

関係者情報欄の携帯番号欄そのものを見る。


==================================================
電話番号
==================================================

関係者情報欄の固定電話番号欄を見る。

ただし電話番号が空欄であっても、
携帯番号が書かれていれば後でOK判定にするため、
実際の状態だけ返してください。


==================================================
その他
==================================================

関係者情報欄内で、
記入が必要な通常の項目が明らかに空欄なら

other_required_blank = true

必要な選択欄に○がない場合は

required_circle_missing = true

としてください。

印刷文字を手書き記入と誤認しないでください。
"""
        }
    ]


    # 全体画像も送る
    content.append(
        {
            "type": "text",
            "text": "以下は1枚目の書類全体です。"
        }
    )

    content.append(
        {
            "type": "image_url",
            "image_url": {
                "url": pil_to_data_url(
                    img
                ),
                "detail": "high"
            }
        }
    )


    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text":
                    f"以下は【{name}】周辺の拡大画像です。"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url":
                        pil_to_data_url(
                            crop
                        ),
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

        response_format=
            relation_schema()
    )


    return json.loads(
        response.choices[
            0
        ].message.content
    )


# =========================================================
# 関係者情報 Python判定
# =========================================================

def relation_result(data):

    if not data[
        "applicable"
    ]:

        return {
            "name":
                "関係者情報",

            "status":
                "not_applicable",

            "observed_value":
                "",

            "reason":
                "関係者情報の記入対象外と判定しました。"
        }


    problems = []


    # -----------------------------------------------------
    # 氏名
    # -----------------------------------------------------

    if not data[
        "name_has_handwriting"
    ]:

        problems.append(
            "氏名"
        )


    # -----------------------------------------------------
    # 住所
    # 住所記入 または 同上 でOK
    # -----------------------------------------------------

    address_ok = (
        data[
            "address_has_handwriting"
        ]
        or
        data[
            "address_is_same_as_above"
        ]
    )


    if not address_ok:

        problems.append(
            "所在地"
        )


    # -----------------------------------------------------
    # 郵便番号 必須
    # -----------------------------------------------------

    if not data[
        "postal_code_has_handwriting"
    ]:

        problems.append(
            "郵便番号"
        )


    # -----------------------------------------------------
    # 電話関係
    #
    # 携帯番号があれば
    # 固定電話は空欄でもOK
    #
    # 固定電話のみでも電話連絡先自体はある。
    # ただし現在の業務ルールでは
    # 「携帯番号は必須」とユーザー指定なので、
    # 携帯が空なら漏れ扱い。
    # -----------------------------------------------------

    if not data[
        "mobile_has_handwriting"
    ]:

        problems.append(
            "携帯番号"
        )


    # 固定電話については
    # 携帯ありなら完全に不要
    if (
        not data[
            "telephone_has_handwriting"
        ]
        and
        not data[
            "mobile_has_handwriting"
        ]
    ):

        # 携帯番号で既に問題登録されているため
        # 固定電話を重複カウントしない
        pass


    # -----------------------------------------------------
    # ○
    # -----------------------------------------------------

    if data[
        "required_circle_missing"
    ]:

        problems.append(
            "必要な○"
        )


    # -----------------------------------------------------
    # その他
    # -----------------------------------------------------

    if data[
        "other_required_blank"
    ]:

        problems.append(
            "その他の必要欄"
        )


    if problems:

        return {

            "name":
                "関係者情報",

            "status":
                "missing",

            "observed_value":
                "不足："
                + "、".join(
                    problems
                ),

            "reason":
                "関係者情報の必要項目に"
                "記入漏れまたは○の付け忘れがあります。"
        }


    return {

        "name":
            "関係者情報",

        "status":
            "ok",

        "observed_value":
            (
                "所在地："
                + (
                    "同上"
                    if data[
                        "address_is_same_as_above"
                    ]
                    else "記入あり"
                )
                + " / 郵便番号：記入あり"
                + " / 携帯番号：記入あり"
            ),

        "reason":
            "関係者情報の必要項目を確認しました。"
    }


# =========================================================
# 2枚目 厳格Schema
# =========================================================

def strict_page2_schema():

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "strict_page2",

            "strict": True,

            "schema": {

                "type": "object",

                "properties": {

                    # -------------------------------------------------
                    # コース名
                    # -------------------------------------------------

                    "course_name": {

                        "type": "object",

                        "properties": {

                            "written_text": {
                                "type": "string"
                            },

                            "target_box_has_handwriting": {
                                "type": "boolean"
                            }
                        },

                        "required": [
                            "written_text",
                            "target_box_has_handwriting"
                        ],

                        "additionalProperties": False
                    },


                    # -------------------------------------------------
                    # 住所
                    # -------------------------------------------------

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


                    # -------------------------------------------------
                    # 指導対象A
                    # -------------------------------------------------

                    "target_a": {

                        "type": "object",

                        "properties": {

                            "yes_is_circled": {
                                "type": "boolean"
                            },

                            "description": {
                                "type": "string"
                            }
                        },

                        "required": [
                            "yes_is_circled",
                            "description"
                        ],

                        "additionalProperties": False
                    },


                    # -------------------------------------------------
                    # 公・国・私
                    # -------------------------------------------------

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
                            },

                            "description": {
                                "type": "string"
                            }
                        },

                        "required": [
                            "public_circled",
                            "national_circled",
                            "private_circled",
                            "uncertain",
                            "description"
                        ],

                        "additionalProperties": False
                    },


                    # -------------------------------------------------
                    # 数量
                    # -------------------------------------------------

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


                    # -------------------------------------------------
                    # 受領サイン
                    # -------------------------------------------------

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
                    "school_type",
                    "quantity",
                    "receipt_signature"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 2枚目 厳格AI読み取り
# =========================================================

def strict_read_page2(img):

    crops = create_page2_crops(
        img
    )


    content = [

        {
            "type": "text",

            "text": """
あなたは契約書の指定された場所だけを
正確に読み取る担当です。

OKかNGかは判断しません。

実際に見える手書き文字、
数字、○だけを返します。

推測は禁止です。


==================================================
コース名
==================================================

「コース名」と印刷されている文字の
すぐ右側にある記入欄を見る。

必要なのは

週1 90分

という内容。

近くにある

4回/月

などは別項目です。

絶対に代用しない。

コース名欄が空欄なら

written_text = ""

target_box_has_handwriting = false


==================================================
住所・都道府県
==================================================

「ご住所・連絡先」の住所欄を見る。

住所から都道府県を推測してはいけない。

例えば

神戸市灘区

しか書かれていないなら

兵庫県

と推測しない。

さらに印刷されている

都
道
府
県

のどれかに○があるか確認する。


==================================================
指導対象A
==================================================

指導対象Aの

有

の文字そのものに○がある場合だけ

yes_is_circled = true

とする。

他の○を代用しない。


==================================================
学校区分 公・国・私
==================================================

指導対象A付近にある

公
国
私

という3つの選択肢だけを見る。

「公」に○ →
public_circled = true

「国」に○ →
national_circled = true

「私」に○ →
private_circled = true

○がないものは false。

性別、
有・無、
学校種別、
その他の○を
絶対に公・国・私の○と混同しない。

見えにくい場合は

uncertain = true


==================================================
数量
==================================================

中央の商品表を
行ごとに確認する。

各行の左側には、
学年等の欄が横方向に並んでいる。

例：

1  1  1

と記入されていた場合、

horizontal_values = [1, 1, 1]

とする。

そして同じ行の
右側にある

「数量」

という列を見る。

1 + 1 + 1 = 3

の場合、

数量欄に3が必要。

数量欄が空欄なら

written_quantity = ""

quantity_box_has_handwriting = false


重要：

数量欄より右にある

各単価
小計
商品定価合計
消費税
税込価格合計
お申込合計額

などの金額を数量として読んではいけない。

648000
712800
36000
108000

なども数量として使わない。

別の行の数字も混ぜない。

必ず同じ行だけで比較できる形で返す。


==================================================
受領サイン
==================================================

受領サインの指定欄だけを見る。

保護者氏名
申込者氏名
販売担当者名
社員名

などを代用しない。

指定欄が空欄なら

written_text = ""

signature_box_has_handwriting = false
"""
        }
    ]


    # 書類全体
    content.append(
        {
            "type": "text",
            "text":
                "以下は2枚目の書類全体です。位置確認に使用してください。"
        }
    )

    content.append(
        {
            "type": "image_url",
            "image_url": {

                "url":
                    pil_to_data_url(
                        img
                    ),

                "detail":
                    "high"
            }
        }
    )


    # 拡大
    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text":
                    f"以下は【{name}】周辺の拡大画像です。"
            }
        )

        content.append(
            {
                "type": "image_url",

                "image_url": {

                    "url":
                        pil_to_data_url(
                            crop
                        ),

                    "detail":
                        "high"
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

        response_format=
            strict_page2_schema()
    )


    return json.loads(
        response.choices[
            0
        ].message.content
    )


# =========================================================
# 都道府県○の対応
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

def strict_results_page2(
    data
):

    results = []


    # =====================================================
    # コース名
    # =====================================================

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
        or
        "週１" in text
    )

    minute_ok = (
        "90分" in text
        or
        "９０分" in text
    )


    if (
        course[
            "target_box_has_handwriting"
        ]
        and
        week_ok
        and
        minute_ok
    ):

        status = "ok"

        reason = (
            "コース名欄に"
            "「週1 90分」の記載があります。"
        )

    else:

        status = "missing"

        reason = (
            "コース名欄に"
            "「週1 90分」の記載を確認できません。"
        )


    results.append(
        {
            "name": "コース名",
            "status": status,
            "observed_value":
                course[
                    "written_text"
                ],
            "reason": reason
        }
    )


    # =====================================================
    # 住所
    # =====================================================

    address = data[
        "address"
    ]

    prefecture = (
        address[
            "written_prefecture"
        ].strip()
    )

    mark = address[
        "circle_mark"
    ]


    valid_prefecture = (
        prefecture
        in PREFECTURES
    )


    expected_mark = (
        expected_prefecture_mark(
            prefecture
        )
        if valid_prefecture
        else None
    )


    if (
        valid_prefecture
        and
        mark == expected_mark
    ):

        status = "ok"

        reason = (
            "都道府県名の記入と"
            "対応する都・道・府・県への○を確認しました。"
        )

    elif not valid_prefecture:

        status = "missing"

        reason = (
            "住所欄に都道府県名まで"
            "明確に記入されていません。"
        )

    elif mark in [
        "none",
        "uncertain"
    ]:

        status = "missing"

        reason = (
            f"{prefecture}の記載はありますが、"
            "対応する都・道・府・県への○を"
            "確認できません。"
        )

    else:

        status = "warning"

        reason = (
            "記載された都道府県と"
            "○を付けた都・道・府・県が一致していません。"
        )


    results.append(
        {
            "name":
                "ご住所・連絡先",

            "status":
                status,

            "observed_value":
                (
                    "都道府県："
                    + (
                        prefecture
                        if prefecture
                        else "確認できず"
                    )
                    + " / ○："
                    + mark
                ),

            "reason":
                reason
        }
    )


    # =====================================================
    # 指導対象A
    # =====================================================

    target = data[
        "target_a"
    ]


    if target[
        "yes_is_circled"
    ]:

        status = "ok"

        reason = (
            "指導対象Aの「有」に"
            "○を確認しました。"
        )

    else:

        status = "missing"

        reason = (
            "指導対象Aの「有」に"
            "○を確認できません。"
        )


    results.append(
        {
            "name":
                "指導対象A",

            "status":
                status,

            "observed_value":
                target[
                    "description"
                ],

            "reason":
                reason
        }
    )


    # =====================================================
    # 公・国・私
    # =====================================================

    school = data[
        "school_type"
    ]


    if school[
        "uncertain"
    ]:

        status = "uncertain"

        reason = (
            "公・国・私の○を"
            "画像から確実に判定できません。"
        )

        observed = (
            school[
                "description"
            ]
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


        if len(selected) == 1:

            status = "ok"

            reason = (
                "公・国・私のうち"
                "1つに○があります。"
            )

            observed = (
                selected[0]
            )


        elif len(selected) == 0:

            status = "missing"

            reason = (
                "公・国・私の"
                "いずれにも○を確認できません。"
            )

            observed = (
                "○なし"
            )


        else:

            status = "warning"

            reason = (
                "公・国・私のうち"
                "複数に○が付いています。"
            )

            observed = (
                "・".join(
                    selected
                )
            )


    results.append(
        {
            "name":
                "公・国・私",

            "status":
                status,

            "observed_value":
                observed,

            "reason":
                reason
        }
    )


    # =====================================================
    # 数量
    # =====================================================

    quantity = data[
        "quantity"
    ]


    rows = quantity[
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


        # 数字のある行だけ対象
        if not values:
            continue


        checked_rows += 1


        row_label = (
            row[
                "row_label"
            ].strip()
        )


        if not row_label:

            row_label = (
                f"{checked_rows}行目"
            )


        expected_quantity = sum(
            values
        )


        written_text = (
            row[
                "written_quantity"
            ].strip()
        )


        has_written_quantity = (
            row[
                "quantity_box_has_handwriting"
            ]
        )


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


        # -------------------------------------------------
        # 数量欄空欄
        # -------------------------------------------------

        if not has_written_quantity:

            has_missing = True

            row_results.append(
                f"{row_label}："
                f"{calculation}"
                " / 数量欄：空欄"
            )

            continue


        # -------------------------------------------------
        # 読み取れない
        # -------------------------------------------------

        if written_number is None:

            has_uncertain = True

            row_results.append(
                f"{row_label}："
                f"{calculation}"
                " / 数量欄：読取不能"
            )

            continue


        # -------------------------------------------------
        # 不一致
        # -------------------------------------------------

        if (
            written_number
            != expected_quantity
        ):

            has_warning = True

            row_results.append(
                f"{row_label}："
                f"{calculation}"
                f" / 数量欄：{written_number}"
            )

            continue


        # -------------------------------------------------
        # 正常
        # -------------------------------------------------

        row_results.append(
            f"{row_label}："
            f"{calculation}"
            f" / 数量欄：{written_number}"
        )


    if has_missing:

        quantity_status = "missing"

        quantity_reason = (
            "横方向の数字の合計に対して、"
            "右側の数量欄が空欄の行があります。"
        )


    elif has_warning:

        quantity_status = "warning"

        quantity_reason = (
            "横方向の数字の合計と"
            "数量欄の数字が一致しない行があります。"
        )


    elif has_uncertain:

        quantity_status = "uncertain"

        quantity_reason = (
            "数量欄を確実に読み取れない行があります。"
        )


    elif checked_rows > 0:

        quantity_status = "ok"

        quantity_reason = (
            "各行の横方向の数字の合計と"
            "数量欄が一致しています。"
        )


    else:

        quantity_status = "uncertain"

        quantity_reason = (
            "数量チェック対象の記入行を"
            "確認できませんでした。"
        )


    results.append(
        {
            "name":
                "数量",

            "status":
                quantity_status,

            "observed_value":
                " / ".join(
                    row_results
                ),

            "reason":
                quantity_reason
        }
    )


    # =====================================================
    # 受領サイン
    # =====================================================

    signature = data[
        "receipt_signature"
    ]


    if signature[
        "signature_box_has_handwriting"
    ]:

        status = "ok"

        reason = (
            "受領サイン欄そのものに"
            "手書き記入を確認しました。"
        )

    else:

        status = "missing"

        reason = (
            "受領サイン欄に"
            "記入を確認できません。"
        )


    results.append(
        {
            "name":
                "受領サイン",

            "status":
                status,

            "observed_value":
                signature[
                    "written_text"
                ],

            "reason":
                reason
        }
    )


    return results


# =========================================================
# 通常AI用Schema
# =========================================================

def normal_schema(
    active_pages
):

    all_names = []

    for page in active_pages:

        for name, _ in CHECK_ITEMS[
            page
        ]:

            if name not in all_names:

                all_names.append(
                    name
                )


    return {

        "type":
            "json_schema",

        "json_schema": {

            "name":
                "contract_check",

            "strict":
                True,

            "schema": {

                "type":
                    "object",

                "properties": {

                    "pages": {

                        "type":
                            "array",

                        "items": {

                            "type":
                                "object",

                            "properties": {

                                "page_name": {

                                    "type":
                                        "string",

                                    "enum":
                                        active_pages
                                },

                                "document_type_status": {

                                    "type":
                                        "string",

                                    "enum": [
                                        "match",
                                        "wrong_document",
                                        "uncertain"
                                    ]
                                },

                                "document_quality": {

                                    "type":
                                        "string",

                                    "enum": [
                                        "good",
                                        "usable",
                                        "poor"
                                    ]
                                },

                                "items": {

                                    "type":
                                        "array",

                                    "items": {

                                        "type":
                                            "object",

                                        "properties": {

                                            "name": {

                                                "type":
                                                    "string",

                                                "enum":
                                                    all_names
                                            },

                                            "status": {

                                                "type":
                                                    "string",

                                                "enum": [
                                                    "ok",
                                                    "missing",
                                                    "warning",
                                                    "uncertain",
                                                    "not_applicable"
                                                ]
                                            },

                                            "observed_value": {
                                                "type":
                                                    "string"
                                            },

                                            "reason": {
                                                "type":
                                                    "string"
                                            }
                                        },

                                        "required": [
                                            "name",
                                            "status",
                                            "observed_value",
                                            "reason"
                                        ],

                                        "additionalProperties":
                                            False
                                    }
                                }
                            },

                            "required": [
                                "page_name",
                                "document_type_status",
                                "document_quality",
                                "items"
                            ],

                            "additionalProperties":
                                False
                        }
                    }
                },

                "required": [
                    "pages"
                ],

                "additionalProperties":
                    False
            }
        }
    }


# =========================================================
# 通常AIチェック
# =========================================================

def normal_ai_check(
    files,
    images
):

    active_pages = [
        page
        for page, file
        in files.items()
        if file is not None
    ]


    rules = []


    for page in active_pages:

        rules.append(
            f"""
==================================================
{page}
==================================================

{DOCUMENT_INFO[page]["description"]}
"""
        )


        for name, rule in CHECK_ITEMS[
            page
        ]:

            rules.append(
                f"""
■ {name}

{rule}
"""
            )


    content = [

        {
            "type": "text",

            "text": f"""
あなたは契約書の提出前チェック担当です。

以下のルールに従って
記入漏れを確認してください。

{"".join(rules)}


==================================================
共通ルール
==================================================

・指定された欄だけを見る。

・別の欄の文字や数字を代用しない。

・印刷文字を手書き記入と誤認しない。

・1枚目と2枚目を混同しない。

・画像から判断できなければ uncertain。

・条件上不要なら not_applicable。

・空欄は missing。

・明確な不一致や条件超過は warning。

・個人名、住所、電話番号等を
  必要以上に全文転記しない。
"""
        }
    ]


    for page in active_pages:

        content.append(
            {
                "type": "text",
                "text":
                    f"以下の画像は【{page}】です。"
            }
        )

        content.append(
            {
                "type": "image_url",

                "image_url": {

                    "url":
                        pil_to_data_url(
                            images[
                                page
                            ]
                        ),

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
            normal_schema(
                active_pages
            )
    )


    return json.loads(
        response.choices[
            0
        ].message.content
    )


# =========================================================
# 通常結果を整理
# =========================================================

def normalize_normal_result(
    result,
    active_pages
):

    page_map = {}


    for page in result.get(
        "pages",
        []
    ):

        page_name = page.get(
            "page_name"
        )

        if page_name in active_pages:

            page_map[
                page_name
            ] = page


    normalized_pages = []


    for page_name in active_pages:

        expected_names = [
            name
            for name, _
            in CHECK_ITEMS[
                page_name
            ]
        ]


        if page_name not in page_map:

            normalized_pages.append(
                {
                    "page_name":
                        page_name,

                    "document_type_status":
                        "uncertain",

                    "document_quality":
                        "poor",

                    "items": [
                        {
                            "name":
                                name,

                            "status":
                                "uncertain",

                            "observed_value":
                                "",

                            "reason":
                                "結果を取得できませんでした。"
                        }

                        for name
                        in expected_names
                    ]
                }
            )

            continue


        page = page_map[
            page_name
        ]


        item_map = {}


        for item in page.get(
            "items",
            []
        ):

            name = item.get(
                "name"
            )

            if name in expected_names:

                item_map[
                    name
                ] = item


        clean_items = []


        for name in expected_names:

            if name in item_map:

                clean_items.append(
                    item_map[
                        name
                    ]
                )

            else:

                clean_items.append(
                    {
                        "name":
                            name,

                        "status":
                            "uncertain",

                        "observed_value":
                            "",

                        "reason":
                            "この項目の結果を取得できませんでした。"
                    }
                )


        page[
            "items"
        ] = clean_items


        normalized_pages.append(
            page
        )


    result[
        "pages"
    ] = normalized_pages

    return result


# =========================================================
# 結果表示
# =========================================================

def display_item(
    item
):

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
# アップロード画面
# =========================================================

st.divider()

st.markdown(
    "## 📷 契約書の写真を選択"
)


st.markdown(
    "### ① クレジット申込書"
)

st.info(
    "申込者情報・勤務先・世帯状況・"
    "関係者情報・銀行口座などがある方です。"
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


st.markdown(
    "### ② 役務申込書・指導内容"
)

st.info(
    "保護者氏名・指導対象・公/国/私・"
    "コース名・商品数量・受領サインなどがある方です。"
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
    "書類全体が写るように、"
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
            "写真を1枚以上選択してください。"
        )

    else:

        try:

            files = {
                "1枚目":
                    file1,

                "2枚目":
                    file2
            }


            active_pages = [
                page
                for page, file
                in files.items()
                if file is not None
            ]


            images = {}


            if file1:

                images[
                    "1枚目"
                ] = prepare_image(
                    file1
                )


            if file2:

                images[
                    "2枚目"
                ] = prepare_image(
                    file2
                )


            with st.spinner(
                "AIが契約書を確認しています…"
            ):

                # -----------------------------------------
                # 通常項目
                # -----------------------------------------

                normal_result = (
                    normal_ai_check(
                        files,
                        images
                    )
                )


                normal_result = (
                    normalize_normal_result(
                        normal_result,
                        active_pages
                    )
                )


                # -----------------------------------------
                # 1枚目 関係者情報
                # -----------------------------------------

                relation_item = None


                if file1:

                    relation_data = (
                        read_relation_information(
                            images[
                                "1枚目"
                            ]
                        )
                    )

                    relation_item = (
                        relation_result(
                            relation_data
                        )
                    )


                # -----------------------------------------
                # 2枚目 厳格判定
                # -----------------------------------------

                strict_page2_items = []


                if file2:

                    strict_data = (
                        strict_read_page2(
                            images[
                                "2枚目"
                            ]
                        )
                    )

                    strict_page2_items = (
                        strict_results_page2(
                            strict_data
                        )
                    )


            # =================================================
            # 集計
            # =================================================

            total_missing = 0
            total_warning = 0
            total_uncertain = 0


            # =================================================
            # ページ表示
            # =================================================

            for page in normal_result[
                "pages"
            ]:

                page_name = page[
                    "page_name"
                ]


                st.divider()

                st.subheader(
                    DOCUMENT_INFO[
                        page_name
                    ][
                        "display_name"
                    ]
                )


                st.image(
                    images[
                        page_name
                    ],
                    use_container_width=True
                )


                # ---------------------------------------------
                # 書類種類
                # ---------------------------------------------

                doc_status = page[
                    "document_type_status"
                ]


                if doc_status == "match":

                    st.success(
                        "✅ 書類種類：OK"
                    )


                elif doc_status == "wrong_document":

                    st.error(
                        "❌ 違う書類の可能性があります。"
                    )


                else:

                    st.warning(
                        "🔍 書類種類を確実に判定できません。"
                    )


                # ---------------------------------------------
                # 通常結果
                # ---------------------------------------------

                combined = {}


                for item in page[
                    "items"
                ]:

                    combined[
                        item[
                            "name"
                        ]
                    ] = item


                # =============================================
                # 1枚目
                # =============================================

                if page_name == "1枚目":

                    if relation_item:

                        combined[
                            "関係者情報"
                        ] = relation_item


                    order = [

                        "お申込年月日",

                        "申込者フリガナ",

                        "申込者氏名",

                        "生年月日",

                        "申込者住所",

                        "勤務先名称",

                        "勤務先電話番号",

                        "雇用形態",

                        "派遣先・出向先",

                        "世帯主の確認",

                        "世帯状況",

                        "世帯主クレジット月額",

                        "関係者情報",

                        "クレジット側役務提供期間",

                        "特定商取引法42条受領年月日",

                        "支払ヶ月",

                        "銀行口座",

                        "口座名義人フリガナ"
                    ]


                # =============================================
                # 2枚目
                # =============================================

                else:

                    for item in strict_page2_items:

                        combined[
                            item[
                                "name"
                            ]
                        ] = item


                    order = [

                        "保護者氏名フリガナ",

                        "保護者氏名",

                        "ご住所・連絡先",

                        "指導対象A",

                        "公・国・私",

                        "コース名",

                        "初回指導日",

                        "役務提供期間A",

                        "数量",

                        "受領サイン"
                    ]


                # ---------------------------------------------
                # 表示
                # ---------------------------------------------

                for name in order:

                    if name not in combined:
                        continue


                    item = combined[
                        name
                    ]


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
            # 最終まとめ
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
                    "該当箇所を人の目でも確認してください。"
                )


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
