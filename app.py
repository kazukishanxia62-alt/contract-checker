import streamlit as st
from openai import OpenAI
from PIL import Image, ImageOps
import io
import base64
import json
import re


# =========================================================
# 基本設定
# =========================================================

st.set_page_config(
    page_title="契約書 記入漏れチェック",
    page_icon="✅",
    layout="wide"
)

MODEL = "gpt-5.4-mini"
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


# =========================================================
# 画像処理
# =========================================================

def load_image(uploaded_file):
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def image_to_data_url(image):
    buffer = io.BytesIO()

    # 小さい○をできるだけ潰さない
    image.save(
        buffer,
        format="JPEG",
        quality=96,
        subsampling=0
    )

    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


# =========================================================
# OpenAI 呼び出し
# =========================================================

def call_json(images, prompt, schema_name, properties):

    schema = {
        "name": schema_name,
        "strict": True,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys()),
            "additionalProperties": False
        }
    }

    content = [
        {
            "type": "text",
            "text": prompt
        }
    ]

    for index, image in enumerate(images):

        content.append({
            "type": "text",
            "text": f"画像{index + 1}"
        })

        content.append({
            "type": "image_url",
            "image_url": {
                "url": image_to_data_url(image),
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
        response_format={
            "type": "json_schema",
            "json_schema": schema
        }
    )

    return json.loads(
        response.choices[0].message.content
    )


# =========================================================
# 共通Schema
# =========================================================

FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "visible": {
            "type": "boolean"
        },
        "present": {
            "type": "boolean"
        },
        "uncertain": {
            "type": "boolean"
        }
    },
    "required": [
        "visible",
        "present",
        "uncertain"
    ],
    "additionalProperties": False
}


def field_properties(*fields):

    return {
        field: FIELD_SCHEMA
        for field in fields
    }


# =========================================================
# 共通プロンプト
# =========================================================

COMMON_CONTEXT = """
あなたは日本の契約書を提出する直前に、
記入漏れを確認する担当者です。

この仕事の目的は、
契約内容の真偽を審査することではありません。

原則として確認するものは、

・指定欄に手書き記入が存在するか
・指定選択肢に手書きの丸が存在するか

です。


＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
非常に重要な判定原則
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝

1.
印刷済み文字は「記入あり」に含めない。

2.
フリガナについては、
内容が正しいか、氏名と一致するかは確認しない。

指定されたフリガナ欄に
手書き文字が存在すれば記入あり。

3.
会社名についても、
実在性や内容の正しさは確認しない。

会社名欄に手書き記入があればよい。

4.
近くの別欄から内容を補完しない。

5.
周辺の似た数字や文字を
対象欄の記入として扱わない。

6.
対象欄が画像内で確認できなければ
visible=false。

7.
対象欄の位置は分かるが、
手書きの有無を判断できなければ
uncertain=true。

8.
分からないものを
推測でOKにしない。

9.
写真が90度・180度・270度回転していても、
頭の中で正しい向きに直して判断する。

10.
同じ書類の写真が複数ある場合、
最も対象欄が見やすい画像を利用する。


＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
最重要：欄の位置の探し方
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝

対象欄を単独で検索してはいけない。

必ず次の順番で場所を特定する。

① 書類全体の大きな構造
↓
② 対象が入っている大ブロック
↓
③ その上下左右にあるブロック
↓
④ 対象欄の印刷ラベル
↓
⑤ 同じ行の左右関係
↓
⑥ 選択肢の場合は並び順

この位置関係が一致して初めて
その欄だと判断する。

文字認識だけで場所を決めてはいけない。
"""


# =========================================================
# ① クレジット契約書 構造マップ
# =========================================================

