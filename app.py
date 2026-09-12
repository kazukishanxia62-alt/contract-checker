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
# チェック項目
# =========================================================

CHECK_ITEMS = {

    # -----------------------------------------------------
    # 1枚目
    # クレジット申込書
    # -----------------------------------------------------

    "1枚目": [

        (
            "お申込年月日",
            """
            書類上部の「お申込年月日」の年・月・日が
            必要な箇所まで記入されているか確認する。
            """
        ),

        (
            "申込者フリガナ",
            """
            お名前欄の上にある申込者本人のフリガナ欄を確認する。
            他の場所にあるフリガナを代用しない。
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
            申込者本人の生年月日の年・月・日が
            記入されているか確認する。
            """
        ),

        (
            "住所",
            """
            「ご住所」欄を確認する。

            都道府県名まで記入されていること。

            さらに、印刷されている
            「都・道・府・県」のいずれか適切なものに
            ○が付いていること。

            例：
            大阪＋府に○ → OK
            京都＋府に○ → OK
            兵庫＋県に○ → OK
            東京＋都に○ → OK
            北海道＋道に○ → OK

            大阪と書いてあるが○なし → missing
            大阪なのに県に○ → warning

            市区町村以下の住所も、
            明らかに途中で終わっていないか確認する。
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
            勤務先の電話番号欄に番号が記入されているか確認する。
            """
        ),

        (
            "雇用形態",
            """
            雇用形態の選択肢のいずれかに
            ○などの選択がされているか確認する。
            """
        ),

        (
            "派遣先・出向先",
            """
            雇用形態を確認する。

            「派遣社員」に○が付いている場合のみ、
            「派遣先・出向先の会社名」が必須。

            派遣社員なのに会社名が空欄 → missing

            派遣社員ではない場合は、
            派遣先・出向先欄が空欄でも問題ないため
            not_applicable とする。
            """
        ),

        (
            "世帯主の確認",
            """
            「世帯主の確認」欄について、
            申込者本人かその他か、
            必要な選択・記入がされているか確認する。

            ただし、
            「世帯主の確認」の右側にある「連絡先」欄は
            空欄でも問題ない。

            この連絡先が空欄であることを理由に
            missing にしてはいけない。
            """
        ),

        (
            "世帯状況",
            """
            縦書きで「世帯状況」と書かれた欄について、
            必要な世帯主情報が記入されているか確認する。
            """
        ),

        (
            "世帯主クレジット月額",
            """
            「世帯状況」欄にある
            「世帯主のクレジットの月あたりのお支払額」
            を読み取る。

            金額が100,000円以下 → ok

            100,000円を超えている → warning

            warningの場合は、
            observed_value に読み取った金額を記載し、
            reason に
            「10万円を超えているため要注意」
            と記載する。

            金額欄自体が本来記入対象なのに空欄なら
            missing。
            """
        ),

        (
            "関係者情報",
            """
            縦書きで「関係者情報」と書かれた欄を確認する。

            申込者が夫の場合 → 妻の情報を書く。
            申込者が妻の場合 → 夫の情報を書く。

            配偶者がいることが書類から確認できるのに、
            対応する夫または妻の情報が空欄なら missing。

            配偶者がいないなど、
            明らかに対象外の場合は not_applicable。

            他の人物の情報を間違って使用しない。
            """
        ),

        (
            "役務提供期間",
            """
            クレジット申込内容付近にある
            「役務提供期間」
            「役務提供期間（権利の移転時期）」
            などの指定欄を確認する。

            その欄に必要な期間・年月等が
            記入されているか確認する。

            別の年月日を誤って拾わない。
            """
        ),

        (
            "特定商取引法42条受領年月日",
            """
            右上付近にある
            「特定商取引法第42条第2項、
            又は第3項書面の受領年月日」
            の欄だけを確認する。

            年・月・日がすべて記入されていれば ok。

            一部でも欠けていれば missing。

            他の年月日を代用してはいけない。
            """
        ),

        (
            "受領サイン",
            """
            受領サイン・受領確認欄に
            手書きの署名または記名があるか確認する。

            黒色のペンでも問題ない。

            印刷済みの文字だけでは
            記入ありにしない。
            """
        ),

        (
            "数量計",
            """
            商品・役務欄の「数量」を確認する。

            必ず以下の手順で判定する。

            1. 商品表の数量欄に手書きされている数量を
               すべて読み取る。

            2. 読み取った数量をすべて足し算する。

            3. 「数量計」欄に記入された数字を読む。

            4. 計算結果と数量計欄が一致しているか比較する。

            例：
            数量 3 と 3
            → 3 + 3 = 6
            → 数量計6なら ok

            金額・単価・小計・税込金額・頭金・
            支払額・商品価格などを
            数量として絶対に使用しない。

            一致 → ok

            数量計が空欄 → missing

            数量計はあるが計算と不一致 → warning

            observed_valueには可能なら
            「3 + 3 = 6 / 数量計 6」
            のように記載する。
            """
        ),

        (
            "支払ヶ月",
            """
            指定されている「ヶ月」欄だけを確認する。

            その欄に月数が記入されているか確認する。

            書類内の別の数字・日付・支払回数を
            勝手に代用しない。
            """
        ),

        (
            "銀行口座",
            """
            書類最下部の銀行口座欄を確認する。

            左側：
            「ゆうちょ銀行」

            右側：
            「ゆうちょ銀行以外の銀行」

            このどちらか一方に、
            必要な口座情報が記入されていればOK。

            ゆうちょ記入あり・他行空欄 → ok

            ゆうちょ空欄・他行記入あり → ok

            両方空欄 → missing

            両方を書く必要はない。
            """
        ),

        (
            "口座名義人フリガナ",
            """
            書類最下部付近の
            「口座名義人」の「フリガナ」欄を確認する。

            選択・記入された銀行口座に対応する
            口座名義人フリガナが記入されていること。

            他のフリガナ欄を代用してはいけない。
            """
        ),

    ],


    # -----------------------------------------------------
    # 2枚目
    # 役務申込書・指導内容
    # -----------------------------------------------------

    "2枚目": [

        (
            "保護者氏名フリガナ",
            """
            「保護者氏名」に対応する
            フリガナ欄を確認する。

            他の人物のフリガナ欄ではなく、
            保護者氏名に対応するフリガナだけを判定する。
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
            「ご住所・連絡先」の住所欄を確認する。

            都道府県名まで記入されていること。

            さらに、
            印刷されている
            「都・道・府・県」
            のいずれか正しいものに○が付いていること。

            住所と○が一致している必要がある。

            例：
            大阪＋府 → OK
            京都＋府 → OK
            兵庫＋県 → OK
            東京＋都 → OK
            北海道＋道 → OK

            都道府県名だけあって○なし → missing

            ○はあるが住所がない → missing

            大阪なのに県に○など → warning
            """
        ),

        (
            "指導対象A",
            """
            右上にある指導対象A・B・Cのうち、
            Aを確認する。

            指導対象Aの「有」に
            ○が付いていること。

            有に○ → ok

            ○なし → missing

            判別不能 → uncertain
            """
        ),

        (
            "コース名",
            """
            左下付近の「コース名」の
            右側の記入欄を確認する。

            この欄には原則として
            「週1 90分」
            のようなコース内容が記入される。

            この指定欄が空欄なら missing。

            他の場所にある
            「90分」「週1」等の記載を
            代用してはいけない。
            """
        ),

        (
            "初回指導日",
            """
            「指導料・交通費について」の中にある
            「初回指導日」欄を確認する。

            必要な年・月・日等が
            記入されているか確認する。

            他の日付を代用しない。
            """
        ),

        (
            "役務提供期間A",
            """
            左下付近の
            「役務提供期間」欄を確認する。

            Aの行だけが判定対象。

            Aの必要箇所が
            記入されていれば ok。

            Bの行は空欄でも問題ない。

            Bが空欄であることを理由に
            missing にしてはいけない。
            """
        ),

        (
            "その他必須記入欄",
            """
            このページについて、
            印刷上明らかに記入必須と分かる欄、
            「※」等で必須と示されている欄のうち、
            上記チェック項目に含まれていない
            重大な記入漏れがないか確認する。

            条件付き・任意・明らかに対象外の欄は
            無理に未記入扱いしない。

            条件が分からない場合は
            missingではなく uncertain とする。
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

    # 小さい文字を読み取れるように解像度をある程度維持
    max_side = 2600

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

def make_schema():

    all_names = []

    for page_items in CHECK_ITEMS.values():

        for name, _ in page_items:

            if name not in all_names:
                all_names.append(name)

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
                                    "enum": [
                                        "1枚目",
                                        "2枚目"
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
                                                "enum": all_names
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

    content = []

    page_prompts = []

    previews = {}

    for page_name, uploaded in files.items():

        if uploaded is None:
            continue

        data_url, preview = image_to_data_url(uploaded)

        previews[page_name] = preview

        checklist_text = "\n".join(
            [
                f"■ {name}\n{desc}"
                for name, desc in CHECK_ITEMS[page_name]
            ]
        )

        page_prompts.append(
            f"""
====================
{page_name}
====================

{checklist_text}
"""
        )

        content.append(
            {
                "type": "text",
                "text": f"次の画像は【{page_name}】です。"
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

    full_checklist = "\n".join(page_prompts)

    prompt = f"""
あなたは日本語契約書の提出前チェック担当です。

送られている契約書画像について、
指定されたチェックルールを厳密に確認してください。

{full_checklist}


【最重要ルール】

1.
印刷されている文字だけでは
「記入済み」と判定しないでください。

手書き、○、署名、押印、入力された数字など、
実際の記入内容を確認してください。


2.
各チェック項目は
指定された欄・指定された位置だけを見てください。

書類内の別の場所に
似た数字、名前、カタカナ、年月日があっても
代用してはいけません。


3.
条件付き項目については
必ず条件を確認してください。

対象外の場合は
not_applicable
としてください。


4.
記入はあるが、
内容が条件に違反している場合や、
金額・数量などが不一致の場合は

warning

にしてください。


5.
本来必要な記入そのものがない場合は

missing

にしてください。


6.
写真がぼやけている、
文字が重なっている、
欄を確実に特定できないなど、
判断に自信がない場合は

uncertain

にしてください。

推測でOKにしないでください。


7.
問題がない場合は

ok

としてください。


8.
数量計では、
数量欄の数字だけを使用してください。

金額、
税込金額、
単価、
小計、
頭金、
支払額、
商品価格などを
数量として絶対に使用しないでください。


9.
数字の計算が必要な場合は、
読み取った数字を実際に計算してください。


10.
observed_valueには、
実際に読み取った内容を短く記載してください。

個人情報については
必要以上に全文を書き写さないでください。


11.
reasonは日本語で、
判定理由を簡潔に記載してください。


12.
各ページについて、
指定されたチェック項目を
すべて1回ずつ返してください。

項目を勝手に省略しないでください。


13.
書類の種類・レイアウトが想定と違う場合は、
無理に判定せず uncertain としてください。
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

        response_format=make_schema()
    )

    raw = response.choices[0].message.content

    result = json.loads(raw)

    return result, previews


# =========================================================
# 結果表示
# =========================================================

def display_page_result(page, preview):

    page_name = page["page_name"]

    if page_name == "1枚目":
        display_name = "1枚目：クレジット申込書"
    else:
        display_name = "2枚目：役務申込書・指導内容"

    st.subheader(display_name)

    if preview is not None:

        st.image(
            preview,
            use_container_width=True
        )

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

    return (
        missing,
        warning,
        uncertain
    )


# =========================================================
# 写真アップロード
# =========================================================

st.divider()

st.markdown("## 📷 契約書の写真を選択")

st.write(
    "下の説明を確認して、"
    "それぞれ対応する契約書の写真を選んでください。"
)


# ---------------------------------------------------------
# 1枚目
# ---------------------------------------------------------

st.markdown("### ① クレジット申込書")

st.info(
    "「クレジットお申込の内容」が上部にあり、"
    "お申込者情報・世帯状況・関係者情報・"
    "商品/数量/金額・銀行口座などが載っている書類です。"
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


# ---------------------------------------------------------
# 2枚目
# ---------------------------------------------------------

st.markdown("### ② 役務申込書・指導内容")

st.info(
    "保護者氏名・指導対象A/B/C・コース名・"
    "初回指導日・役務提供期間などが載っている書類です。"
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
    "📌 契約書全体が写るように、"
    "できるだけ真上から明るい場所で撮影してください。"
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

            with st.spinner(
                "AIが契約書全体を確認しています…"
            ):

                result, previews = check_with_ai(
                    files
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

            st.markdown("## 📋 チェック結果まとめ")

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
