"""
Avatar Module - Manajemen visual avatar dengan ekspresi
Mendukung multiple expression states berdasarkan emosi
"""

from pathlib import Path
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from PIL import Image, ImageTk
import customtkinter as ctk


@dataclass
class AvatarState:
    """State avatar dengan ekspresi"""
    name: str
    image_path: Optional[Path]
    emoji_fallback: str
    color: str


class AvatarManager:
    """
    Mengelola avatar dan ekspresi visual.
    
    Mendukung:
    - Image-based avatar (jika ada)
    - Emoji fallback (jika tidak ada gambar)
    - Smooth transition antar ekspresi
    """
    
    def __init__(self, avatar_dir: Path, expressions: Dict[str, str]):
        """
        Args:
            avatar_dir: Directory berisi gambar avatar
            expressions: Dict mapping emotion -> emoji fallback
        """
        self.avatar_dir = avatar_dir
        self.expressions = expressions
        self.states: Dict[str, AvatarState] = {}
        self.current_state: str = "neutral"
        self.image_cache: Dict[str, ImageTk.PhotoImage] = {}
        
        self._initialize_states()
    
    def _initialize_states(self):
        """Initialize avatar states dari expressions"""
        # Default colors untuk tiap emosi
        emotion_colors = {
            "neutral": "#39C5BB",
            "happy": "#FFD700",
            "excited": "#FF6B6B",
            "thinking": "#9B59B6",
            "confused": "#3498DB",
            "sad": "#5DADE2",
            "embarrassed": "#E91E63",
            "annoyed": "#E74C3C",
        }
        
        for emotion, emoji in self.expressions.items():
            # Cari gambar untuk emosi ini
            image_path = self._find_image(emotion)
            
            self.states[emotion] = AvatarState(
                name=emotion,
                image_path=image_path,
                emoji_fallback=emoji,
                color=emotion_colors.get(emotion, "#39C5BB")
            )
    
    def _find_image(self, emotion: str) -> Optional[Path]:
        """Cari file gambar untuk emosi tertentu"""
        extensions = ['.png', '.gif', '.jpg', '.jpeg']
        
        for ext in extensions:
            path = self.avatar_dir / f"{emotion}{ext}"
            if path.exists():
                return path
        
        return None
    
    def set_expression(self, emotion: str) -> Tuple[str, str]:
        """
        Set ekspresi avatar.
        
        Args:
            emotion: Nama emosi
            
        Returns:
            Tuple (display_content, color)
            display_content bisa path gambar atau emoji
        """
        if emotion not in self.states:
            emotion = "neutral"
        
        self.current_state = emotion
        state = self.states[emotion]
        
        if state.image_path and state.image_path.exists():
            return str(state.image_path), state.color
        else:
            return state.emoji_fallback, state.color
    
    def get_current_expression(self) -> Tuple[str, str]:
        """Get current expression"""
        return self.set_expression(self.current_state)
    
    def has_image(self, emotion: str) -> bool:
        """Check apakah ada gambar untuk emosi"""
        if emotion not in self.states:
            return False
        state = self.states[emotion]
        return state.image_path is not None and state.image_path.exists()
    
    def load_image(self, emotion: str, size: Tuple[int, int] = (200, 200)) -> Optional[ImageTk.PhotoImage]:
        """
        Load dan cache gambar avatar.
        
        Args:
            emotion: Nama emosi
            size: Ukuran gambar (width, height)
            
        Returns:
            PhotoImage atau None jika tidak ada
        """
        cache_key = f"{emotion}_{size[0]}x{size[1]}"
        
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]
        
        if emotion not in self.states:
            return None
        
        state = self.states[emotion]
        if not state.image_path or not state.image_path.exists():
            return None
        
        try:
            img = Image.open(state.image_path)
            img = img.resize(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.image_cache[cache_key] = photo
            return photo
        except Exception as e:
            print(f"[Avatar] Error loading image: {e}")
            return None
    
    def get_all_emotions(self) -> list:
        """Get list semua emosi yang tersedia"""
        return list(self.states.keys())
    
    def clear_cache(self):
        """Clear image cache"""
        self.image_cache.clear()


class AvatarWidget(ctk.CTkFrame):
    """
    Custom widget untuk menampilkan avatar dengan ekspresi.
    Bisa menampilkan gambar atau emoji dengan animasi transisi.
    """
    
    def __init__(self, master, avatar_manager: AvatarManager, size: int = 150, **kwargs):
        super().__init__(master, **kwargs)
        
        self.avatar_manager = avatar_manager
        self.avatar_size = size
        self.current_emotion = "neutral"
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create avatar display widgets"""
        # Container dengan corner radius
        self.configure(corner_radius=15)
        
        # Label untuk emoji (fallback)
        self.emoji_label = ctk.CTkLabel(
            self,
            text="😊",
            font=ctk.CTkFont(size=64),
            text_color=("#39C5BB", "#39C5BB")
        )
        self.emoji_label.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Label untuk nama karakter
        self.name_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.name_label.pack(pady=(0, 10))
    
    def set_character_name(self, name: str):
        """Set nama karakter"""
        self.name_label.configure(text=name)
    
    def update_expression(self, emotion: str):
        """Update ekspresi avatar"""
        self.current_emotion = emotion
        content, color = self.avatar_manager.set_expression(emotion)
        
        # Check apakah content adalah path atau emoji
        if content.endswith(('.png', '.gif', '.jpg', '.jpeg')):
            # TODO: Implement image display
            # Untuk sekarang fallback ke emoji
            state = self.avatar_manager.states.get(emotion)
            if state:
                self.emoji_label.configure(text=state.emoji_fallback)
        else:
            # Display emoji
            self.emoji_label.configure(text=content)
        
        # Update warna
        self.emoji_label.configure(text_color=(color, color))
    
    def get_current_emotion(self) -> str:
        """Get current emotion"""
        return self.current_emotion
