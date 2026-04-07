"""
Memory Module - Konteks dan memori percakapan
Menyimpan history interaksi untuk konteks yang lebih baik
"""

import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Message:
    """Single message dalam conversation"""
    role: str  # "user" atau "assistant"
    content: str
    timestamp: str
    emotion: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass 
class ConversationContext:
    """Konteks percakapan saat ini"""
    messages: List[Message]
    character_name: str
    session_start: str
    user_name: Optional[str] = None
    summary: Optional[str] = None


class MemoryManager:
    """
    Mengelola memori percakapan dan konteks.
    
    Features:
    - Short-term memory (current session)
    - Context window management
    - Conversation summarization
    """
    
    def __init__(self, data_dir: Path, max_context_messages: int = 20):
        """
        Args:
            data_dir: Directory untuk menyimpan data
            max_context_messages: Maksimum pesan dalam context window
        """
        self.data_dir = data_dir
        self.max_context = max_context_messages
        self.conversations_dir = data_dir / "conversations"
        self.conversations_dir.mkdir(exist_ok=True)
        
        self.current_context: Optional[ConversationContext] = None
        self.session_id: Optional[str] = None
    
    def start_session(self, character_name: str, user_name: Optional[str] = None):
        """Mulai session percakapan baru"""
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_context = ConversationContext(
            messages=[],
            character_name=character_name,
            session_start=datetime.now().isoformat(),
            user_name=user_name
        )
        print(f"[Memory] Session started: {self.session_id}")
    
    def add_message(self, role: str, content: str, emotion: Optional[str] = None):
        """
        Tambah pesan ke memori.
        
        Args:
            role: "user" atau "assistant"
            content: Isi pesan
            emotion: Emosi yang terdeteksi (untuk assistant)
        """
        if not self.current_context:
            self.start_session("unknown")
        
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            emotion=emotion
        )
        
        self.current_context.messages.append(message)
        
        # Trim jika melebihi context window
        if len(self.current_context.messages) > self.max_context:
            self._trim_context()
    
    def _trim_context(self):
        """Trim pesan lama dari context"""
        if len(self.current_context.messages) <= self.max_context:
            return
        
        # Simpan beberapa pesan terakhir
        excess = len(self.current_context.messages) - self.max_context
        
        # TODO: Bisa implement summarization untuk pesan yang di-trim
        self.current_context.messages = self.current_context.messages[excess:]
    
    def get_context_for_prompt(self) -> List[Dict[str, str]]:
        """
        Get messages dalam format yang siap untuk prompt LLM.
        
        Returns:
            List of {"role": str, "content": str}
        """
        if not self.current_context:
            return []
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.current_context.messages
        ]
    
    def get_recent_messages(self, count: int = 5) -> List[Message]:
        """Get N pesan terakhir"""
        if not self.current_context:
            return []
        return self.current_context.messages[-count:]
    
    def save_session(self):
        """Simpan session ke file"""
        if not self.current_context or not self.session_id:
            return
        
        filepath = self.conversations_dir / f"session_{self.session_id}.json"
        
        data = {
            "session_id": self.session_id,
            "character": self.current_context.character_name,
            "start_time": self.current_context.session_start,
            "end_time": datetime.now().isoformat(),
            "user_name": self.current_context.user_name,
            "messages": [asdict(m) for m in self.current_context.messages]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[Memory] Session saved: {filepath}")
    
    def load_session(self, session_id: str) -> bool:
        """Load session dari file"""
        filepath = self.conversations_dir / f"session_{session_id}.json"
        
        if not filepath.exists():
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            messages = [
                Message(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m["timestamp"],
                    emotion=m.get("emotion"),
                    metadata=m.get("metadata")
                )
                for m in data.get("messages", [])
            ]
            
            self.session_id = data["session_id"]
            self.current_context = ConversationContext(
                messages=messages,
                character_name=data["character"],
                session_start=data["start_time"],
                user_name=data.get("user_name")
            )
            
            print(f"[Memory] Session loaded: {session_id}")
            return True
            
        except Exception as e:
            print(f"[Memory] Failed to load session: {e}")
            return False
    
    def get_session_summary(self) -> str:
        """Generate ringkasan session"""
        if not self.current_context:
            return "No active session"
        
        msg_count = len(self.current_context.messages)
        user_msgs = sum(1 for m in self.current_context.messages if m.role == "user")
        
        return (
            f"Session: {self.session_id}\n"
            f"Character: {self.current_context.character_name}\n"
            f"Messages: {msg_count} ({user_msgs} from user)\n"
            f"Started: {self.current_context.session_start}"
        )
    
    def clear(self):
        """Clear current memory"""
        if self.current_context:
            self.current_context.messages.clear()
    
    def end_session(self, save: bool = True):
        """End current session"""
        if save:
            self.save_session()
        self.current_context = None
        self.session_id = None
