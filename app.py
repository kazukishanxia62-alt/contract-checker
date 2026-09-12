
import streamlit as st
from PIL import Image, ImageOps
from io import BytesIO
import base64
import json
from openai import OpenAI

st.set_page_config(page_title="契約書AIチェック", page_icon="✅", layout="centered")
st.title("契約書 AI記入漏れチェック")
st.caption("写真をAIが直接見て、指定項目の記入有無を確認します。")

st.warning(
    "これは提出前の補助チェック用です。最終確認は人が行ってください。"
    "実際の顧客契約書を扱う前に、会社の情報セキュリティ・個人情報取扱ルールを確認してください。"
)

# Streamlit Secrets からAPIキーを読む
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    st.error("OPENAI_API_KEY が設定されていません。StreamlitのSecretsにAPIキーを登録してください。")
    st.stop()

MODEL = "gpt-5.4-mini"

CHECK_ITEMS = {
    "1枚目": [
        ("役務提供期間", "『役務提供期間』または同等の期間記入欄に、日付・期間が手書き等で記入されているか"),
        ("受領サイン", "受領サイン・受領確認サイン欄に署名または記名があるか。黒ペンでもよい"),
        ("数量計", "数量の合計・数量計の欄に数値が記入されているか"),
    ],
    "2枚目": [
        ("提供期間等", "『提供期間等』『提供期間』等の欄に期間・日付が記入されているか"),
        ("特定商取引法42条欄", "特定商取引法42条に関する指定欄に必要な記入があるか"),
        ("フリガナ", "契約者等のフリガナ欄にフリガナが記入されているか"),
        ("ヶ月", "支払回数・契約期間等の『ヶ月』に対応する数値欄が記入されているか"),
    ],
}

def image_to_data_url(uploaded):
    img = Image.open(uploaded)
    img = ImageOps.exif_transpose(img).convert("RGB")

    # API送信量を抑えつつ文字を読めるサイズを確保
    max_side = 2200
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}", img

def make_schema(item_names):
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_check",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "document_quality": {
                        "type": "string",
                        "enum": ["good", "usable", "poor"]
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "enum": item_names},
                                "status": {
                                    "type": "string",
                                    "enum": ["filled", "missing", "uncertain"]
                                },
                                "observed_value": {"type": "string"},
                                "reason": {"type": "string"}
                            },
                            "required": ["name", "status", "observed_value", "reason"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["document_quality", "items"],
                "additionalProperties": False
            }
        }
    }

def check_with_ai(uploaded, page_name):
    data_url, preview = image_to_data_url(uploaded)
    items = CHECK_ITEMS[page_name]

    checklist_text = "\n".join(
        [f"- {name}: {desc}" for name, desc in items]
    )

    prompt = f"""
あなたは日本語の契約書画像の「記入漏れチェック」を行う検査担当です。
この画像について、下記の項目だけを確認してください。

{checklist_text}

重要ルール:
1. 印刷済みの文字があるだけでは「記入あり」にしないでください。
2. 手書き、押印、署名、入力済み数値など、実際に欄が埋められているかを見てください。
3. 項目名の位置が多少ずれていても、書類全体から意味的に該当欄を探してください。
4. 読み取れない、欄を特定できない、写真が不鮮明な場合は missing ではなく uncertain にしてください。
5. observed_value には読めた内容を短く記載してください。読めない場合は空文字にしてください。
6. reason は日本語で簡潔に書いてください。
7. 指定項目以外については判定しないでください。
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        response_format=make_schema([x[0] for x in items]),
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)
    return result, preview

def display_result(page_name, result, preview):
    st.subheader(page_name)
    st.image(preview, use_container_width=True)

    quality_labels = {
        "good": "✅ 画像品質：良好",
        "usable": "🟡 画像品質：判定可能",
        "poor": "🔴 画像品質：不十分",
    }
    st.caption(quality_labels.get(result["document_quality"], ""))

    missing = 0
    uncertain = 0

    for item in result["items"]:
        if item["status"] == "filled":
            icon = "✅"
            label = "記入あり"
        elif item["status"] == "missing":
            icon = "❌"
            label = "未記入"
            missing += 1
        else:
            icon = "⚠️"
            label = "要確認"
            uncertain += 1

        with st.container(border=True):
            st.markdown(f"### {icon} {item['name']}：{label}")
            if item["observed_value"]:
                st.write(f"読み取った内容：**{item['observed_value']}**")
            st.caption(item["reason"])

    return missing, uncertain

st.markdown("### 写真を選択")
col1, col2 = st.columns(2)

with col1:
    file1 = st.file_uploader(
        "1枚目",
        type=["jpg", "jpeg", "png"],
        key="page1"
    )
with col2:
    file2 = st.file_uploader(
        "2枚目",
        type=["jpg", "jpeg", "png"],
        key="page2"
    )

st.info(
    "ポイント：契約書の四隅が入るように撮影してください。"
    "多少の傾きや背景はそのままで構いません。"
)

if st.button("🤖 AIでチェックする", type="primary", use_container_width=True):
    if not file1 and not file2:
        st.error("写真を1枚以上選んでください。")
    else:
        total_missing = 0
        total_uncertain = 0

        try:
            if file1:
                with st.spinner("1枚目をAIが確認しています…"):
                    result1, preview1 = check_with_ai(file1, "1枚目")
                m, u = display_result("1枚目", result1, preview1)
                total_missing += m
                total_uncertain += u

            if file2:
                with st.spinner("2枚目をAIが確認しています…"):
                    result2, preview2 = check_with_ai(file2, "2枚目")
                m, u = display_result("2枚目", result2, preview2)
                total_missing += m
                total_uncertain += u

            st.divider()

            if total_missing == 0 and total_uncertain == 0:
                st.success("指定項目はすべて記入ありと判定されました。")
            elif total_missing > 0:
                st.error(
                    f"未記入の可能性がある項目が {total_missing} 件あります。"
                    f" 要確認は {total_uncertain} 件です。"
                )
            else:
                st.warning(
                    f"未記入判定はありませんが、要確認が {total_uncertain} 件あります。"
                )

        except Exception as e:
            st.error("AI判定中にエラーが発生しました。")
            st.code(str(e))
