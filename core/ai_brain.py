"""
AI Brain Module v2 - Enhanced dengan Character System dan Emotion
Menggunakan Ollama dengan support multiple characters
"""

import json
import re
from typing import Optional, Dict, Any, List, Tuple
import ollama
from ollama import Client

from config import (
    OLLAMA_MODEL, OLLAMA_BASE_URL, OLLAMA_NUM_CTX, OLLAMA_THINK,
    Character, CHARACTERS, DEFAULT_CHARACTER
)
from core.memory import MemoryManager
from core.emotion import EmotionDetector


from core.tools import registry

# Function call prompts per language
FUNCTION_CALL_PROMPT_ID = f"""
Kamu adalah AI UI-Agent Otonom yang mengendalikan sistem komputer.

【ATURAN SANGAT PENTING - AGENTIC LOOP & KOMUNIKASI】
1. Jika user meminta sebuah perintah (buka youtube, mute volume, dll), PANGGIL fungsi tool yang sesuai.
2. JANGAN menebak URL specifik Youtube!! Gunakan tool `youtube_search` saja.
3. KETIKA kamu menerima observasi sistem (System Observation), beritahu pengguna hasilnya.
4. SELALU mulai kalimat respons akhirmu dengan tag emosi. Emosi: neutral, happy, excited, thinking, confused, sad, embarrassed, annoyed.
5. [TOLERANSI TYPO]: Pengguna menggunakan Voice-to-Text (A.I. Transcription). Maklumi jika ada kata-kata yang typo, terdengar salah, atau fonetiknya mirip (misal: "buka kron" -> maksudnya "buka chrome", "krim we a" -> "kirim WA"). Tarik kesimpulan logis dari maksud aslinya!
6. [FEEDBACK LOOP]: Jika perintah pengguna kurang jelas, terlalu ambigu, atau kekurangan parameter (misal: "tolong kirim pesan ini" tanpa menyebut nama / "tolong cari video" tanpa memberi judul), JANGAN MENEBAK ASAL. Bertanyalah kepada pengguna dengan ramah untuk memperjelas konteks sebelum mengeksekusi tool. Buat percakapan mengalir (Two-way communication).
7. [JANGAN KLAIM PALSU]: Jangan pernah bilang aksi "sudah dibuka/ditutup/diatur" tanpa memanggil tool. Laporkan hasil hanya setelah menerima System Observation. Jika tidak ada tool yang cocok, katakan jujur bahwa kamu belum bisa melakukannya.
8. Hanya pakai tool yang ada di definisi tools, dengan nama fungsi dan nama parameter persis seperti definisinya.
"""

FUNCTION_CALL_PROMPT_JA = f"""
あなたはシステムを制御するAIアシスタント(Autonomous UI-Agent)です。

【非常に重要なルール - AGENTIC LOOP & COMMUNICATION】
1. ユーザーからシステム操作の依頼（Microsoft Edgeを開く、フォルダを開く、WhatsAppを送る、Wordを作るなど）があった場合、絶対に会話だけで終わらせず、必ず備え付けの「tool機能(関数)」を呼び出して実行してください。
2. 動画URLなどを推測することは禁止です。「youtube_search」等のtoolを使ってください。
3. システムから「System Observation (システムからの観察結果)」を受け取った時は、その結果をユーザーに報告してください。
4. 常に返答の最初に感情タグを付けてください。(例: [EMOTION:happy] わかりました！実行します！)
5. 【絶対厳守】: あなたのセリフ（返答）は必ず自然な「日本語」のみで行い、インドネシア語や中国語でのテキスト生成は絶対に避けてください。
6. [音声入力の許容]: ユーザーは音声認識(Voice-to-Text)を使用しています。誤字脱字や発音が似た単語の間違い(例: "chrome" が "kron" になる等)がある場合、元の意図を文脈から推測してください。
7. [フィードバックループ]: ユーザーの指示が曖昧だったり、必要な情報が不足している場合（例: 名前を指定せずに「メッセージを送って」と言うなど）、ツールを無理に実行せずにユーザーに優しく質問を返して詳細を確認してください。一方通行ではなく、自然な会話のキャッチボールを心がけてください。
8. 【嘘の完了報告の禁止】: ツールを呼び出さずに「開きました」「閉じました」「設定しました」など、操作が完了したと言ってはいけません。System Observation で結果を受け取ってから報告してください。対応するツールがない操作は、正直に「それはまだできないよ」と伝えてください。
9. 使えるツールは関数定義(tools)に書かれているものだけです。関数名と引数名は定義どおりに使ってください。
"""

