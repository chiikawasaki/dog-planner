# 履歴を圧縮する関数
import json
from typing import Any

MAX_HISTORY = 100
KEEP_RECENT = 50

# 古い触れ合い履歴old_historyを要約する関数
def summarize_history(
    client: Any,
    previous_summary: str,
    old_history: list[dict],
) -> str:
     """これまでの要約と古い履歴を統合して、新しい要約を作る。"""

     prompt = f"""
     あなたは、仮想の犬のペットとユーザーの交流履歴を整理する役割です。

     これまでの要約と、新しく追加された履歴を統合して、今後の仮想ペットの
     反応に必要な情報をまとめてください。

     【これまでの要約】
     {previous_summary or "なし"}

     【今回要約する履歴】
     {json.dumps(old_history, ensure_ascii=False, indent=2)}

     以下を優先して残してください。
     - ユーザーとの関係性の変化
     - 交流や撫で方の傾向
     - ペットが喜んだ・落ち着いた・警戒したなどの傾向
     - 今後の反応に影響する重要な出来事

     500文字程度で要約してください。
     """

     response = client.models.generate_content(
        model = "gemini-3.1-flash-lite",
        contents = prompt,
     )

     return response.text

# 実際に圧縮する関数
# dictは辞書型のこと
def compress_history_if_needed(
    client: Any,
    interaction_summary: str,
    interaction_history: list[dict],
) -> tuple[str, list[dict], bool]:
    """履歴がMAX_HISTORYを超えたら、古い履歴を圧縮する。

    戻り値の3つ目は「圧縮を実際に行ったか」を表すbool。
    """

    # 履歴がMAX_HISTORYを超えていない場合は、そのまま返す（圧縮なし）
    if len(interaction_history) <= MAX_HISTORY:
        return interaction_summary, interaction_history, False
    # 古い履歴
    old_history = interaction_history[:-KEEP_RECENT]
    # 最近の履歴
    recent_history = interaction_history[-KEEP_RECENT:]

    new_summary = summarize_history(
        client = client,
        previous_summary = interaction_summary,
        old_history = old_history,
    )

    return new_summary, recent_history, True