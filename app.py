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
        "StreamlitのSecretsにAPIキーを登録してください。"
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
            "「クレジットお申込の内容」があり、"
            "申込者情報・勤務先・世帯状況・関係者情報・"
            "銀行口座などが載っている書類"
        )
    },

    "2枚目": {
        "display_name": "② 役務申込書・指導内容",
        "description": (
            "保護者氏名・指導対象・コース名・初回指導日・"
            "役務提供期間・商品数量・受領サインなどが載っている書類"
        )
    }
}


# =========================================================
# 通常AI判定項目
# =========================================================

CHECK_ITEMS = {

    # =====================================================
    # 1枚目
    # =====================================================

    "1枚目": [

        (
            "お申込年月日",
            """
            書類上部の「お申込年月日」欄だけを見る。
            年・月・日が必要な箇所まで記入されているか確認する。
            """
        ),

        (
            "申込者フリガナ",
            """
            申込者本人の氏名に対応するフリガナ欄だけを見る。
            他の人物のフリガナを代用しない。
            """
        ),

        (
            "申込者氏名",
            """
            申込者本人の姓・名が記入されているか確認する。
            """
        ),

        (
            "生年月日",
            """
            申込者本人の生年月日の年・月・日が記入されているか確認する。
            """
        ),

        (
            "申込者住所",
            """
            申込者本人の「ご住所」欄を見る。

            都道府県まで実際に記入されていること。

            さらに印刷されている
            「都・道・府・県」
            の適切なものに○があること。

            住所から都道府県を推測してはいけない。
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
            勤務先電話番号欄に電話番号が記入されているか確認する。
            """
        ),

        (
            "雇用形態",
            """
            雇用形態の選択肢のいずれかに○があるか確認する。
            """
        ),

        (
            "派遣先・出向先",
            """
            雇用形態と連動して判定する。

            「派遣社員」に○がある場合のみ
            「派遣先・出向先の会社名」が必須。

            派遣社員なのに会社名が空欄 → missing

            派遣社員でない場合 →
            not_applicable
            """
        ),

        (
            "世帯主の確認",
            """
            「世帯主の確認」欄について、
            申込者本人またはその他等の必要な選択があるか確認する。

            ただし右側の「連絡先」は空欄でも問題ない。

            連絡先が空欄であることを理由に
            missing にしてはいけない。
            """
        ),

        (
            "世帯状況",
            """
            縦書きで「世帯状況」と書かれた欄を確認する。
            必要な世帯主情報が記入されているか確認する。
            """
        ),

        (
            "世帯主クレジット月額",
            """
            「世帯主のクレジットの月あたりのお支払額」を読む。

            100,000円以下 → ok

            100,000円を超える → warning

            10万円を超えている場合は
            「10万円を超えているため要注意」と理由に書く。
            """
        ),

        (
            "関係者情報",
            """
            縦書きの「関係者情報」欄を見る。

            申込者が夫なら妻の情報。
            申込者が妻なら夫の情報。

            配偶者がいるのに必要な情報が空欄なら missing。

            明らかに対象外なら not_applicable。
            """
        ),

        (
            "クレジット側役務提供期間",
            """
            クレジット申込書側の「役務提供期間」
            または「役務提供期間（権利の移転時期）」欄を見る。

            必要な期間・年月等が記入されているか確認する。

            別の日付を代用しない。
            """
        ),

        (
            "特定商取引法42条受領年月日",
            """
            「特定商取引法第42条第2項又は第3項書面の受領年月日」
            の欄だけを見る。

            年・月・日がすべて記入されていれば ok。

            一部でも欠けていれば missing。

            他の日付を代用しない。
            """
        ),

        (
            "支払ヶ月",
            """
            指定されている「ヶ月」欄だけを見る。

            月数が記入されているか確認する。

            別の数字・日付・金額を代用しない。
            """
        ),

        (
            "銀行口座",
            """
            最下部の銀行口座欄を見る。

            左側：
            ゆうちょ銀行

            右側：
            ゆうちょ銀行以外の銀行

            どちらか片方に必要事項が記入されていればOK。

            両方を書く必要はない。

            両方空欄なら missing。
            """
        ),

        (
            "口座名義人フリガナ",
            """
            最下部の「口座名義人」の「フリガナ」欄を見る。

            使用している銀行口座に対応する
            口座名義人フリガナが記入されているか確認する。

            他のフリガナを代用しない。
            """
        ),
    ],


    # =====================================================
    # 2枚目
    # 厳格5項目以外
    # =====================================================

    "2枚目": [

        (
            "保護者氏名フリガナ",
            """
            保護者氏名に対応するフリガナ欄だけを見る。

            他の人物のフリガナを代用しない。
            """
        ),

        (
            "保護者氏名",
            """
            保護者氏名欄に氏名が記入されているか確認する。
            """
        ),

        (
            "初回指導日",
            """
            左下付近の「初回指導日」欄そのものを見る。

            必要な年月日が記入されているか確認する。

            他の日付を代用しない。
            """
        ),

        (
            "役務提供期間A",
            """
            左下付近の「役務提供期間」欄を見る。

            A行だけを判定する。

            A行が必要箇所まで記入されていれば ok。

            B行は空欄でも問題ない。

            B行が空欄であることを理由に
            missing にしてはいけない。
            """
        ),
    ]
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
# 2枚目の重要部分を切り出し
# =========================================================

def create_page2_crops(img):

    return {

        # 保護者住所周辺
        "住所・都道府県": crop_by_ratio(
            img,
            0.00,
            0.05,
            0.53,
            0.35
        ),

        # 指導対象A/B/C周辺
        "指導対象A": crop_by_ratio(
            img,
            0.46,
            0.04,
            0.98,
            0.30
        ),

        # コース名周辺
        "コース名": crop_by_ratio(
            img,
            0.00,
            0.34,
            0.43,
            0.70
        ),

        # 商品表全体
        "商品数量表": crop_by_ratio(
            img,
            0.36,
            0.28,
            0.78,
            0.90
        ),

        # 受領サイン・書面交付周辺
        "受領サイン": crop_by_ratio(
            img,
            0.25,
            0.00,
            1.00,
            0.22
        ),
    }


# =========================================================
# 2枚目 厳格項目Schema
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


                    # -------------------------------------------------
                    # 数量
                    # 各行ごとに判定
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
                    "quantity",
                    "receipt_signature"
                ],

                "additionalProperties": False
            }
        }
    }