PAGE1_MAP = """
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
① クレジット契約書の構造
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝

この用紙は横長。


【左側】

上から順番に

A ご契約者情報

↓

B ご契約者の勤務先情報

↓

C 世帯主・世帯状況

↓

D 関係者情報

↓

E 銀行口座情報


【右側】

上部：
契約・役務関係

中央：
商品（役務）名、数量、金額

下部：
支払情報、購入確認等



＝＝＝＝＝＝＝＝＝＝＝＝
A ご契約者情報
＝＝＝＝＝＝＝＝＝＝＝＝

用紙左上。

氏名
氏名フリガナ
性別
生年月日
ご住所
住所フリガナ
郵便番号
電話番号
携帯電話

などがある。


＝＝＝＝＝＝＝＝＝＝＝＝
B ご契約者勤務先
＝＝＝＝＝＝＝＝＝＝＝＝

Aのすぐ下。

C世帯主・世帯状況より上。

会社名
所在地
郵便番号
業種
雇用形態
勤務年数
給料日
派遣先・出向先

などがある。


【雇用形態】

勤務先ブロック内にある。

選択肢の印刷順は、

1 正社員

2 派遣社員

3 契約社員

4 パート・アルバイト

5 公務員

6 事業者

7 主婦

8 年金

9 学生

この順番。

文字だけで判断せず、
この並びの位置を使う。


例えば、

一番左側の最初の選択肢
＝正社員

その次
＝派遣社員

その次
＝契約社員

という位置関係を使う。


【業種】

同じ勤務先ブロック内。

雇用形態とは別の選択行。

雇用形態の丸を
業種の丸として数えてはいけない。



＝＝＝＝＝＝＝＝＝＝＝＝
C 世帯主・世帯状況
＝＝＝＝＝＝＝＝＝＝＝＝

B勤務先の下。

D関係者情報より上。

ここには、

世帯主
世帯状況
年収
クレジット支払額

などがある。


「世帯主の年収(税込)」

と

「世帯主のクレジットの
月あたりのお支払額」

は全く別の欄。

絶対に混同しない。



＝＝＝＝＝＝＝＝＝＝＝＝
D 関係者情報
＝＝＝＝＝＝＝＝＝＝＝＝

C世帯状況の下。

E銀行口座より上。

このブロック内に、

氏名
氏名フリガナ
性別
生年月日
ご契約者との関係
ご住所
住所郵便番号
電話番号
携帯電話
税込年収
ご住居
雇用形態
勤務年数
給料日
会社名
所在地
所在地郵便番号
所在地電話番号

がある。


同じ名前の項目が
AやBにも存在するので、

必ず

「D 関係者情報の中」

という位置を優先する。



＝＝＝＝＝＝＝＝＝＝＝＝
E 銀行口座
＝＝＝＝＝＝＝＝＝＝＝＝

用紙左下。

ゆうちょ銀行

または

ゆうちょ銀行以外

のどちらかを使用する。

両方記入する必要はない。

口座名義人フリガナは
専用欄で確認する。
"""


# =========================================================
# ② 役務申込書 構造マップ
# =========================================================

PAGE2_MAP = """
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
② 役務申込書・指導内容の構造
＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝

この用紙も横長。


【最上段】

細いヘッダー。


【左上】

お申込者記入欄。


【右上】

指導対象A・B・C
生徒・学校情報。


【左中段から左下】

指導料
コース名
交通費
初回指導日
役務提供期間


【中央から右中央】

教材・数量表。


【右側】

支払方法・金額等。



＝＝＝＝＝＝＝＝＝＝＝＝
保護者・住所
＝＝＝＝＝＝＝＝＝＝＝＝

左上の
「お申込者記入欄」。

保護者氏名
フリガナ
住所
郵便番号
電話番号等。


＝＝＝＝＝＝＝＝＝＝＝＝
指導対象A
＝＝＝＝＝＝＝＝＝＝＝＝

右上。

A
B
C

が上下に並ぶ。

今回確認するのはA。

Aの「有」と、

学校区分の
「公・国・私」

は別の選択項目。


学校区分は
学校名付近の

公・国・私

だけを見る。


＝＝＝＝＝＝＝＝＝＝＝＝
コース名
＝＝＝＝＝＝＝＝＝＝＝＝

左側中央。

印刷された

「コース名」

の右側にある
専用記入欄。

近くにある

4回/月

などは
コース名の記入として扱わない。


＝＝＝＝＝＝＝＝＝＝＝＝
数量表
＝＝＝＝＝＝＝＝＝＝＝＝

中央。

横方向に、

教科・学年等の選択記入欄

↓

数量

↓

各単価

↓

小計

の順に並ぶ。


つまり

数量は
各単価の左。

各単価は
数量の右。

36000等の数字は
通常「各単価」なので、

数量として絶対に使用しない。


＝＝＝＝＝＝＝＝＝＝＝＝
受領サイン
＝＝＝＝＝＝＝＝＝＝＝＝

用紙上部。

印刷された

「受領サイン →」

という文字がある。

対象は

その矢印の直後の欄だけ。

保護者氏名や
担当者氏名を代用しない。
"""


# =========================================================
# ステータス
# =========================================================

def get_status(field):

    if field["uncertain"]:
        return "uncertain"

    if not field["visible"]:
        return "uncertain"

    if field["present"]:
        return "ok"

    return "missing"


def add_result(results, status, name, detail=""):

    results.append({
        "status": status,
        "name": name,
        "detail": detail
    })


def render_results(results):

    priority = {
        "missing": 0,
        "warning": 1,
        "uncertain": 2,
        "ok": 3
    }

    results = sorted(
        results,
        key=lambda x: priority[x["status"]]
    )

    missing = sum(
        x["status"] == "missing"
        for x in results
    )

    warning = sum(
        x["status"] == "warning"
        for x in results
    )

    uncertain = sum(
        x["status"] == "uncertain"
        for x in results
    )

    ok = sum(
        x["status"] == "ok"
        for x in results
    )

    a, b, c, d = st.columns(4)

    a.metric("❌ 未記入", missing)
    b.metric("⚠️ 注意", warning)
    c.metric("🔍 要確認", uncertain)
    d.metric("✅ OK", ok)

    st.divider()

    icons = {
        "missing": "❌",
        "warning": "⚠️",
        "uncertain": "🔍",
        "ok": "✅"
    }

    for item in results:

        text = (
            f"{icons[item['status']]} "
            f"**{item['name']}**"
        )

        if item["detail"]:
            text += f" — {item['detail']}"

        st.markdown(text)