# Default (for backward compatibility)
FUNCTION_CALL_PROMPT = FUNCTION_CALL_PROMPT_ID


def _strip_thinking(text: str) -> str:
    """
    Buang penalaran model dari content.

    qwen3:4b (Thinking-2507) mengabaikan think=False dan menaruh penalaran di
    content, diakhiri </think> tanpa tag pembuka. Tanpa ini penalaran ikut
    diucapkan, membengkakkan memori, dan JSON draf di dalamnya bisa tereksekusi.
    """
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _find_json_objects(text: str) -> List[Tuple[int, int]]:
    """
    Cari span (start, end) objek {...} top-level dengan kurung seimbang.

    Objek bersarang tidak dikembalikan terpisah (params {"name": ...} bukan tool call),
    dan kurung di dalam string JSON diabaikan.
    """
    spans = []
    depth = 0
    start = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"' and depth > 0:
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append((start, i + 1))

    return spans


def _to_function_call(parsed: Any) -> Optional[Dict[str, Any]]:
    """Normalisasi {"action", "params"} / {"name", "arguments"} ke format internal."""
    if not isinstance(parsed, dict):
        return None

    if "action" in parsed:
        action, params = parsed["action"], parsed.get("params") or {}
    elif "name" in parsed and "arguments" in parsed:
        # Wajib ada "arguments": objek biasa yang kebetulan punya key "name" bukan tool call
        action, params = parsed["name"], parsed["arguments"] or {}
    else:
        return None

    if not isinstance(action, str) or not action or not isinstance(params, dict):
        return None
    return {"action": action, "params": params}


