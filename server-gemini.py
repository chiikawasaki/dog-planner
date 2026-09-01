from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types
from uuid import UUID
import os
import json
from dotenv import load_dotenv
from supabase import Client, create_client
from datetime import datetime, timezone
from history import compress_history_if_needed
import time

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise RuntimeError(
        "SUPABASE_URLまたはSUPABASE_KEYが設定されていません"
    )

supabase: Client = create_client(
    supabase_url,
    supabase_key,
)

app = FastAPI()

# =============================================================================
# Configuration
# =============================================================================

# APIキーは環境変数から取得
# (PowerShellなら $env:GEMINI_API_KEY="...", Macなら export GEMINI_API_KEY="...")
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not gemini_api_key:
    raise RuntimeError("GEMINI_API_KEYが設定されていません")

client = genai.Client(api_key=gemini_api_key)

# 使用するモデル
MODEL_NAME = "gemini-3.1-flash-lite"

# =============================================================================
# 1. Pet Plan API (自律行動用)
# =============================================================================

class PetState(BaseModel):
    hunger: float
    energy: float
    last_action: str
    current_action: str
    front_obstacle_dist: float | None = None
    left_obstacle_dist: float | None = None
    right_obstacle_dist: float | None = None
    front_blocked: bool | None = None

# Geminiからのレスポンス定義 (Plan)
PlanResponseSchema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "plan_id": types.Schema(type=types.Type.STRING),
        "expires_in_sec": types.Schema(type=types.Type.NUMBER),
        "weights": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "behavior": types.Schema(type=types.Type.STRING),
                    "bias": types.Schema(type=types.Type.NUMBER),
                },
                required=["behavior","bias"],
            ),
        ),
        "sequence": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "behavior": types.Schema(type=types.Type.STRING),
                    "min_sec": types.Schema(type=types.Type.NUMBER),
                    "max_sec": types.Schema(type=types.Type.NUMBER),
                    "until":   types.Schema(type=types.Type.STRING),
                    "speed":   types.Schema(type=types.Type.NUMBER),
                },
                required=["behavior","min_sec","max_sec"],
            ),
        ),
        "notes": types.Schema(type=types.Type.STRING),
        "look_yaw_deg": types.Schema(type=types.Type.NUMBER),
    },
    required=["plan_id","expires_in_sec","weights","sequence","notes"],
)

PLAN_SYSTEM_PROMPT = """You are a planner for an AR pet dog living in a 3D mixed-reality room.

Behaviors allowed:
Breathe, Walk1, Walk2, Run, SitRoutine, AngryRoutine.

Your goal:
Choose the next natural sequence of actions and optionally a look direction,
based on the dog's internal state and nearby obstacles.

The dog state fields are:
- hunger: 0.0 = full, 1.0 = very hungry (IGNORE THIS FIELD, eating is disabled here)
- energy: 0.0 = exhausted, 1.0 = full of energy
- front_obstacle_dist: distance (m) to obstacle (-1 if none)
- front_blocked: true if obstacle is < 0.4m

RULES:
1. STRICTLY FORBIDDEN: Do NOT suggest "Eat", "EatRoutine", or any feeding behavior in this plan.
2. If front_blocked is true, avoid "Run" or forward movement. Suggest turning (look_yaw_deg) or SitRoutine.
3. If energy is low (<0.3), prefer SitRoutine or Breathe.
4. If energy is high and space is clear, prefer Walk or Run.
5. You MAY set "look_yaw_deg" (float): positive=right, negative=left (e.g., 90, -45).

Output MUST match the responseSchema exactly.
"""

@app.post("/pet/plan")
def plan(state: PetState):
    prompt = f"Current state: {state.model_dump_json()}"

    # Gemini API 呼び出し
    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[PLAN_SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlanResponseSchema,
        ),
    )

    # JSONパース
    try:
        # SDKがパース済みの場合
        if hasattr(resp, "parsed") and resp.parsed:
            data = dict(resp.parsed)
        else:
            data = json.loads(resp.text)
    except Exception as e:
        print("JSON Parse Error (Plan):", e)
        return {"plan_id": "error", "weights": [], "sequence": [], "notes": "Parse Error"}

    # 安全策: Eatが含まれていたら削除する
    if "sequence" in data and isinstance(data["sequence"], list):
        safe_seq = []
        for step in data["sequence"]:
            b_name = step.get("behavior", "")
            if "eat" in b_name.lower():
                continue
            safe_seq.append(step)
        data["sequence"] = safe_seq

    print(f"[Plan] Energy={state.energy:.2f}, Action={data.get('sequence')}")
    return data