# =========================================================
# 金額
# =========================================================

def parse_money(text):

    text = str(text or "")

    text = (
        text
        .replace(",", "")
        .replace("，", "")
        .replace(" ", "")
        .replace("　", "")
    )

    if not text:
        return None

    man = re.search(
        r"(\d+(?:\.\d+)?)万",
        text
    )

    if man:

        return int(
            float(man.group(1))
            * 10000
        )

    digits = re.sub(
        r"[^\d]",
        "",
        text
    )

    if not digits:
        return None

    return int(digits)


# =========================================================
# ① 判定
# =========================================================

def check_page1(images, relation_required):

    results = []


    # -----------------------------------------------------
    # 契約者 基本情報
    # -----------------------------------------------------

    applicant = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

今回確認するのは
A ご契約者情報だけです。

B勤務先より上のブロックです。

各欄について、
内容の正しさではなく、

その専用欄に
手書き記入が存在するかだけ判定。

住所フリガナは、

氏名フリガナではなく

「ご住所」に対応する
住所フリガナ専用欄だけを見る。

電話番号と携帯電話は
別々に判定する。
""",

        "page1_applicant",

        field_properties(

            "氏名",

            "氏名フリガナ",

            "生年月日",

            "住所",

            "住所フリガナ",

            "郵便番号",

            "固定電話",

            "携帯電話"
        )
    )


    for key in [

        "氏名",

        "氏名フリガナ",

        "生年月日",

        "住所",

        "住所フリガナ",

        "郵便番号"
    ]:

        add_result(
            results,
            get_status(applicant[key]),
            f"ご契約者・{key}"
        )


    # 電話はどちらか一方
    phone = applicant["固定電話"]
    mobile = applicant["携帯電話"]

    if (
        phone["uncertain"]
        or mobile["uncertain"]
    ):

        add_result(
            results,
            "uncertain",
            "ご契約者・連絡先"
        )

    elif (
        phone["present"]
        or mobile["present"]
    ):

        add_result(
            results,
            "ok",
            "ご契約者・連絡先",
            "固定電話または携帯電話あり"
        )

    else:

        add_result(
            results,
            "missing",
            "ご契約者・連絡先",
            "固定電話・携帯電話とも未記入"
        )


    # -----------------------------------------------------
    # 住所 都道府県
    # -----------------------------------------------------

    address = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

対象は

A ご契約者情報の
「ご住所」欄そのもの。

B勤務先より上。

住所の内容全部を読む必要はない。

見るのは、

手書き住所の先頭に

北海道
青森県
東京都
大阪府
京都府

等の

都道府県名が
実際に手書きされているか。

「岡山市」
「大阪市」
「神戸市」

等から

都道府県を推測してはいけない。

印刷された
都・道・府・県

は住所の一部として数えない。
""",

        "page1_address_prefecture",

        {
            "field_visible": {
                "type": "boolean"
            },

            "has_entry": {
                "type": "boolean"
            },

            "prefecture_explicit": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        address["uncertain"]
        or not address["field_visible"]
    ):

        add_result(
            results,
            "uncertain",
            "ご契約者・住所（都道府県）"
        )

    elif not address["has_entry"]:

        add_result(
            results,
            "missing",
            "ご契約者・住所（都道府県）"
        )

    elif address["prefecture_explicit"]:

        add_result(
            results,
            "ok",
            "ご契約者・住所（都道府県）"
        )

    else:

        add_result(
            results,
            "warning",
            "ご契約者・住所（都道府県）",
            "都道府県名から記入されていません"
        )


    # -----------------------------------------------------
    # 勤務先 基本項目
    # -----------------------------------------------------

    work = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

対象は

B ご契約者勤務先。

A契約者情報の下。

C世帯主情報の上。

この位置関係を確認してから、

会社名
所在地
所在地郵便番号
勤務年数
給料日

の専用欄を見る。