# =========================================================
# 厳格項目 AI読み取り
# =========================================================

def strict_read_page2(img):

    crops = create_page2_crops(
        img
    )

    content = [

        {
            "type": "text",
            "text": """
あなたは契約書の指定欄を「読むだけ」の担当です。

今回はOK/NGを判断しません。

指定欄そのものに実際に見える
手書き文字・数字・○だけを返してください。

絶対に推測しないでください。


==================================================
コース名
==================================================

左側の「コース名」の右横にある
指定欄だけを見る。

この欄に
「週1 90分」
という内容が必要。

ただし、
別の欄にある
「4回/月」
「○円」
「月謝」
等を
コース名として代用してはいけない。

指定欄が空欄なら

written_text = ""

target_box_has_handwriting = false


==================================================
住所
==================================================

「ご住所・連絡先」の住所欄だけを見る。

住所から都道府県を推測してはいけない。

例えば

「神戸市灘区」

としか書かれていないなら

「兵庫県」

とは返さない。

written_prefecture は空文字。

さらに、
印刷された

都
道
府
県

のどれに実際に○が付いているかを見る。

○がなければ

circle_mark = "none"


==================================================
指導対象A
==================================================

指導対象Aの

「有」

という文字そのものに
明確な○が付いている場合だけ

yes_is_circled = true

にする。

近くの
性別の○、
学校区分の○、
別の○
を代用してはいけない。


==================================================
数量
==================================================

中央の商品・教材表を
「行ごと」に確認する。

ここが非常に重要。

各商品行には、
左から横方向に

小1
小2
小3
小4
小5
小6

または

中1
中2
中3

などの列がある。

そこに

1
1
1

などの数字が横方向に記入される。

各行ごとに、

1.
横方向に実際に書かれている数字を読む。

2.
horizontal_values に
その数字を順番に入れる。

例：

1、1、1

なら

horizontal_values = [1, 1, 1]

3.
その同じ行の右側にある
「数量」欄そのものを見る。

4.
その数量欄に
「3」
と書いてあれば

written_quantity = "3"

quantity_box_has_handwriting = true

5.
数量欄が空欄なら

written_quantity = ""

quantity_box_has_handwriting = false


絶対に以下を数量として使わない：

金額
単価
小計
商品定価合計
消費税
税込価格合計
申込合計額
36000
72000
648000
712800

など。

これらはすべて金額。

数量ではない。

別の行の数量も混ぜない。

必ず行ごとに返す。


==================================================
受領サイン
==================================================

受領サイン・受領確認の
指定された署名欄そのものだけを見る。

販売担当者名
保護者氏名
申込者氏名
会社担当者名

などを
受領サインとして代用してはいけない。

指定欄が空欄なら

written_text = ""

signature_box_has_handwriting = false
"""
        }
    ]


    for name, crop in crops.items():

        content.append(
            {
                "type": "text",
                "text": (
                    f"以下は【{name}】周辺を"
                    "拡大した画像です。"
                )
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": pil_to_data_url(
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
            strict_page2_schema()
    )


    return json.loads(
        response.choices[
            0
        ].message.content
    )


# =========================================================
# 都道府県の○
# =========================================================

def expected_prefecture_mark(
    prefecture
):

    if prefecture == "東京都":
        return "都"

    if prefecture == "北海道":
        return "道"

    if prefecture in [
        "京都府",
        "大阪府"
    ]:
        return "府"

    if prefecture.endswith(
        "県"
    ):
        return "県"

    return None


# =========================================================
# 厳格項目をPython側で判定
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

    course_text = (
        course[
            "written_text"
        ]
        .replace(" ", "")
        .replace("　", "")
    )

    has_week1 = (
        "週1" in course_text
        or
        "週１" in course_text
    )

    has_90 = (
        "90分" in course_text
        or
        "９０分" in course_text
    )

    if (
        course[
            "target_box_has_handwriting"
        ]
        and
        has_week1
        and
        has_90
    ):

        status = "ok"

        reason = (
            "コース名欄に"
            "「週1」「90分」の記載があります。"
        )

    else:

        status = "missing"

        reason = (
            "指定されたコース名欄に"
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
    # 住所・都道府県
    # =====================================================

    address = data[
        "address"
    ]

    written_prefecture = (
        address[
            "written_prefecture"
        ].strip()
    )

    mark = address[
        "circle_mark"
    ]

    valid_prefecture = (
        written_prefecture
        in PREFECTURES
    )

    required_mark = None

    if valid_prefecture:

        required_mark = (
            expected_prefecture_mark(
                written_prefecture
            )
        )


    if (
        valid_prefecture
        and
        mark == required_mark
    ):

        status = "ok"

        reason = (
            f"{written_prefecture}の記載と"
            f"「{mark}」への○を確認しました。"
        )

    else:

        status = "missing"

        if not valid_prefecture:

            reason = (
                "住所欄に都道府県名までの"
                "明確な記載を確認できません。"
            )

        elif mark in [
            "none",
            "uncertain"
        ]:

            reason = (
                f"{written_prefecture}の記載はありますが、"
                "都・道・府・県の対応箇所への○を"
                "確認できません。"
            )

        else:

            status = "warning"

            reason = (
                f"{written_prefecture}に対して"
                f"「{mark}」に○があり、"
                "都道府県と○が一致していません。"
            )


    results.append(
        {
            "name": "ご住所・連絡先",
            "status": status,
            "observed_value":
                (
                    "都道府県："
                    +
                    (
                        written_prefecture
                        if written_prefecture
                        else "確認できず"
                    )
                    +
                    f" / ○：{mark}"
                ),
            "reason": reason
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
            "明確な○を確認できません。"
        )


    results.append(
        {
            "name": "指導対象A",
            "status": status,
            "observed_value":
                target[
                    "visible_mark_description"
                ],
            "reason": reason
        }
    )


    # =====================================================
    # 数量
    #
    # 行ごとに
    # 1 + 1 + 1 = 3
    # と右側の数量欄を比較
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


    for i, row in enumerate(
        rows,
        start=1
    ):

        values = row[
            "horizontal_values"
        ]

        # 横方向に数字がない行は
        # 判定対象外
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


        calculated_total = sum(
            values
        )


        written_text = (
            row[
                "written_quantity"
            ].strip()
        )


        has_handwriting = row[
            "quantity_box_has_handwriting"
        ]


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


        calculation_text = (
            " + ".join(
                str(v)
                for v in values
            )
            +
            f" = {calculated_total}"
        )


        # ---------------------------------------------
        # 数量欄そのものが空欄
        # ---------------------------------------------

        if not has_handwriting:

            has_missing = True

            row_results.append(
                f"{row_label}："
                f"{calculation_text}"
                f" / 数量欄：空欄"
            )

            continue


        # ---------------------------------------------
        # 書いてあるが読めない
        # ---------------------------------------------

        if written_number is None:

            has_uncertain = True

            row_results.append(
                f"{row_label}："
                f"{calculation_text}"
                f" / 数量欄：読取不能"
            )

            continue


        # ---------------------------------------------
        # 数量不一致
        # ---------------------------------------------

        if (
            written_number
            != calculated_total
        ):

            has_warning = True

            row_results.append(
                f"{row_label}："
                f"{calculation_text}"
                f" / 数量欄："
                f"{written_number}"
            )

            continue


        # ---------------------------------------------
        # 一致
        # ---------------------------------------------

        row_results.append(
            f"{row_label}："
            f"{calculation_text}"
            f" / 数量欄："
            f"{written_number}"
        )


    # =====================================================
    # 数量の最終判定
    # =====================================================

    if has_missing:

        quantity_status = (
            "missing"
        )

        quantity_reason = (
            "横方向の数字を合計した結果に対して、"
            "右側の数量欄が空欄の行があります。"
        )

    elif has_warning:

        quantity_status = (
            "warning"
        )

        quantity_reason = (
            "横方向の数字の合計と"
            "右側の数量欄が一致していない行があります。"
        )

    elif has_uncertain:

        quantity_status = (
            "uncertain"
        )

        quantity_reason = (
            "数量欄の一部を確実に読み取れません。"
        )

    elif checked_rows > 0:

        quantity_status = (
            "ok"
        )

        quantity_reason = (
            "各行の横方向の数字の合計と"
            "右側の数量欄が一致しています。"
        )

    else:

        quantity_status = (
            "uncertain"
        )

        quantity_reason = (
            "数量判定対象となる"
            "横方向の数字を確認できませんでした。"
        )


    results.append(
        {
            "name": "数量",
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

    sign = data[
        "receipt_signature"
    ]


    if sign[
        "signature_box_has_handwriting"
    ]:

        status = "ok"

        reason = (
            "受領サイン指定欄に"
            "手書き署名・記名を確認しました。"
        )

    else:

        status = "missing"

        reason = (
            "受領サイン指定欄に"
            "手書き署名・記名を確認できません。"
        )


    results.append(
        {
            "name": "受領サイン",
            "status": status,
            "observed_value":
                sign[
                    "written_text"
                ],
            "reason": reason
        }
    )


    return results


# =========================================================
# 通常項目Schema
# =========================================================

def normal_schema(
    active_pages
):

    names = []

    for page in active_pages:

        for name, _ in CHECK_ITEMS[
            page
        ]:

            if name not in names:
                names.append(
                    name
                )


    return {

        "type": "json_schema",

        "json_schema": {

            "name":
                "normal_contract_check",

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
                                                    names
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
    prepared_images
):

    active_pages = [
        page
        for page, uploaded
        in files.items()
        if uploaded is not None
    ]


    content = []

    sections = []


    for page in active_pages:

        checklist = "\n".join(
            [
                f"""
■ {name}

{description}
"""
                for name, description
                in CHECK_ITEMS[
                    page
                ]
            ]
        )


        sections.append(
            f"""
==================================================
【{page}】
==================================================

{DOCUMENT_INFO[page]["description"]}

{checklist}
"""
        )


        content.append(
            {
                "type":
                    "text",

                "text":
                    f"次の画像は【{page}】です。"
            }
        )


        content.append(
            {
                "type":
                    "image_url",

                "image_url": {

                    "url":
                        pil_to_data_url(
                            prepared_images[
                                page
                            ]
                        ),

                    "detail":
                        "high"
                }
            }
        )


    prompt = f"""
あなたは日本語契約書の
提出前チェック担当です。

以下のチェック項目を
厳密に確認してください。

{"".join(sections)}


==================================================
絶対ルール
==================================================

1.
1枚目と2枚目の項目を
絶対に混ぜない。

2.
アップロードされていないページは
結果を返さない。

3.
印刷文字だけでは
記入済みにしない。

4.
指定された欄そのものだけを見る。

5.
別の欄の名前・数字・年月日・金額を
代用しない。

6.
住所から都道府県を推測しない。

7.
判断できない場合は
uncertain。

8.
条件上不要なら
not_applicable。

9.
問題なしは
ok。

10.
記入漏れは
missing。

11.
条件違反・不一致は
warning。

12.
observed_valueには
必要な範囲だけ記載する。

13.
個人情報を必要以上に
全文転記しない。
"""


    content.insert(
        0,
        {
            "type":
                "text",

            "text":
                prompt
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
# AI結果をページごとに整理
# =========================================================

def normalize_normal_result(
    result,
    active_pages
):

    returned_pages = {}

    for page in result.get(
        "pages",
        []
    ):

        page_name = page.get(
            "page_name"
        )

        if page_name in active_pages:

            returned_pages[
                page_name
            ] = page


    normalized = []


    for page_name in active_pages:

        expected_names = [
            name
            for name, _
            in CHECK_ITEMS[
                page_name
            ]
        ]


        if page_name not in returned_pages:

            normalized.append(
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
                                "AIから判定結果が返されませんでした。"
                        }
                        for name
                        in expected_names
                    ]
                }
            )

            continue


        page = returned_pages[
            page_name
        ]


        returned_items = {}


        for item in page.get(
            "items",
            []
        ):

            name = item.get(
                "name"
            )

            if (
                name in expected_names
                and
                name not in returned_items
            ):

                returned_items[
                    name
                ] = item


        clean_items = []


        for name in expected_names:

            if name in returned_items:

                clean_items.append(
                    returned_items[
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
                            "AIからこの項目の結果が返されませんでした。"
                    }
                )


        page[
            "items"
        ] = clean_items


        normalized.append(
            page
        )


    result[
        "pages"
    ] = normalized


    return result


# =========================================================
# 表示
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


        if item[
            "observed_value"
        ]:

            st.write(
                "読み取った内容："
                f"**{item['observed_value']}**"
            )


        st.caption(
            item[
                "reason"
            ]
        )


# =========================================================
# アップロード画面
# =========================================================

st.divider()

st.markdown(
    "## 📷 契約書の写真を選択"
)

st.write(
    "それぞれ対応する書類を選んでください。"
)


# =========================================================
# 1枚目
# =========================================================

st.markdown(
    "### ① クレジット申込書"
)

st.info(
    "「クレジットお申込の内容」があり、"
    "お申込者情報・勤務先・世帯状況・関係者情報・"
    "銀行口座などが載っている書類です。"
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


# =========================================================
# 2枚目
# =========================================================

st.markdown(
    "### ② 役務申込書・指導内容"
)

st.info(
    "保護者氏名・指導対象A/B/C・コース名・"
    "初回指導日・役務提供期間・商品数量・"
    "受領サインなどが載っている書類です。"
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
    "📌 契約書全体が入るように、"
    "できるだけ真上から明るい場所で撮影してください。"
)


# =========================================================
# AIチェック開始
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
                "1枚目":
                    file1,

                "2枚目":
                    file2
            }


            active_pages = [
                page
                for page, uploaded
                in files.items()
                if uploaded is not None
            ]


            prepared_images = {}


            if file1:

                prepared_images[
                    "1枚目"
                ] = prepare_image(
                    file1
                )


            if file2:

                prepared_images[
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
                        prepared_images
                    )
                )


                normal_result = (
                    normalize_normal_result(
                        normal_result,
                        active_pages
                    )
                )


                # -----------------------------------------
                # 2枚目 厳格項目
                # -----------------------------------------

                strict_items = []


                if file2:

                    strict_data = (
                        strict_read_page2(
                            prepared_images[
                                "2枚目"
                            ]
                        )
                    )


                    strict_items = (
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
                    ][
                        "display_name"
                    ]
                )


                st.image(
                    prepared_images[
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
                        "✅ 書類の種類：正しい書類と判定"
                    )


                elif doc_status == "wrong_document":

                    st.error(
                        "❌ 違う種類の書類がアップロードされている可能性があります。"
                    )


                else:

                    st.warning(
                        "⚠️ 書類の種類を確実に判定できませんでした。"
                    )


                # ---------------------------------------------
                # 画像品質
                # ---------------------------------------------

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


                # ---------------------------------------------
                # 表示する項目を構成
                # ---------------------------------------------

                page_items = list(
                    page[
                        "items"
                    ]
                )


                if page_name == "2枚目":

                    combined = {}


                    # 通常項目
                    for item in page_items:

                        combined[
                            item[
                                "name"
                            ]
                        ] = item


                    # 厳格項目
                    for item in strict_items:

                        combined[
                            item[
                                "name"
                            ]
                        ] = item


                    # 2枚目の表示順
                    wanted_order = [

                        "保護者氏名フリガナ",

                        "保護者氏名",

                        "ご住所・連絡先",

                        "指導対象A",

                        "コース名",

                        "初回指導日",

                        "役務提供期間A",

                        "受領サイン",

                        "数量"
                    ]


                    page_items = []


                    for name in wanted_order:

                        if name in combined:

                            page_items.append(
                                combined[
                                    name
                                ]
                            )


                # ---------------------------------------------
                # 各項目を表示
                # ---------------------------------------------

                for item in page_items:

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
                    "上記の項目を人の目でも確認してください。"
                )


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
