        # ----------------------------------------------------
        # ★ 本人の勤務年数「年・ヶ月」専用判定
        # ----------------------------------------------------

        with st.spinner(
            "① 勤務年数の年・ヶ月を確認中..."
        ):

            applicant_work_years = safe_analysis(
                p1_bytes,

                COMMON
                + PAGE1_STRUCTURE
                + """
【今回確認するのは本人の勤務年数だけです】

書類内にある数字を探すのではありません。

必ず次の順番で対象欄を特定してください。


STEP 1

「ご契約者本人」の勤務先ブロックを
特定してください。

本人情報の下、
世帯状況の上にある勤務先ブロックです。


STEP 2

その勤務先ブロックの中にある

「勤務年数」

という印刷ラベルを
実際に発見してください。


STEP 3

「勤務年数」と同じ行、
または勤務年数ラベルに直接対応する
記入欄だけを確認してください。


STEP 4

その指定欄には

［手書き数字］年［手書き数字］ヶ月

という構造があります。

印刷された「年」と「ヶ月」を
アンカーとして使ってください。


━━━━━━━━━━━━━━━━━━

【非常に重要】

勤務年数欄の外にある数字は
絶対に読み取ってはいけません。

特に、

19
20
2026

などの数字が
別の日付・生年月日・年収・電話番号等に
存在していても無視してください。

━━━━━━━━━━━━━━━━━━


【年の判定】

印刷された「年」の
すぐ左側の記入スペースだけを見ます。

そこに手書き数字があれば

year_has_entry=true

として、
その数字だけをyear_valueに入れます。


【ヶ月の判定】

印刷された「ヶ月」の
すぐ左側の記入スペースだけを見ます。

そこに手書き数字があれば

months_has_entry=true

として、
その数字だけをmonths_valueに入れます。


【0について】

0年
0ヶ月

と実際に「0」が書かれている場合は
記入ありです。


【空欄】

印刷された

年
ヶ月

だけがあり、
その直前に手書き数字がなければ
未記入です。


━━━━━━━━━━━━━━━━━━

【重要：欄を間違えない】

次の数字は絶対に使用禁止です。

・生年月日
・契約年月日
・受領年月日
・年収
・税込年収
・給料日
・郵便番号
・電話番号
・会社所在地
・世帯主情報
・関係者情報
・関係者の勤務年数

━━━━━━━━━━━━━━━━━━


【整合性確認】

year_valueまたはmonths_valueを返す前に、

「この数字は本当に
本人勤務先ブロックの
勤務年数欄の中に書かれているか？」

をもう一度確認してください。

答えが明確にYESでない場合、
その数字を返してはいけません。


勤務年数欄自体を
確実に特定できない場合：

field_located=false
uncertain=true


勤務年数欄は特定できるが
数字がぼやけている場合：

field_located=true
uncertain=true


数字が明確な場合だけ
year_value / months_value
を返してください。


【例】

指定欄が

3年8ヶ月

なら

field_located=true
year_has_entry=true
year_value=3
months_has_entry=true
months_value=8
uncertain=false


指定欄が

3年0ヶ月

なら

field_located=true
year_has_entry=true
year_value=3
months_has_entry=true
months_value=0
uncertain=false


指定欄が

3年　ヶ月

なら

field_located=true
year_has_entry=true
year_value=3
months_has_entry=false
months_value=null
uncertain=false


指定欄が

年8ヶ月

なら

field_located=true
year_has_entry=false
year_value=null
months_has_entry=true
months_value=8
uncertain=false
""",
                WorkYearsCheck
            )


        if applicant_work_years:

            show_work_years(
                "勤務年数",
                applicant_work_years
            )