関係者情報の会社名・所在地を
間違えて使用しない。
""",

        "page1_work",

        field_properties(

            "会社名",

            "所在地",

            "所在地郵便番号",

            "勤務年数",

            "給料日"
        )
    )


    for key in [

        "会社名",

        "所在地",

        "所在地郵便番号",

        "勤務年数",

        "給料日"
    ]:

        add_result(
            results,
            get_status(work[key]),
            f"ご契約者勤務先・{key}"
        )


    # -----------------------------------------------------
    # 業種
    # -----------------------------------------------------

    industry = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

今回は
「業種」だけを見る。

最重要。

まず、

A契約者情報

↓

B勤務先

↓

C世帯状況

という上下構造を確認する。

そのB勤務先内の

「業種」

という印刷ラベルを確認。

その業種ラベルに対応する
同じ行の選択肢だけを見る。

雇用形態
ご住居
性別
世帯状況
関係者情報

などの丸は
絶対に業種として扱わない。

業種ラベルと
業種選択行の位置関係が
確実に確認できた場合だけ
anchor_verified=true。

その業種選択肢内に
手書きの丸が1個以上あれば
has_circle=true。
""",

        "page1_industry",

        {
            "field_visible": {
                "type": "boolean"
            },

            "anchor_verified": {
                "type": "boolean"
            },

            "has_circle": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        industry["uncertain"]
        or not industry["field_visible"]
        or not industry["anchor_verified"]
    ):

        add_result(
            results,
            "uncertain",
            "ご契約者勤務先・業種"
        )

    elif industry["has_circle"]:

        add_result(
            results,
            "ok",
            "ご契約者勤務先・業種"
        )

    else:

        add_result(
            results,
            "missing",
            "ご契約者勤務先・業種",
            "選択なし"
        )


    # -----------------------------------------------------
    # 雇用形態
    # -----------------------------------------------------

    employment_options = [

        "正社員",

        "派遣社員",

        "契約社員",

        "パート・アルバイト",

        "公務員",

        "事業者",

        "主婦",

        "年金",

        "学生"
    ]


    employment_properties = {

        "field_visible": {
            "type": "boolean"
        },

        "anchor_verified": {
            "type": "boolean"
        },

        "uncertain": {
            "type": "boolean"
        }
    }


    for option in employment_options:

        employment_properties[option] = {

            "type": "object",

            "properties": {

                "position_verified": {
                    "type": "boolean"
                },

                "circled": {
                    "type": "boolean"
                }
            },

            "required": [
                "position_verified",
                "circled"
            ],

            "additionalProperties": False
        }


    employment = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

今回は

B ご契約者勤務先の
「雇用形態」

だけを見る。


まず、

A契約者情報より下

C世帯主情報より上

という位置関係から
B勤務先を特定。


その中の
「雇用形態」の行を特定。


重要：

印刷文字をOCRして
選択肢を推測するだけではなく、

各選択肢の
相対位置を使う。


印刷順は、

正社員
↓
派遣社員
↓
契約社員
↓
パート・アルバイト
↓
公務員
↓
事業者
↓
主婦
↓
年金
↓
学生


実際には横並び・複数段でも、

この印刷順と位置関係を使う。


それぞれの選択肢について、

その選択肢そのものを
囲む・重なる

手書きの丸がある場合だけ

circled=true。


隣の選択肢の丸を
移動して解釈しない。


特に、

派遣社員

と

契約社員

は隣接しているため、

丸の中心位置が
どちらの印刷文字に対応しているかを
必ず位置で判断する。
""",

        "page1_employment",

        employment_properties
    )


    selected = []


    for option in employment_options:

        if (
            employment[option]["position_verified"]
            and employment[option]["circled"]
        ):

            selected.append(option)


    if (
        employment["uncertain"]
        or not employment["field_visible"]
        or not employment["anchor_verified"]
    ):

        add_result(
            results,
            "uncertain",
            "ご契約者勤務先・雇用形態"
        )


    elif len(selected) == 0:

        add_result(
            results,
            "missing",
            "ご契約者勤務先・雇用形態",
            "選択なし"
        )


    elif len(selected) > 1:

        add_result(
            results,
            "warning",
            "ご契約者勤務先・雇用形態",
            "複数選択：" + " / ".join(selected)
        )


    else:

        add_result(
            results,
            "ok",
            "ご契約者勤務先・雇用形態",
            selected[0]
        )


    # -----------------------------------------------------
    # 派遣先
    # -----------------------------------------------------

    if (
        len(selected) == 1
        and selected[0] == "派遣社員"
    ):

        dispatch = call_json(

            images,

            COMMON_CONTEXT
            + PAGE1_MAP
            + """

対象は

B勤務先の

「派遣先・出向先の会社名」

という専用欄。

通常の会社名欄を
代用しない。

内容の正しさは不要。