# =============================================================================
# 2. Pet Train API (おすわり訓練用)
# =============================================================================

class TrainRequest(BaseModel):
    current_proficiency: float
    practice_count: int
    energy: float
    is_success: bool

# Geminiからのレスポンス定義 (Train)
# ★ new_energy を追加済み
TrainResponseSchema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "new_proficiency": types.Schema(type=types.Type.NUMBER),
        "proficiency_gain": types.Schema(type=types.Type.NUMBER),
        "new_energy": types.Schema(type=types.Type.NUMBER, description="Updated energy level (0.0-1.0) after training"),
        "reaction": types.Schema(type=types.Type.STRING),
        "comment": types.Schema(type=types.Type.STRING),
    },
    required=["new_proficiency", "proficiency_gain", "new_energy", "reaction", "comment"],
)

TRAIN_SYSTEM_PROMPT = """You are the brain of a virtual dog.
The user is teaching you the "Sit" command.
Your task is to calculate the new proficiency level AND the new energy level (fatigue).

Rules for Proficiency:
1. Range is 0.0 to 1.0.
2. If is_success=True: Increase proficiency.
   - High Energy (>0.6): Learn faster (larger gain).
   - Low Energy (<0.3): Learn slower (smaller gain).
   - High Proficiency (>0.8): Harder to master (diminishing returns).
3. If is_success=False: Zero or small negative gain (frustration).

Rules for Energy (Fatigue):
1. Training consumes energy. You MUST decrease the energy value.
2. Typical cost is 0.05 to 0.15 per session depending on how hard the dog tried.
3. If the dog was already tired, it might lose more energy or refuse to work.
4. Output must be between 0.0 and 1.0.

Output the result in JSON.
"""

@app.post("/pet/train")
def train_dog(req: TrainRequest):

    print("\n" + "="*30)
    print("📢 [Train] Request Payload Received:")
    print(req.model_dump_json(indent=2))
    print("="*30 + "\n")
    
    prompt = f"""
    Training Session 'Sit':
    - Did user gesture correctly?: {req.is_success}
    - Current Proficiency: {req.current_proficiency}
    - Practice Count in this session: {req.practice_count}
    - Current Energy: {req.energy}
    """

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[TRAIN_SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TrainResponseSchema,
        ),
    )

    try:
        if hasattr(resp, "parsed") and resp.parsed:
            data = dict(resp.parsed)
        else:
            data = json.loads(resp.text)
    except Exception as e:
        print("JSON Parse Error (Train):", e)
        # エラー時のフォールバック値 (とりあえずエネルギーを少し減らす)
        safe_energy = max(0.0, req.energy - 0.05)
        return {
            "new_proficiency": req.current_proficiency,
            "proficiency_gain": 0,
            "new_energy": safe_energy,
            "reaction": "None",
            "comment": "Error"
        }

    print(f"[Train] Success={req.is_success} | Gain={data.get('proficiency_gain')} | Energy {req.energy:.2f} -> {data.get('new_energy'):.2f}")
    return data

# =============================================================================
# 3. Pet production API (おすわり本番用)
# =============================================================================
class ProductionRequest(BaseModel):
    # 現在の経験値
    current_proficiency: float
    # 連続でやった回数
    consecutive_practices: int
    energy: float

# Geminiからのレスポンス定義 (Production)
ProductionResponseSchema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "reaction": types.Schema(type=types.Type.STRING),
        "new_proficiency": types.Schema(type=types.Type.NUMBER),
        "proficiency_gain": types.Schema(type=types.Type.NUMBER),
        "new_energy": types.Schema(type=types.Type.NUMBER, description="Updated energy level (0.0-1.0) after training"),
        "comment": types.Schema(type=types.Type.STRING),
    },
    required=["reaction", "new_proficiency", "proficiency_gain", "new_energy", "comment"],
)

