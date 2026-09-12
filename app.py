import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
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
    "契約書の写真をAIが確認し、"
    "記入漏れ・条件違反・要注意項目をチェックします。"
)

st.warning(
    "これは提出前の補助チェック用です。最終確認は人が行ってください。"
    "実際の顧客契約書を扱う前に、会社の情報セキュリティ・"
    "個人情報取扱ルールを確認してください。"
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
# 書類の説明
# =========================================================

DOCUMENT_INFO = {

    "1枚目": {
        "display_name": "① クレジット申込書",

        "description":
        "「クレジットお申込の内容」があり、"
        "申込者情報・勤務先・世帯状況・関係者情報・"
        "クレジット支払内容・銀行口座などが載っている書類",

        "landmarks":
        """
        ・「クレジットお申込の内容」という大きな見出しがある
        ・お申込者情報、勤務先、世帯状況、関係者情報がある
        ・下部にゆうちょ銀行／ゆうちょ銀行以外の銀行の欄がある
        """
    },

    "2枚目": {
        "display_name": "② 役務申込書・指導内容",

        "description":
        "保護者氏名・指導対象A/B/C・コース名・"
        "初回指導日・役務提供期間・商品数量などが載っている書類",

        "landmarks":
        """
        ・右上付近に「指導対象」A・B・Cがある
        ・左下付近に「コース名」「初回指導日」「役務提供期間」がある
        ・中央付近に商品名・数量・金額の大きな表がある
        ・受領サイン欄がある
        """
    }
}


# =========================================================
# チェック項目
# =========================================================

CHECK_ITEMS = {

    # =====================================================
    # 1枚目：クレジット申込書
    # =====================================================

    "1枚目": [

        (
            "お申込年月日",
            """
            書類上部の「お申込年月日」を確認する。
            年・月・日が必要な箇所まで記入されていること。
            """
        ),

        (
            "申込者フリガナ",
            """
            申込者本人の氏名に対応する「フリガナ」欄だけを見る。
            他のフリガナを代用してはいけない。
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
            申込者本人の生年月日の年・月・日を確認する。
            """
        ),

        (
            "申込者住所",
            """
            お申込者の「ご住所」欄を確認する。

            都道府県まで記入されていること。

            さらに印刷されている
            「都・道・府・県」
            の正しいものに○が付いていること。

            例：
            東京＋都 → OK
            北海道＋道 → OK
            大阪＋府 → OK
            京都＋府 → OK
            兵庫＋県 → OK

            都道府県は書いてあるが○がない → missing

            大阪なのに「県」へ○など、
            都道府県と○が不一致 → warning
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
            勤務先の電話番号欄に電話番号が記入されているか確認する。
            """
        ),

        (
            "雇用形態",
            """
            雇用形態の選択肢のいずれかに○が付いているか確認する。
            """
        ),

        (
            "派遣先・出向先",
            """
            雇用形態と連動して判定する。

            「派遣社員」に○がある場合のみ
            「派遣先・出向先の会社名」が必須。

            派遣社員＋派遣先会社名あり → ok

            派遣社員＋派遣先会社名なし → missing

            派遣社員ではない →
            派遣先・出向先が空欄でも問題ないため
            not_applicable。
            """
        ),

        (
            "世帯主の確認",
            """
            「世帯主の確認」欄について、
            1. お申込者
            2. 他
            など必要な選択がされているか確認する。

            重要：
            「世帯主の確認」の右側にある
            「連絡先」欄は空欄でもよい。

            連絡先が空欄であることを理由に
            missingにしてはいけない。
            """
        ),

        (
            "世帯状況",
            """
            縦書きで「世帯状況」と書かれた部分を確認する。

            必要な世帯主情報が記入されているか確認する。
            """
        ),

        (
            "世帯主クレジット月額",
            """
            「世帯状況」欄にある

            「世帯主のクレジットの月あたりのお支払額」

            の金額を読む。

            100,000円以下 → ok

            100,000円を超える → warning

            warningの場合、
            reasonに
            「月あたりのお支払額が10万円を超えているため要注意」
            と書く。

            observed_valueには読み取った金額を書く。
            """
        ),

        (
            "関係者情報",
            """
            縦書きで「関係者情報」と書かれた欄を見る。

            申込者が夫の場合 → 妻の情報

            申込者が妻の場合 → 夫の情報

            を記入する欄として確認する。

            配偶者がいるのに必要な配偶者情報がない →
            missing。

            明らかに対象外の場合 →
            not_applicable。

            他の人物の情報を代用しない。
            """
        ),

        (
            "クレジット側役務提供期間",
            """
            クレジット申込書側にある
            「役務提供期間」
            または
            「役務提供期間（権利の移転時期）」
            の指定欄を確認する。

            必要な期間・年月等が記入されていること。

            他の日付や期間を代用しない。
            """
        ),

        (
            "特定商取引法42条受領年月日",
            """
            右上付近の

            「特定商取引法第42条第2項、
            又は第3項書面の受領年月日」

            の欄だけを見る。

            年・月・日がすべて記入 → ok

            年・月・日の一部がない → missing

            他の年月日を絶対に代用しない。
            """
        ),

        (
            "支払ヶ月",
            """
            指定されている「ヶ月」欄だけを見る。

            月数が記入されていること。

            書類内の別の数字、
            支払回数、
            年月日、
            金額などを代用してはいけない。
            """
        ),

        (
            "銀行口座",
            """
            書類最下部の銀行口座欄を見る。

            左側：
            ゆうちょ銀行

            右側：
            ゆうちょ銀行以外の銀行

            どちらか片方に必要事項が記入されていればOK。

            ゆうちょのみ記入 → ok

            その他銀行のみ記入 → ok

            両方空欄 → missing

            両方書く必要はない。
            """
        ),

        (
            "口座名義人フリガナ",
            """
            書類最下部付近の
            「口座名義人」の「フリガナ」欄を見る。

            使用している銀行口座に対応する
            口座名義人フリガナが記入されていること。

            他のフリガナを代用しない。
            """
        ),

    ],


    # =====================================================
    # 2枚目：役務申込書・指導内容
    # =====================================================

    "2枚目": [

        (
            "保護者氏名フリガナ",
            """
            「保護者氏名」に対応する
            フリガナ欄だけを確認する。

            他の人のフリガナを使ってはいけない。
            """
        ),

        (
            "保護者氏名",
            """
            「保護者氏名」欄に
            氏名が記入されているか確認する。
            """
        ),

        (
            "ご住所・連絡先",
            """
            保護者等の「ご住所・連絡先」の
            住所欄を確認する。

            都道府県まで記入されていること。

            さらに
            「都・道・府・県」
            の適切なものに○があること。

            例：

            東京＋都 → OK
            北海道＋道 → OK
            大阪＋府 → OK
            京都＋府 → OK
            兵庫＋県 → OK

            都道府県名はあるが○なし → missing

            ○だけあり住所なし → missing

            都道府県と○が不一致 → warning
            """
        ),

        (
            "指導対象A",
            """
            右上の
            「指導対象」
            A・B・Cのうち、

            Aを確認する。

            Aの「有」に○が付いていること。

            有に○ → ok

            有に○なし → missing

            写真から判別できない → uncertain

            B・Cはこの項目では判定しない。
            """
        ),

        (
            "コース名",
            """
            左下付近にある
            「コース名」の右側の記入欄を見る。

            この欄には
            「週1 90分」
            のような内容が入る。

            欄に記入あり → ok

            空欄 → missing

            別の場所にある
            「週1」「90分」などを代用しない。
            """
        ),

        (
            "初回指導日",
            """
            左下付近の
            「指導料・交通費について」
            の中にある

            「初回指導日」

            を確認する。

            必要な年月日が記入されていること。

            他の日付を代用しない。
            """
        ),

        (
            "役務提供期間A",
            """
            左下付近の
            「役務提供期間」
            を確認する。

            Aの行だけを判定対象とする。

            Aが必要事項まで埋まっている → ok

            Aが空欄または必要部分が欠けている → missing

            Bは空欄でも問題ない。

            Bが空欄であることを理由に
            missingにしてはいけない。
            """
        ),

        (
            "受領サイン",
            """
            この2枚目の書類にある
            受領サイン・受領確認の署名欄を見る。

            手書きの署名または記名があれば → ok

            空欄 → missing

            黒ペンでも問題ない。

            印刷された文字だけでは
            記入済みにしてはいけない。
            """
        ),

        (
            "数量計",
            """
            この2枚目の中央付近にある
            商品・役務・教材等の表を確認する。

            必ず次の手順で判定する。

            1.
            商品表の「数量」欄に
            実際に記入されている数量をすべて読む。

            2.
            それらを全部足す。

            3.
            表にある「数量計」の数字を読む。

            4.
            計算した数量合計と
            「数量計」の記入値を比較する。


            例：

            数量欄
            3
            3

            なら

            3 + 3 = 6

            数量計が6なら → ok

            数量計が空欄 → missing

            数量計が5など不一致 → warning


            最重要：

            「金額」
            「税込金額」
            「単価」
            「小計」
            「商品定価合計」
            「申込合計額」
            「頭金」
            「支払額」

            などの金額を
            数量として絶対に使用しない。

            observed_valueには可能なら

            「3 + 3 = 6 / 数量計 6」

            のように書く。
            """
        ),

        (
            "その他必須記入欄",
            """
            この2枚目について、

            「※」などで明らかに必須と示されている欄や、
            明らかに必要な主要記入欄で、

            上記チェック項目に含まれていない
            重大な記入漏れがないか確認する。

            ただし、

            条件付きの欄
            任意欄
            対象外の欄

            を勝手にmissingにしてはいけない。

            判断できない場合は
            uncertain。
            """
        ),

    ]
}


# =========================================================
# 画像処理
# =========================================================

def image_to_data_url(uploaded):

    img = Image.open(uploaded)

    img = ImageOps.exif_transpose(img).convert("RGB")

    # 細かい文字を読むため少し高め
    max_side = 2800

    if max(img.size) > max_side:

        ratio = max_side / max(img.size)

        img = img.resize(
            (
                int(img.width * ratio),
                int(img.height * ratio)
            )
        )

    buf = BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=92
    )

    b64 = base64.b64encode(
        buf.getvalue()
    ).decode("utf-8")

    return (
        f"data:image/jpeg;base64,{b64}",
        img
    )