専用欄に
手書きがあれば present=true。
""",

            "page1_dispatch",

            field_properties(
                "派遣先会社名"
            )
        )


        add_result(
            results,
            get_status(
                dispatch["派遣先会社名"]
            ),
            "ご契約者勤務先・派遣先/出向先会社名"
        )


    # -----------------------------------------------------
    # 世帯主 クレジット月額
    # -----------------------------------------------------

    household = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

対象は

C 世帯主・世帯状況。


その中の

「世帯主のクレジットの
月あたりのお支払額」

という専用欄だけを読む。


非常に重要。


近くにある

「世帯主の年収(税込)」

は絶対に使わない。


例えば、

年収欄に
400万円

と書かれていて、

月額支払額欄が空欄なら、

月額支払額は
未記入。


400万円を
月額として返してはいけない。


amount_textには

月額支払欄そのものに
書かれている数字だけを返す。

空欄なら空文字。
""",

        "page1_household",

        {
            "field_visible": {
                "type": "boolean"
            },

            "has_entry": {
                "type": "boolean"
            },

            "amount_text": {
                "type": "string"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        household["uncertain"]
        or not household["field_visible"]
    ):

        add_result(
            results,
            "uncertain",
            "世帯主・クレジット月額"
        )


    elif not household["has_entry"]:

        add_result(
            results,
            "missing",
            "世帯主・クレジット月額"
        )


    else:

        amount = parse_money(
            household["amount_text"]
        )


        if amount is None:

            add_result(
                results,
                "uncertain",
                "世帯主・クレジット月額"
            )


        elif amount > 100000:

            add_result(
                results,
                "warning",
                "世帯主・クレジット月額",
                f"{amount:,}円（10万円超）"
            )


        else:

            add_result(
                results,
                "ok",
                "世帯主・クレジット月額",
                f"{amount:,}円"
            )


    # -----------------------------------------------------
    # 関係者情報
    # -----------------------------------------------------

    if relation_required:

        relation = call_json(

            images,

            COMMON_CONTEXT
            + PAGE1_MAP
            + """

今回は

D 関係者情報だけ。


C世帯主情報の下。

E銀行口座の上。


この位置関係を確認する。


A契約者情報や
B勤務先情報から

同名項目を流用しない。


住所と所在地については、

実際の住所

または

「同上」

と書かれていれば
present=true。


電話番号と携帯電話は
別々に判定する。
""",

            "page1_relation",

            field_properties(

                "氏名",

                "氏名フリガナ",

                "性別",

                "生年月日",

                "契約者との関係",

                "住所",

                "住所郵便番号",

                "固定電話",

                "携帯電話",

                "税込年収",

                "ご住居",

                "勤務年数",

                "給料日",

                "会社名",

                "所在地",

                "所在地郵便番号",

                "所在地電話番号"
            )
        )


        relation_labels = {

            "氏名":
                "関係者情報・氏名",

            "氏名フリガナ":
                "関係者情報・氏名フリガナ",

            "性別":
                "関係者情報・性別",

            "生年月日":
                "関係者情報・生年月日",

            "契約者との関係":
                "関係者情報・ご契約者との関係",

            "住所":
                "関係者情報・ご住所",

            "住所郵便番号":
                "関係者情報・ご住所の郵便番号",

            "税込年収":
                "関係者情報・税込年収",

            "ご住居":
                "関係者情報・ご住居",

            "勤務年数":
                "関係者情報・勤務年数",

            "給料日":
                "関係者情報・給料日",

            "会社名":
                "関係者情報・会社名",

            "所在地":
                "関係者情報・所在地",

            "所在地郵便番号":
                "関係者情報・所在地の郵便番号",

            "所在地電話番号":
                "関係者情報・所在地の電話番号"
        }


        for key, label in relation_labels.items():

            add_result(
                results,
                get_status(
                    relation[key]
                ),
                label
            )


        # 関係者の連絡先

        r_phone = relation["固定電話"]
        r_mobile = relation["携帯電話"]


        if (
            r_phone["uncertain"]
            or r_mobile["uncertain"]
        ):

            add_result(
                results,
                "uncertain",
                "関係者情報・連絡先"
            )


        elif (
            r_phone["present"]
            or r_mobile["present"]
        ):

            add_result(
                results,
                "ok",
                "関係者情報・連絡先",
                "固定電話または携帯電話あり"
            )


        else:

            add_result(
                results,
                "missing",
                "関係者情報・連絡先"
            )


        # 関係者 雇用形態

        relation_employment = call_json(

            images,

            COMMON_CONTEXT
            + PAGE1_MAP
            + """

今回は

D 関係者情報の
「雇用形態」だけ。


Bご契約者勤務先の
雇用形態ではない。


C世帯主情報より下。

E銀行口座より上。


関係者氏名・住所・電話の
下側にある

関係者用の雇用形態を探す。


印刷順は

正社員
派遣社員
契約社員
パート・アルバイト
公務員
事業者
主婦
年金
学生


各選択肢に
直接対応する丸だけを見る。
""",

            "page1_relation_employment",

            employment_properties
        )


        relation_selected = []


        for option in employment_options:

            if (
                relation_employment[option][
                    "position_verified"
                ]
                and relation_employment[option][
                    "circled"
                ]
            ):

                relation_selected.append(option)


        if (
            relation_employment["uncertain"]
            or not relation_employment[
                "field_visible"
            ]
            or not relation_employment[
                "anchor_verified"
            ]
        ):

            add_result(
                results,
                "uncertain",
                "関係者情報・雇用形態"
            )


        elif len(relation_selected) == 0:

            add_result(
                results,
                "missing",
                "関係者情報・雇用形態"
            )


        elif len(relation_selected) > 1:

            add_result(
                results,
                "warning",
                "関係者情報・雇用形態",
                "複数選択"
            )


        else:

            add_result(
                results,
                "ok",
                "関係者情報・雇用形態",
                relation_selected[0]
            )


    # -----------------------------------------------------
    # 銀行
    # -----------------------------------------------------

    bank = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

対象は

E 銀行口座。

用紙左下。


ゆうちょ銀行

と

ゆうちょ銀行以外

は別エリア。


どちらか一方に
必要な手書き記入が存在すればよい。


両方必須ではない。


口座名義人フリガナは
専用のフリガナ欄だけを見る。
""",

        "page1_bank",

        {
            "area_visible": {
                "type": "boolean"
            },

            "yucho_has_entry": {
                "type": "boolean"
            },

            "other_bank_has_entry": {
                "type": "boolean"
            },

            "account_holder_furigana": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        bank["uncertain"]
        or not bank["area_visible"]
    ):

        add_result(
            results,
            "uncertain",
            "銀行口座"
        )

        add_result(
            results,
            "uncertain",
            "口座名義人フリガナ"
        )


    else:

        if (
            bank["yucho_has_entry"]
            or bank["other_bank_has_entry"]
        ):

            add_result(
                results,
                "ok",
                "銀行口座"
            )

        else:

            add_result(
                results,
                "missing",
                "銀行口座"
            )


        if bank[
            "account_holder_furigana"
        ]:

            add_result(
                results,
                "ok",
                "口座名義人フリガナ"
            )

        else:

            add_result(
                results,
                "missing",
                "口座名義人フリガナ"
            )


    # -----------------------------------------------------
    # 契約情報
    # -----------------------------------------------------

    contract_info = call_json(

        images,

        COMMON_CONTEXT
        + PAGE1_MAP
        + """

右側の契約情報部分。


確認対象は正確に

1
「役務提供期間」

2
「特定商取引法第42条第2項
又は第3項書面の受領年月日」

の2つ。


似た日付欄を
代わりに使用しない。


年・月・日の専用欄に
手書きが存在するか確認。
""",

        "page1_contract_info",

        field_properties(

            "役務提供期間",

            "法定書面受領年月日"
        )
    )


    add_result(
        results,
        get_status(
            contract_info["役務提供期間"]
        ),
        "役務提供期間"
    )


    add_result(
        results,
        get_status(
            contract_info[
                "法定書面受領年月日"
            ]
        ),
        "特定商取引法42条書面・受領年月日"
    )


    return results


# =========================================================
# ② 判定
# =========================================================

def check_page2(images):

    results = []


    # -----------------------------------------------------
    # 保護者・住所
    # -----------------------------------------------------

    guardian = call_json(

        images,

        COMMON_CONTEXT
        + PAGE2_MAP
        + """

対象は左上の

お申込者記入欄。


保護者氏名フリガナは、

保護者氏名の近くにある
専用フリガナ欄。


内容一致は不要。


住所は、

手書き住所の先頭に
都道府県名が実際にあるか。


市区町村名から
推測しない。


さらに、

住所欄に印刷された

都
道
府
県

のうち、

該当箇所に
手書きの丸・選択印があるかも
別々に確認。
""",

        "page2_guardian",

        {
            "guardian_furigana":
                FIELD_SCHEMA,

            "address_visible": {
                "type": "boolean"
            },

            "address_has_entry": {
                "type": "boolean"
            },

            "prefecture_explicit": {
                "type": "boolean"
            },

            "todofuken_mark_present": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    add_result(
        results,
        get_status(
            guardian[
                "guardian_furigana"
            ]
        ),
        "保護者氏名・フリガナ"
    )


    if (
        guardian["uncertain"]
        or not guardian["address_visible"]
    ):

        add_result(
            results,
            "uncertain",
            "ご住所・都道府県名"
        )

        add_result(
            results,
            "uncertain",
            "ご住所・都/道/府/県の丸"
        )


    elif not guardian[
        "address_has_entry"
    ]:

        add_result(
            results,
            "missing",
            "ご住所・都道府県名"
        )

        add_result(
            results,
            "missing",
            "ご住所・都/道/府/県の丸"
        )


    else:

        add_result(
            results,
            (
                "ok"
                if guardian[
                    "prefecture_explicit"
                ]
                else "warning"
            ),
            "ご住所・都道府県名"
        )

        add_result(
            results,
            (
                "ok"
                if guardian[
                    "todofuken_mark_present"
                ]
                else "missing"
            ),
            "ご住所・都/道/府/県の丸"
        )


    # -----------------------------------------------------
    # 指導対象A・公国私
    # -----------------------------------------------------

    school = call_json(

        images,

        COMMON_CONTEXT
        + PAGE2_MAP
        + """

対象は右上の

指導対象A。


まずA・B・Cのうち
一番上のAを特定。


確認項目1

指導対象Aの
「有」

に丸があるか。


確認項目2

Aの学校名付近にある

公
国
私

のそれぞれに
丸があるか。


性別の丸

有無の別の丸

B/Cの丸

などを

公・国・私として
絶対に数えない。
""",

        "page2_school",

        {
            "anchor_verified": {
                "type": "boolean"
            },

            "target_a_yes": {
                "type": "boolean"
            },

            "public": {
                "type": "boolean"
            },

            "national": {
                "type": "boolean"
            },

            "private": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        school["uncertain"]
        or not school[
            "anchor_verified"
        ]
    ):

        add_result(
            results,
            "uncertain",
            "指導対象A・有"
        )

        add_result(
            results,
            "uncertain",
            "学校区分・公/国/私"
        )


    else:

        add_result(
            results,
            (
                "ok"
                if school[
                    "target_a_yes"
                ]
                else "missing"
            ),
            "指導対象A・有"
        )


        school_count = sum([

            school["public"],

            school["national"],

            school["private"]
        ])


        if school_count == 1:

            add_result(
                results,
                "ok",
                "学校区分・公/国/私"
            )


        elif school_count == 0:

            add_result(
                results,
                "missing",
                "学校区分・公/国/私",
                "選択なし"
            )


        else:

            add_result(
                results,
                "warning",
                "学校区分・公/国/私",
                "複数選択"
            )


    # -----------------------------------------------------
    # コース名・初回・期間
    # -----------------------------------------------------

    course = call_json(

        images,

        COMMON_CONTEXT
        + PAGE2_MAP
        + """

対象は左側中央の

役務提供内容。


「コース名」

という印刷ラベルを探し、

その右側の
専用記入欄だけを見る。


コース名欄に、

「週1」

があるか。


さらに

「90分」

があるか。


近くにある

4回/月

料金

回数

などは絶対に
コース名として使わない。


また、

初回指導日

と

役務提供期間A

の専用欄について

手書きがあるか確認。


B・Cの期間は
対象外。
""",

        "page2_course",

        {
            "course_visible": {
                "type": "boolean"
            },

            "course_has_entry": {
                "type": "boolean"
            },

            "has_week1": {
                "type": "boolean"
            },

            "has_90min": {
                "type": "boolean"
            },

            "course_uncertain": {
                "type": "boolean"
            },

            "initial_date":
                FIELD_SCHEMA,

            "service_period_a":
                FIELD_SCHEMA
        }
    )


    if (
        course["course_uncertain"]
        or not course[
            "course_visible"
        ]
    ):

        add_result(
            results,
            "uncertain",
            "コース名"
        )


    elif not course[
        "course_has_entry"
    ]:

        add_result(
            results,
            "missing",
            "コース名"
        )


    elif (
        course["has_week1"]
        and course["has_90min"]
    ):

        add_result(
            results,
            "ok",
            "コース名",
            "週1・90分あり"
        )


    else:

        missing_items = []

        if not course["has_week1"]:

            missing_items.append(
                "週1"
            )

        if not course["has_90min"]:

            missing_items.append(
                "90分"
            )

        add_result(
            results,
            "warning",
            "コース名",
            "不足：" + "・".join(
                missing_items
            )
        )


    add_result(
        results,
        get_status(
            course["initial_date"]
        ),
        "初回指導日"
    )


    add_result(
        results,
        get_status(
            course[
                "service_period_a"
            ]
        ),
        "役務提供期間A"
    )


    # -----------------------------------------------------
    # 受領サイン
    # -----------------------------------------------------

    receipt = call_json(

        images,

        COMMON_CONTEXT
        + PAGE2_MAP
        + """

今回は
受領サインだけ。

まず用紙上部で

「受領サイン →」

という印刷文字を
実際に確認。


その矢印の
直後にある記入欄だけを見る。


他の場所の

保護者氏名

指導対象氏名

担当者名

販売店担当者名

などは

受領サインとして
絶対に使わない。


「受領サイン →」

というアンカー自体を
見つけられなければ

anchor_visible=false。
""",

        "page2_receipt",

        {
            "anchor_visible": {
                "type": "boolean"
            },

            "signature_present": {
                "type": "boolean"
            },

            "uncertain": {
                "type": "boolean"
            }
        }
    )


    if (
        receipt["uncertain"]
        or not receipt[
            "anchor_visible"
        ]
    ):

        add_result(
            results,
            "uncertain",
            "受領サイン"
        )


    elif receipt[
        "signature_present"
    ]:

        add_result(
            results,
            "ok",
            "受領サイン"
        )


    else:

        add_result(
            results,
            "missing",
            "受領サイン"
        )


    # -----------------------------------------------------
    # 数量
    # -----------------------------------------------------

    quantity = call_json(

        images,

        COMMON_CONTEXT
        + PAGE2_MAP
        + """

対象は中央の教材・数量表。


最重要。


まず列の位置関係を確認。


左側：

学年・教科等の
横方向の記入欄


その右：

「数量」


さらに右：

「各単価」


さらに右：

「小計」


つまり、

数量列は
各単価列の左。


各行について、

数量列より左側にある

手書き整数だけを

horizontal_values

に入れる。


そして

「数量」

という印刷列の
真下・同じ行にあるセルだけを

written_quantity

として読む。


数量セルが空欄なら、

横の数字を足して
勝手に数量を書いてはいけない。


空文字を返す。


絶対禁止：

12000
24000
36000
48000
108000
648000
712800

など、

各単価
小計
合計

の金額を
written_quantity に入れない。


数量列より右側は
数量判定では使用禁止。


対象行についてのみ返す。

行を確定できなければ
table_uncertain=true。
""",

        "page2_quantity",

        {
            "table_visible": {
                "type": "boolean"
            },

            "table_uncertain": {
                "type": "boolean"
            },

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

                        "quantity_has_handwriting": {
                            "type": "boolean"
                        }
                    },

                    "required": [

                        "row_label",

                        "horizontal_values",

                        "written_quantity",

                        "quantity_has_handwriting"
                    ],

                    "additionalProperties": False
                }
            }
        }
    )


    if (
        quantity[
            "table_uncertain"
        ]
        or not quantity[
            "table_visible"
        ]
    ):

        add_result(
            results,
            "uncertain",
            "数量"
        )


    elif len(
        quantity["rows"]
    ) == 0:

        add_result(
            results,
            "uncertain",
            "数量",
            "対象行を特定できません"
        )


    else:

        missing_rows = []

        warning_rows = []

        uncertain_rows = []


        for row in quantity[
            "rows"
        ]:

            expected = sum(
                row[
                    "horizontal_values"
                ]
            )


            written = parse_money(
                row[
                    "written_quantity"
                ]
            )


            if not row[
                "quantity_has_handwriting"
            ]:

                missing_rows.append(
                    f"{row['row_label']}：数量欄未記入"
                )

                continue


            if written is None:

                uncertain_rows.append(
                    f"{row['row_label']}：読取不可"
                )

                continue


            # 金額誤読の安全弁
            if written >= 1000:

                uncertain_rows.append(
                    f"{row['row_label']}：{written}は金額誤読の可能性"
                )

                continue


            if written != expected:

                warning_rows.append(
                    f"{row['row_label']}：横合計{expected} / 数量{written}"
                )


        if missing_rows:

            add_result(
                results,
                "missing",
                "数量",
                " / ".join(
                    missing_rows
                )
            )


        elif warning_rows:

            add_result(
                results,
                "warning",
                "数量",
                " / ".join(
                    warning_rows
                )
            )


        elif uncertain_rows:

            add_result(
                results,
                "uncertain",
                "数量",
                " / ".join(
                    uncertain_rows
                )
            )


        else:

            add_result(
                results,
                "ok",
                "数量",
                "各行の横合計と一致"
            )


    return results


# =========================================================
# UI
# =========================================================

st.title(
    "契約書 記入漏れチェック"
)

st.caption(
    "書類の構造・上下左右の位置関係・選択肢の並び順を使って判定します。"
)


st.info(
    "①は1〜2枚、②は1枚で使用できます。"
    " 写真アプリのスクリーンショットではなく、"
    "できるだけ元のカメラ写真を使ってください。"
)


col1, col2 = st.columns(2)


with col1:

    st.subheader(
        "① クレジット契約書"
    )

    page1_files = st.file_uploader(

        "①の写真",

        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ],

        accept_multiple_files=True,

        key="page1"
    )


    relation_required = st.checkbox(

        "関係者情報をチェックする",

        value=True,

        help=(
            "関係者情報が今回の契約で"
            "対象外ならOFF"
        )
    )


with col2:

    st.subheader(
        "② 役務申込書・指導内容"
    )

    page2_files = st.file_uploader(

        "②の写真",

        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ],

        accept_multiple_files=True,

        key="page2"
    )


# =========================================================
# プレビュー
# =========================================================

if page1_files:

    st.write(
        "### ① プレビュー"
    )

    preview = [
        load_image(file)
        for file in page1_files
    ]

    st.image(
        preview,
        width=350
    )


if page2_files:

    st.write(
        "### ② プレビュー"
    )

    preview = [
        load_image(file)
        for file in page2_files
    ]

    st.image(
        preview,
        width=500
    )


# =========================================================
# 実行
# =========================================================

run = st.button(

    "契約書を一括チェック",

    type="primary",

    use_container_width=True
)


if run:

    if (
        not page1_files
        and not page2_files
    ):

        st.error(
            "写真を入れてください。"
        )

        st.stop()


    if (
        page1_files
        and len(page1_files) > 2
    ):

        st.error(
            "①は1〜2枚にしてください。"
        )

        st.stop()


    if (
        page2_files
        and len(page2_files) > 1
    ):

        st.error(
            "②は1枚にしてください。"
        )

        st.stop()


    all_results = []


    try:


        # =============================================
        # ①
        # =============================================

        if page1_files:

            with st.spinner(
                "① クレジット契約書を確認中..."
            ):

                page1_images = [

                    load_image(file)

                    for file
                    in page1_files
                ]


                page1_results = check_page1(

                    page1_images,

                    relation_required
                )


            st.header(
                "① クレジット契約書"
            )


            render_results(
                page1_results
            )


            for result in page1_results:

                all_results.append(
                    ("①", result)
                )


        # =============================================
        # ②
        # =============================================

        if page2_files:

            with st.spinner(
                "② 役務申込書・指導内容を確認中..."
            ):

                page2_images = [

                    load_image(file)

                    for file
                    in page2_files
                ]


                page2_results = check_page2(
                    page2_images
                )


            st.header(
                "② 役務申込書・指導内容"
            )


            render_results(
                page2_results
            )


            for result in page2_results:

                all_results.append(
                    ("②", result)
                )


        # =============================================
        # 全体結果
        # =============================================

        problem_results = [

            item

            for item in all_results

            if item[1]["status"]
            in [
                "missing",
                "warning",
                "uncertain"
            ]
        ]


        st.divider()


        if len(
            problem_results
        ) == 0:

            st.success(
                "チェック対象はすべてOKです。"
                " 最終提出前は人の目でも確認してください。"
            )


        else:

            st.warning(
                f"未記入・注意・要確認が "
                f"{len(problem_results)}件あります。"
            )


    except Exception as e:

        st.error(
            "判定中にエラーが発生しました。"
        )

        st.exception(e)