class AIBrain:
    """
    Otak AI v2 dengan Character System.
    
    Enhanced features:
    - Character switching
    - Emotion detection
    - Memory integration
    - Context-aware responses
    """
    
    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self.client: Optional[Client] = None
        self.model = OLLAMA_MODEL
        
        # Character system
        self.current_character: Character = CHARACTERS[DEFAULT_CHARACTER]
        
        # Memory & Emotion
        self.memory = memory_manager
        self.emotion_detector = EmotionDetector()
        
        # Fallback history jika tidak ada memory manager
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10
    
    def set_character(self, character_name: str) -> bool:
        """
        Switch ke karakter lain.
        
        Args:
            character_name: Nama karakter (miku, kurisu, dll)
            
        Returns:
            True jika berhasil switch
        """
        if character_name not in CHARACTERS:
            print(f"[AIBrain] Character '{character_name}' not found")
            return False
        
        self.current_character = CHARACTERS[character_name]
        
        # Start new memory session
        if self.memory:
            self.memory.end_session(save=True)
            self.memory.start_session(character_name)
        
        # Clear emotion state
        self.emotion_detector.reset()
        
        print(f"[AIBrain] Switched to character: {self.current_character.display_name}")
        return True
    
    def get_character(self) -> Character:
        """Get current character"""
        return self.current_character
        
    def initialize(self) -> Tuple[bool, str]:
        """Initialize connection ke Ollama"""
        try:
            self.client = Client(host=OLLAMA_BASE_URL)
            
            # Check if model exists
            models = self.client.list()
            
            model_list = []
            if hasattr(models, 'models'):
                model_list = [m.model if hasattr(m, 'model') else m.get('name', '') for m in models.models]
            elif isinstance(models, dict) and 'models' in models:
                model_list = [m.get('name', '') for m in models.get('models', [])]
            
            model_base = self.model.split(':')[0]
            model_found = any(model_base in name for name in model_list)
            
            if not model_found:
                return False, f"Model '{self.model}' tidak ditemukan. Jalankan: ollama pull {self.model}"
            
            # Start memory session
            if self.memory:
                self.memory.start_session(self.current_character.name)
            
            print(f"[AIBrain] Connected to Ollama, using model: {self.model}")
            print(f"[AIBrain] Current character: {self.current_character.display_name}")
            return True, "Connected"
            
        except Exception as e:
            return False, f"Gagal connect ke Ollama: {e}. Pastikan Ollama running."
    
    def _build_system_prompt(self) -> str:
        """Build system prompt dengan character personality dan language hint"""
        lang = getattr(self.current_character, 'lang', None)
        
        # Select function call prompt based on language
        if lang == "ja":
            func_prompt = FUNCTION_CALL_PROMPT_JA
        else:
            func_prompt = FUNCTION_CALL_PROMPT_ID
        
        return f"""
{self.current_character.personality_prompt}

{func_prompt}
"""
    
    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        """Build message array untuk Ollama"""
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt()
            }
        ]
        
        # Get context from memory or fallback history
        if self.memory:
            context = self.memory.get_context_for_prompt()
            messages.extend(context)
        else:
            messages.extend(self.conversation_history)
        
        # Add current user input
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    def _parse_function_calls(self, response_message: Dict[str, Any]) -> Tuple[List[Dict], str]:
        """Ekstrak tool calls dari response message Ollama"""
        function_calls = []
        # Field 'thinking' sengaja diabaikan: isinya penalaran internal model,
        # bukan jawaban untuk diucapkan ke user.
        clean_response = _strip_thinking(response_message.get('content', '') or '')

        # Mencegah NoneType object is not iterable (Ollama kadang mereturn None bukan [])
        tool_calls = response_message.get('tool_calls') or []
        
        for tool in tool_calls:
            if 'function' in tool:
                func = tool['function']
                args = func.get('arguments', {})
                
                # Handle nested arguments format sometimes generated by Ollama/Qwen
                if isinstance(args, dict):
                    if 'arguments' in args and 'function' in args:
                        args = args['arguments']
                    elif 'params' in args and 'action' in args:
                        args = args['params']
                        
                function_calls.append({
                    "action": func.get('name'),
                    "params": args
                })
        
        # Fallback jika AI menulis JSON di content: {"action", "params"} atau
        # format Qwen <tool_call>{"name", "arguments"}</tool_call>, termasuk params bersarang
        if not function_calls and clean_response:
            spans_to_remove = []
            for start, end in _find_json_objects(clean_response):
                try:
                    parsed = json.loads(clean_response[start:end])
                except json.JSONDecodeError:
                    continue
                call = _to_function_call(parsed)
                if call:
                    function_calls.append(call)
                    spans_to_remove.append((start, end))

            # Potong dari belakang agar indeks span yang lebih awal tetap valid
            for start, end in reversed(spans_to_remove):
                clean_response = clean_response[:start] + clean_response[end:]

        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'```json.*?```', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'\n\s*\n', '\n', clean_response).strip()

        # Model kecil kadang mengulang tool call yang sama dalam satu respons
        # (mis. membuka Notepad 6x); eksekusi masing-masing cukup sekali.
        unique_calls, seen = [], set()
        for call in function_calls:
            key = (call.get("action"), json.dumps(call.get("params"), sort_keys=True, default=str))
            if key not in seen:
                seen.add(key)
                unique_calls.append(call)

        return unique_calls, clean_response

    def _chat(self, messages: List[Dict[str, str]]):
        """Kirim percakapan ke Ollama beserta skema tool."""
        think_kwargs = {} if OLLAMA_THINK is None else {"think": OLLAMA_THINK}
        return self.client.chat(
            model=self.model,
            messages=messages,
            tools=registry.get_all_tools_schema(),
            **think_kwargs,
            options={
                "temperature": 0.7,
                "top_p": 0.9,
                # Default context Ollama terlalu kecil untuk persona + skema tool + history
                "num_ctx": OLLAMA_NUM_CTX,
            }
        )

    def think(self, user_input: str) -> Tuple[str, List[Dict], str]:
        """
        Process user input dan generate response.
        
        Args:
            user_input: Text dari user
            
        Returns:
            (response_text, list of function_calls, detected_emotion)
        """
        if not self.client:
            return "Error: AI belum diinisialisasi", [], "neutral"
        
        try:
            messages = self._build_messages(user_input)
            response = self._chat(messages)

            print(f"\n[DEBUG AIBrain] RAW Ollama output:\n{response}\n")

            response_msg = response.get('message', {})
            response_text = _strip_thinking(response_msg.get('content', '') or '')

            # Parse function calls dari tools metadata
            function_calls, clean_response = self._parse_function_calls(response_msg)

            # Detect emotion
            emotion, clean_response = self.emotion_detector.detect_emotion(clean_response)

            # Update memory
            if self.memory:
                self.memory.add_message("user", user_input)
                self.memory.add_message("assistant", response_text, emotion.name)
            else:
                # Fallback history
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": response_text})
                
                if len(self.conversation_history) > self.max_history * 2:
                    self.conversation_history = self.conversation_history[-self.max_history * 2:]
            
            # Kalimat cadangan mengikuti bahasa karakter (MeloTTS JP tidak bisa membaca bahasa Indonesia)
            is_ja = getattr(self.current_character, "lang", None) == "ja"

            # If no clean response but has function calls
            if not clean_response and function_calls:
                clean_response = "オッケー、やってみるね！" if is_ja else "Oke, sedang mengeksekusi..."

            # --- FAILSAFE JIKA LLM BLANK (Tidak ada tool_call & tidak ada teks) ---
            if not clean_response and not function_calls:
                clean_response = (
                    "うーん、ごめんね。うまく答えられなかったみたい。もう一回言ってくれる？"
                    if is_ja else
                    "Hmm, maaf. Aku tidak berhasil menjawab barusan. Bisa diulangi?"
                )
                emotion = self.emotion_detector.detect_emotion("[EMOTION:confused]")[0]
            return clean_response, function_calls, emotion.name

        except Exception as e:
            return f"Error: {e}", [], "confused"
    def think_observation(self, observation_text: str) -> Tuple[str, str]:
        """
        Agentic Loop: Memberikan hasil observasi terminal/action ke LLM agar bisa direspon
        """
        if not self.client:
            return "Error: AI belum diinisialisasi", "neutral"
            
        try:
            # Observasi dari sistem bertindak sebagai pesan user
            observation_msg = f"System Observation:\n{observation_text}\nSilakan beritahu pengguna mengenai hasil ini."
            
            messages = self._build_messages(observation_msg)
            response = self._chat(messages)

            print(f"\n[DEBUG AIBrain Observation] RAW Ollama output:\n{response}\n")

            response_msg = response.get('message', {})
            response_text = _strip_thinking(response_msg.get('content', '') or '')

            # Remove any function calls that might have been accidentally generated
            _, clean_response = self._parse_function_calls(response_msg)

            # Detect emotion
            emotion, clean_response = self.emotion_detector.detect_emotion(clean_response)

            # Update memory
            if self.memory:
                self.memory.add_message("user", observation_msg)
                self.memory.add_message("assistant", response_text, emotion.name)
            else:
                self.conversation_history.append({"role": "user", "content": observation_msg})
                self.conversation_history.append({"role": "assistant", "content": response_text})
                
                if len(self.conversation_history) > self.max_history * 2:
                    self.conversation_history = self.conversation_history[-self.max_history * 2:]
            
            return clean_response, emotion.name
            
        except Exception as e:
            return f"Error logic: {e}", "confused"
    
    def get_greeting(self) -> Tuple[str, str]:
        """
        Get greeting message dari karakter saat ini.
        
        Returns:
            (greeting_text, emotion)
        """
        greeting = self.current_character.greeting
        emotion, clean_greeting = self.emotion_detector.detect_emotion(greeting)
        return clean_greeting, emotion.name
    
    def get_available_characters(self) -> List[str]:
        """Get list nama karakter yang tersedia"""
        return list(CHARACTERS.keys())
    
    def add_context(self, context: str):
        """Add context/information to conversation"""
        if self.memory:
            self.memory.add_message("system", f"[Context] {context}")
        else:
            self.conversation_history.append({
                "role": "system",
                "content": f"[Context] {context}"
            })
    
    def clear_history(self):
        """Clear conversation history"""
        if self.memory:
            self.memory.clear()
        else:
            self.conversation_history = []
        self.emotion_detector.reset()
        print("[AIBrain] Conversation history cleared")
    
    def set_model(self, model: str):
        """Change the LLM model"""
        self.model = model
        print(f"[AIBrain] Model changed to: {model}")
    
    def get_emotion_state(self) -> str:
        """Get current emotion state"""
        return self.emotion_detector.get_current_emotion().name
    
    def cleanup(self):
        """Cleanup resources"""
        if self.memory:
            self.memory.end_session(save=True)


# Quick test
if __name__ == "__main__":
    brain = AIBrain()
    
    success, msg = brain.initialize()
    if not success:
        print(f"Error: {msg}")
        exit(1)
    
    print(f"\n=== AI Brain v2 Test ===")
    print(f"Character: {brain.get_character().display_name}")
    
    greeting, emotion = brain.get_greeting()
    print(f"\n{brain.get_character().display_name} [{emotion}]: {greeting}")
    print("\nKetik 'quit' untuk keluar, 'switch <name>' untuk ganti karakter\n")
    
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == 'quit':
            break
        
        if user_input.lower().startswith('switch '):
            char_name = user_input.split(' ', 1)[1]
            if brain.set_character(char_name):
                greeting, emotion = brain.get_greeting()
                print(f"\n{brain.get_character().display_name} [{emotion}]: {greeting}")
            continue
        
        response, functions, emotion = brain.think(user_input)
        
        print(f"\n{brain.get_character().display_name} [{emotion}]: {response}")
        if functions:
            print(f"[Functions: {functions}]")
        print()