# =========================================================
# JSON Schema
# =========================================================

def make_schema(active_pages):

    # 今回アップロードされたページの項目だけ候補にする
    active_names = []

    for page_name in active_pages:

        for name, _ in CHECK_ITEMS[page_name]:

            if name not in active_names:
                active_names.append(name)

    return {

        "type": "json_schema",

        "json_schema": {

            "name": "contract_check",

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

                                "document_type_reason": {
                                    "type": "string"
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
                                                "enum": active_names
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
                                "document_type_reason",
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
# AIチェック
# =========================================================

def check_with_ai(files):

    active_pages = [
        page_name
        for page_name, uploaded in files.items()
        if uploaded is not None
    ]

    content = []

    previews = {}

    checklist_sections = []


    for page_name in active_pages:

        uploaded = files[page_name]

        data_url, preview = image_to_data_url(uploaded)

        previews[page_name] = preview


        item_text = "\n".join(
            [
                f"""
■ {name}

{description}
"""
                for name, description in CHECK_ITEMS[page_name]
            ]
        )


        checklist_sections.append(
            f"""
==================================================
【{page_name}】
{DOCUMENT_INFO[page_name]["display_name"]}
==================================================

想定する書類：

{DOCUMENT_INFO[page_name]["description"]}

書類を見分ける特徴：

{DOCUMENT_INFO[page_name]["landmarks"]}


チェック項目：

{item_text}
"""
        )


        content.append(
            {
                "type": "text",
                "text":
                f"次の画像はユーザーが【{page_name}】としてアップロードした画像です。"
            }
        )

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": data_url,
                    "detail": "high"
                }
            }
        )


    checklist_text = "\n".join(checklist_sections)


    prompt = f"""
あなたは日本語契約書の提出前チェック担当です。

ユーザーがアップロードした画像を確認してください。


{checklist_text}


==================================================
絶対ルール
==================================================

【1】

ページごとのチェック項目を絶対に混ぜないでください。

「1枚目」の項目は
1枚目だけで判定してください。

「2枚目」の項目は
2枚目だけで判定してください。


例えば、

受領サイン

数量計

は2枚目の項目です。

1枚目の項目として返してはいけません。


【2】

今回アップロードされていないページについては、
結果を一切返さないでください。

例えば、

2枚目だけアップロードされた場合は

2枚目の結果だけを返してください。

1枚目の項目を
not_applicableとして並べることも禁止です。


【3】

まず画像が想定している書類か確認してください。

想定した書類なら

document_type_status = match

違う書類なら

wrong_document

確信できない場合は

uncertain

にしてください。


【4】

印刷されている文字だけでは
記入済みにしないでください。

手書き、
○、
署名、
押印、
入力数字

などを確認してください。


【5】

各項目は指定された場所だけを見ます。

別の場所にある

名前
数字
カタカナ
年月日
金額

を勝手に代用してはいけません。


【6】

問題なし →

ok


本来必要なのに未記入 →

missing


記入はあるが、
条件違反や不一致 →

warning


画像から判断できない →

uncertain


条件上そもそも不要 →

not_applicable


【7】

自信がない場合は
推測でokにしないでください。

uncertainにしてください。


【8】

数量計は特に厳密に判定してください。

数量欄の数値だけを読みます。

金額や単価を
数量として使ってはいけません。

数量を実際に足して、
数量計と比較してください。


【9】

observed_valueには、
判定に必要な内容だけを短く書いてください。

個人情報を必要以上に
全文転記しないでください。


【10】

reasonは日本語で簡潔に書いてください。


【11】

アップロードされた各ページについて、
そのページ用に定義されたチェック項目を
すべて1回ずつ返してください。

項目を勝手に省略しないでください。
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

        response_format=make_schema(active_pages)
    )


    raw = response.choices[0].message.content

    result = json.loads(raw)

    return result, previews, active_pages


# =========================================================
# AIが項目を混ぜても画面には出さない安全処理
# =========================================================

def normalize_result(result, active_pages):

    returned_pages = {}

    for page in result.get("pages", []):

        page_name = page.get("page_name")

        if page_name in active_pages:
            returned_pages[page_name] = page


    normalized_pages = []


    for page_name in active_pages:

        expected_items = {
            name: description
            for name, description in CHECK_ITEMS[page_name]
        }


        if page_name not in returned_pages:

            normalized_pages.append(
                {
                    "page_name": page_name,
                    "document_type_status": "uncertain",
                    "document_type_reason":
                        "AIからこのページの判定結果が返されませんでした。",
                    "document_quality": "poor",
                    "items": [
                        {
                            "name": name,
                            "status": "uncertain",
                            "observed_value": "",
                            "reason":
                                "AIからこの項目の判定結果が返されませんでした。"
                        }
                        for name in expected_items.keys()
                    ]
                }
            )

            continue


        page = returned_pages[page_name]


        returned_items = {}

        for item in page.get("items", []):

            name = item.get("name")

            # そのページに本来存在する項目だけ採用
            if name in expected_items:

                # 同じ項目が複数あっても最初だけ
                if name not in returned_items:
                    returned_items[name] = item


        clean_items = []


        # CHECK_ITEMSで定義した順番で表示
        for expected_name in expected_items.keys():

            if expected_name in returned_items:

                clean_items.append(
                    returned_items[expected_name]
                )

            else:

                clean_items.append(
                    {
                        "name": expected_name,
                        "status": "uncertain",
                        "observed_value": "",
                        "reason":
                            "AIからこの項目の判定結果が返されませんでした。"
                    }
                )


        page["items"] = clean_items

        normalized_pages.append(page)


    result["pages"] = normalized_pages

    return result


# =========================================================
# 結果表示
# =========================================================

def display_page_result(page, preview):

    page_name = page["page_name"]

    display_name = DOCUMENT_INFO[page_name]["display_name"]

    st.subheader(display_name)


    if preview is not None:

        st.image(
            preview,
            use_container_width=True
        )


    # -----------------------------------------------------
    # 書類種類
    # -----------------------------------------------------

    doc_status = page["document_type_status"]


    if doc_status == "match":

        st.success(
            "✅ 書類の種類：正しい書類と判定"
        )

    elif doc_status == "wrong_document":

        st.error(
            "❌ アップロードした書類が違う可能性があります。"
        )

        st.write(
            page["document_type_reason"]
        )

    else:

        st.warning(
            "⚠️ 書類の種類を確実に判定できませんでした。"
        )

        st.write(
            page["document_type_reason"]
        )


    # -----------------------------------------------------
    # 画像品質
    # -----------------------------------------------------

    quality_labels = {

        "good":
        "✅ 画像品質：良好",

        "usable":
        "🟡 画像品質：判定可能",

        "poor":
        "🔴 画像品質：不十分"
    }


    st.caption(
        quality_labels.get(
            page["document_quality"],
            ""
        )
    )


    missing = 0
    warning = 0
    uncertain = 0


    for item in page["items"]:

        status = item["status"]


        if status == "ok":

            icon = "✅"
            label = "問題なし"


        elif status == "missing":

            icon = "❌"
            label = "記入漏れ"

            missing += 1


        elif status == "warning":

            icon = "⚠️"
            label = "要注意"

            warning += 1


        elif status == "not_applicable":

            icon = "➖"
            label = "対象外"


        else:

            icon = "🔍"
            label = "要確認"

            uncertain += 1


        with st.container(border=True):

            st.markdown(
                f"### {icon} {item['name']}：{label}"
            )


            if item["observed_value"]:

                st.write(
                    f"読み取った内容：**{item['observed_value']}**"
                )


            st.caption(
                item["reason"]
            )


    return missing, warning, uncertain


# =========================================================
# アップロード画面
# =========================================================

st.divider()

st.markdown(
    "## 📷 契約書の写真を選択"
)

st.write(
    "それぞれ対応する書類を選択してください。"
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
# AIチェック
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


            with st.spinner(
                "AIが契約書を確認しています…"
            ):

                result, previews, active_pages = check_with_ai(
                    files
                )


                # ページ混在を防ぐ安全処理
                result = normalize_result(
                    result,
                    active_pages
                )


            total_missing = 0
            total_warning = 0
            total_uncertain = 0


            for page in result["pages"]:

                page_name = page["page_name"]

                preview = previews.get(
                    page_name
                )


                m, w, u = display_page_result(
                    page,
                    preview
                )


                total_missing += m
                total_warning += w
                total_uncertain += u


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

                if total_missing > 0:

                    st.error(
                        f"❌ 記入漏れの可能性："
                        f"{total_missing}件"
                    )


                if total_warning > 0:

                    st.warning(
                        f"⚠️ 要注意項目："
                        f"{total_warning}件"
                    )


                if total_uncertain > 0:

                    st.warning(
                        f"🔍 AIでは判定できない項目："
                        f"{total_uncertain}件"
                    )


                st.info(
                    "上記項目を人の目でも確認してください。"
                )


        except Exception as e:

            st.error(
                "AI判定中にエラーが発生しました。"
            )

            st.code(
                str(e)
            )