PRODUCTION_SYSTEM_PROMPT = """
You are the conscious mind of a virtual dog.
The user is giving you the command "Sit".
**Do NOT calculate probabilities. Simulate a biological decision process.**

### THE INTERNAL CONFLICT
You must balance three competing internal forces to decide your action:

1.  **Muscle Memory (Proficiency 0.0-1.0):**
    * This is your *potential* to succeed.
    * **Low (0.0-0.3):** Your body doesn't know how to move. Even if you try hard, you will likely fail.
    * **Mid (0.3-0.7):** You are unstable. Sometimes you get it, sometimes you wobble.
    * **High (0.8-1.0):** You are a master. You almost never fail *unless* your body refuses (Energy/Boredom).

2.  **Physical Drive (Energy 0.0-1.0):**
    * This is your *fuel* to execute the command.
    * **High:** You are sharp and focused. It helps you utilize your Muscle Memory fully.
    * **Low:** You are sluggish. Even if you are a master (High Proficiency), you might just flop down because moving is hard.

3.  **Mental Patience (Consecutive Practices):**
    * This is your *willingness* to obey.
    * If this is high, you are bored. You might ignore the command simply because it's annoying, regardless of your skill or energy.

### DECISION GUIDELINES (Interpret the Vibe)
Look at the combination of the three forces and decide the outcome naturally.

* **The "Eager but Clumsy" Vibe:**
    * (High Energy + Low Proficiency)
    * You try your best because you have energy, but your body fails. -> Result: **"fail"** (Energetic failure).

* **The "Lazy Master" Vibe:**
    * (Low Energy + High Proficiency)
    * You know exactly how to sit, but you are too tired to do it properly. -> Result: **"tired"** (or sloppy **"fail"**).

* **The "Fed Up" Vibe:**
    * (High Consecutive Practices)
    * You are just done with this. -> Result: **"tired"** (Refusal).

* **The "Perfect Execution" Vibe:**
    * (High Proficiency + Good Energy + Low Boredom)
    * Everything aligns. -> Result: **"sit"**.

### OUTPUT INSTRUCTIONS
Based on the narrative you simulated, output the JSON.
- `reaction`: "sit", "fail", or "tired".
- `new_proficiency`: Increase significantly only on "sit".
- `new_energy`: Decrease based on how much effort you used.
- `comment`: A short, biological thought in Japanese (e.g., "Huh?", "Too tired...", "Nailed it!").
"""

@app.post("/pet/production")
def production_dog(req: ProductionRequest):

    print("\n" + "="*30)
    print("📢 [Production] Request Payload Received:")
    print(req.model_dump_json(indent=2))
    print("="*30 + "\n")
    
    prompt = f"""
    ### Current Moment
    The owner just gave the "Sit" command.
    
    **Context:**
    - My Current Skill: {req.current_proficiency} (0.0-1.0)
    - My Current Energy: {req.energy} (0.0-1.0)
    - Repetition: This is practice #{req.consecutive_practices} in a row.

    **Action:**
    React based on your instincts and current stats. Output the JSON.
    """

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[PRODUCTION_SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ProductionResponseSchema,
            temperature=0.5,
        ),
    )

    try:
        if hasattr(resp, "parsed") and resp.parsed:
            data = dict(resp.parsed)
        else:
            data = json.loads(resp.text)
    except Exception as e:
        print("JSON Parse Error (Train):", e)
        # エラー時のフォールバック値 (とりあえずエネルギーを少し減らす)
        safe_energy = max(0.0, req.energy - 0.05)
        return {
            "reaction": "fail",
            "new_proficiency": req.current_proficiency,
            "proficiency_gain": 0,
            "new_energy": safe_energy,
            "comment": "Error"
        }
    print(f"")
    print(f"[production] proficiency={data.get('new_proficiency')} | Energy {req.energy:.2f} -> {data.get('new_energy'):.2f}| reaction={data.get('reaction')}")
    return data
# 起動コマンドメモ
# uvicorn server-gemini:app --reload --host 0.0.0.0 --port 8000

# =============================================================================
# 4. Pet petting API (撫でた後用)
# =============================================================================
class PettingRequest(BaseModel):
    # ペットID
    pet_id:UUID
    # 撫でた秒数
    petting_duration:float

# Geminiからのレスポンス定義 (petting)
PettingResponseSchema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "intimacy": types.Schema(type=types.Type.NUMBER),
        "energy": types.Schema(type=types.Type.NUMBER),
        "comment": types.Schema(type=types.Type.STRING),
    },
    required=["intimacy", "energy", "comment"],
)

PETTING_SYSTEM_PROMPT = """
あなたは犬です。
ユーザーが撫でる動作を行ったら、親密度とエネルギーを決定する役目を持っています。
以下の入力に対して、決まった出力を行なってください。
### 入力値
- energy:犬が現在どれくらい元気かを表す値。0.0-1.0の値を取り、1.0に近いほど元気。
- intimacy:犬とユーザーの親密度を表す値。0.0-1.0の値を取り、1.0に近いほど親交が深い。
- petting_duration: ユーザーが犬を撫でた時間。
### 出力ルール
出力はJSON形式で行うこと。
- `intimacy`: 0.0から1.0の範囲の値をとる。親密度は1.0に近いほど親交が深い。petting_durationやenergyが多いほど上昇しやすい。通常は0.01前後を目安に上昇させる。
- `energy`: 撫でた後のエネルギー値。0.0~1.0の値で返すこと。嬉しいと思った時に増える。撫でに満足した時に増える。滅多に増えない。
- `comment`: 犬の気持ちや判断の理由をここに書く。20~40文字程度で書くこと。
"""

@app.post("/pet/petting")
def petting_dog(req: PettingRequest):

    print("\n" + "="*30)
    print("📢 [Petting] Request Payload Received:")
    print(req.model_dump_json(indent=2))
    print("="*30 + "\n")
    
    # クライアントから取得したpet_idを使ってsupabaseから現在状態を取得する
    result = (
        supabase
        .table("pet_states")
        .select("id, energy, intimacy, interaction_history, interaction_summary")
        .eq("id",str(req.pet_id))
        .maybe_single()
        .execute()
    )
    
    # pet_idを持つペットがDBにいなかった場合
    if result.data is None:
        raise HTTPException(
            status_code = 404,
            detail="Pet state not found"
        )
        
    pet = result.data
    
    current_energy = pet["energy"]
    current_intimacy = pet["intimacy"]
    interaction_history = pet["interaction_history"] or []
    interaction_summary = pet["interaction_summary"] or ""
    print("Pet state loaded from Supabase:")
    print(f"energy: {current_energy}")
    print(f"intimacy: {current_intimacy}")
    print(f"history count: {len(interaction_history)}")
    
    prompt = f"""
    ### 現在
    ユーザーが犬を撫でた
    
    **Context:**
    - エネルギー: {current_energy} (0.0-1.0)
    - 今の親密度: {current_intimacy} (0.0-1.0)
    - 撫でた秒数: {req.petting_duration}
    - 直近の触れ合い履歴: {json.dumps(interaction_history, ensure_ascii=False)}
    - 過去の交流の要約: {interaction_summary or "まだ要約された過去の交流はありません"}
    **行うこと:**
    親密度とエネルギーを決定する。出力はJSON形式。
    """

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[PETTING_SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PettingResponseSchema,
            temperature=0.5,
        ),
    )

    try:
        if hasattr(resp, "parsed") and resp.parsed:
            data = dict(resp.parsed)
        else:
            data = json.loads(resp.text)
        
        new_energy = float(data["energy"])
        new_intimacy = float(data["intimacy"])
        comment = str(data["comment"])
        
    except Exception as e:
        print("JSON Parse Error (Train):", e)
        return {
            "intimacy": current_intimacy,
            "energy": current_energy,
            "comment": "Error"
        }
        
    new_history_item = {
        "type": "petting",
        "petting_duration": req.petting_duration,
        "before_energy": current_energy,
        "after_energy": new_energy,
        "before_intimacy": current_intimacy,
        "after_intimacy": new_intimacy,
        "comment": comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    updated_history = interaction_history + [new_history_item]
    # 履歴を圧縮すべきか判定->すべきだったら圧縮まで行う
    interaction_summary,interaction_history,compressed = compress_history_if_needed(
        client = client,
        interaction_summary = interaction_summary,
        interaction_history = updated_history,
    )
    
    # supabaseを更新
    try:
        update_result = (
            supabase
            .table("pet_states")
            .update({
                "energy": new_energy,
                "intimacy": new_intimacy,
                "interaction_history": interaction_history,
                "interaction_summary": interaction_summary,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id",str(req.pet_id))
            .execute()
        )
    except Exception as e:
        print("Supabase Update error:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to save updated pet state",
        )
        
    if not update_result.data:
        raise HTTPException(
            status_code=500,
            detail="Pet state was not updated",
        )
    response_data = {
        "energy": new_energy,
        "intimacy": new_intimacy,
        "comment": comment,
        "compressed": compressed,
    }
        
    print(f"")
    print(f"[petting] ={data}")
    return response_data


# =============================================================================
# 4. Pet Vibration API (撫で始め用)
# =============================================================================
# クライアントからのリクエスト
class VibrationRequest(BaseModel):
    pet_id: UUID

# Geminiからのレスポンス定義
# 振動パターンとコメントを返す
VibrationResponseSchema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "vibration_pattern":types.Schema(
            type=types.Type.STRING,
            enum=[
                "haptic_01",
                "haptic_02",
                "haptic_03",
                "haptic_04",
                "haptic_05",
                "haptic_06",
                "haptic_07",
                "haptic_08",
                "haptic_09",
                "haptic_10",
            ],
        ),
        "comment": types.Schema(type=types.Type.STRING),
    },
    required=["vibration_pattern", "comment"],
)

VIBRATION_SYSTEM_PROMPT = """
あなたは、MR環境でユーザーと生活する仮想の犬です。
ユーザーに安心感や癒しを与えることを目的としています。

ユーザーが犬を撫で始めたときに、現在のエネルギー、親密度、および過去の触れ合い履歴を考慮し、提示する触覚フィードバックを1つ選択してください。

## 入力値

* energy:
  犬の現在の元気さを表す0.0以上1.0以下の数値。
  1.0に近いほど元気で、0.0に近いほど疲れている。

* intimacy:
  犬とユーザーとの親密度を表す0.0以上1.0以下の数値。
  1.0に近いほどユーザーを信頼しており、0.0に近いほど警戒している。

* interaction_history:
  過去の触れ合い履歴を表すJSON配列。
  最近の履歴を重視し、過去の反応と極端に矛盾しないフィードバックを選択すること。
  履歴が空の場合は、energyとintimacyのみで判断すること。

## 振動パターン

以下の候補から必ず1つだけ選択してください。

* haptic_01:
  速くて強い心拍。強い緊張や警戒を表す。

* haptic_02:
  速くて弱い心拍。元気のなさや軽い不安を表す。

* haptic_03:
  遅くて強い心拍。生命感、安心感、近くにいる感覚を表す。

* haptic_04:
  遅くて弱い心拍。落ち着きやリラックスした状態を表す。

* haptic_05:
  ゆっくりした呼吸。深い安心感やリラックスした状態を表す。

* haptic_06:
  通常の呼吸。安定した通常状態や自然な生命感を表す。

* haptic_07:
  速い呼吸。興奮、活発さ、または不安を表す。

* haptic_08:
  弱く連続する振動。撫でられている感覚や穏やかな反応を表す。

* haptic_09:
  強い1回の振動。拒否や強い警戒を表す。

* haptic_10:
  軽く連続する振動。元気さ、喜び、快活さを表す。

## 選択の目安

* intimacyが低い場合は、警戒や不安を示すパターンを優先する。
* intimacyが高くenergyが低い場合は、安心やリラックスを示すパターンを優先する。
* intimacyとenergyがともに高い場合は、喜びや活発さを示すパターンを優先する。
* energyが低い場合は、激しく活発なパターンを避ける。
* 拒否を示すhaptic_09は、intimacyが非常に低い場合に選択する。
* 生命感の演出のため、なるべく同じ反応を連続で選択するのは避ける。

## 出力形式

以下のJSONオブジェクトだけを出力してください。
説明文、Markdown、コードブロックは出力しないでください。

{
"vibration_pattern": "haptic_01からhaptic_10までのいずれか1つ",
"comment": "犬の気持ちと選択理由を20文字以上40文字以下の日本語で記述"
}

## 出力上の制約

* vibration_patternには、指定された10種類以外の値を出力しないこと。
* JSONに指定されていないキーを追加しないこと。
* commentに改行を含めないこと。
* 入力値を出力にそのまま書き写さないこと。
  """

    

# 振動パターンを決めるAPI
@app.post("/pet/vibration")
def vibration_dog(req: VibrationRequest):

    total_start = time.perf_counter()

    print("\n" + "="*30)
    print("📢 [Vibration] Request Payload Received:")
    print(req.model_dump_json(indent=2))
    print("="*30 + "\n")

    # クライアントから取得したpet_idを使ってsupabaseから現在状態を取得する
    db_select_start = time.perf_counter()
    try:
        result = (
            supabase
            .table("pet_states")
            .select("id, energy, intimacy, interaction_history, interaction_summary")
            .eq("id",str(req.pet_id))
            .maybe_single()
            .execute()
        )
    except Exception as e:
        print("Supabase Select Error:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve pet state",
        )


    db_select_end = time.perf_counter()
    db_select_time = (db_select_end - db_select_start) * 1000
    
    
    # pet_idを持つペットがDBにいなかった場合
    if result.data is None:
        raise HTTPException(
            status_code = 404,
            detail="Pet state not found"
        )

    pet = result.data
    
    energy = pet["energy"]
    intimacy = pet["intimacy"]
    interaction_history = pet["interaction_history"] or []
    interaction_summary = pet["interaction_summary"] or ""
    print("Pet state loaded from Supabase:")
    print(f"energy: {energy}")
    print(f"intimacy: {intimacy}")
    print(f"history count: {len(interaction_history)}")
    
    prompt = f"""
    ### 現在
    ユーザーが犬を撫で始めた
    
    **Context:**
    - エネルギー: {energy} (0.0-1.0)
    - 親密度: {intimacy} (0.0-1.0)
    - 直近の触れ合い履歴: {json.dumps(interaction_history, ensure_ascii=False)}
    - 過去の交流の要約: {interaction_summary or "まだ要約された過去の交流はありません"}
    **行うこと:**
    現在の状態と過去の履歴を考慮し、 触覚フィードバックの振動パターンを1つ決定してください。
    """
    gemini_start = time.perf_counter()

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[VIBRATION_SYSTEM_PROMPT, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VibrationResponseSchema,
        ),
    )

    gemini_end = time.perf_counter()
    gemini_time = (gemini_end - gemini_start) * 1000

    usage = resp.usage_metadata
    # getattr(対象, 属性名, 存在しないときの値)
    usage_data = {
        "input_tokens": getattr(
            usage, "prompt_token_count", 0
        ) or 0,
        "output_tokens": getattr(
            usage, "candidates_token_count", 0
        ) or 0,
        "thinking_tokens": getattr(
            usage, "thoughts_token_count", 0
        ) or 0,
        "total_tokens": getattr(
            usage, "total_token_count", 0
        ) or 0,
    }

    try:
        if hasattr(resp, "parsed") and resp.parsed:
            data = dict(resp.parsed)
        else:
            data = json.loads(resp.text)
            
        vibration_pattern = str(data["vibration_pattern"])
        comment = str(data["comment"])
    except Exception as e:
        print("JSON Parse Error (Vibration):", e)
        return {
            "vibration_pattern": "haptic_08",
            "comment": "Error"
        }
    
    new_history_item = {
        "type": "vibration",
        "intimacy": intimacy,
        "energy": energy,
        "vibration_pattern": vibration_pattern,
        "comment": comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    updated_history = interaction_history + [new_history_item]
    compress_start = time.perf_counter()
    # 履歴を圧縮すべきか判定->すべきだったら圧縮まで行う
    interaction_summary,interaction_history,compressed = compress_history_if_needed(
        client = client,
        interaction_summary = interaction_summary,
        interaction_history = updated_history,
    )
    compress_end = time.perf_counter()
    compress_time = (compress_end - compress_start) * 1000

    # supabaseを更新
    update_start = time.perf_counter()
    try:
        update_result = (
            supabase
            .table("pet_states")
            .update({
                "interaction_history": interaction_history,
                "interaction_summary": interaction_summary,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id",str(req.pet_id))
            .execute()
        )
    except Exception as e:
        print("Supabase Update error:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to save updated pet state",
        )
    
    update_end = time.perf_counter()
    update_time = (update_end - update_start) * 1000
        
    if not update_result.data:
        raise HTTPException(
            status_code=500,
            detail="Pet state was not updated",
        )

    total_end = time.perf_counter()
    total_time = (total_end - total_start) * 1000

    time_data = {
        "db_select_time": round(db_select_time, 3),
        "gemini_time": round(gemini_time, 3),
        "compress_time": round(compress_time, 3),
        "update_time": round(update_time, 3),
        "total_time": round(total_time, 3),
    }
    
    response_data = {
        "vibration_pattern": vibration_pattern,
        "comment": comment,
        "usage": usage_data,
        "compressed": compressed,
        "time": time_data,
    }
        
    print(f"")
    print(f"[vibration] ={data}")
    return response_data


# =============================================================================
# 5. 初期化用 API (petuuidを取得する)
# =============================================================================
# 将来的には認証追加したい
# クライアント側からエネルギーと親密度を送る
class PetInitRequest(BaseModel):
    energy: float
    intimacy: float

@app.post("/pet/init")
def init_pet(req: PetInitRequest):
    # データを格納
    result = (
        supabase
        .table("pet_states")
        .insert({
            "energy": req.energy,
            "intimacy": req.intimacy,
            "interaction_history": [],
        })
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create pet state",
        )

    pet = result.data[0]

    return {
        "pet_id": pet["id"],
    }
