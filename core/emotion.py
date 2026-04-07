"""
Emotion Module - Deteksi dan manajemen emosi karakter
Inspired by Amadeus project emotional system
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass
from config import EMOTIONS, Emotion


class EmotionDetector:
    """
    Mendeteksi emosi dari respons AI dan mengelola state emosi.
    
    AI diharapkan menyertakan tag [EMOTION:nama] di respons.
    Jika tidak ada, kita coba deteksi dari konten.
    """
    
    # Pattern untuk mendeteksi tag emosi explicit
    EMOTION_TAG_PATTERN = re.compile(r'\[EMOTION:(\w+)\]', re.IGNORECASE)
    
    # Keywords untuk deteksi emosi implicit
    EMOTION_KEYWORDS = {
        "happy": ["senang", "yeay", "yay", "hore", "bagus", "hebat", "suka", "happy", "glad"],
        "excited": ["wah", "wow", "keren", "amazing", "luar biasa", "excited", "mantap"],
        "thinking": ["hmm", "mungkin", "sepertinya", "coba", "pikirkan", "think", "consider"],
        "confused": ["bingung", "tidak mengerti", "apa maksud", "confused", "unclear"],
        "sad": ["sedih", "maaf", "sayang sekali", "sad", "sorry", "unfortunately"],
        "embarrassed": ["malu", "aduh", "eh", "um", "embarrassed", "blush"],
        "annoyed": ["jangan", "berhenti", "cukup", "annoyed", "irritating", "stop"],
    }
    
    def __init__(self):
        self.current_emotion: Emotion = EMOTIONS["neutral"]
        self.emotion_history: list = []
        self.max_history = 10
    
    def detect_emotion(self, text: str) -> Tuple[Emotion, str]:
        """
        Deteksi emosi dari teks dan kembalikan (emosi, teks_bersih).
        
        Args:
            text: Teks respons AI
            
        Returns:
            Tuple (Emotion, cleaned_text tanpa tag emosi)
        """
        # Coba deteksi dari tag explicit dulu
        match = self.EMOTION_TAG_PATTERN.search(text)
        
        if match:
            emotion_name = match.group(1).lower()
            if emotion_name in EMOTIONS:
                emotion = EMOTIONS[emotion_name]
                # Hapus tag dari teks
                clean_text = self.EMOTION_TAG_PATTERN.sub('', text).strip()
                self._update_emotion(emotion)
                return emotion, clean_text
        
        # Fallback: deteksi dari keywords
        detected = self._detect_from_keywords(text)
        self._update_emotion(detected)
        return detected, text
    
    def _detect_from_keywords(self, text: str) -> Emotion:
        """Deteksi emosi berdasarkan keywords dalam teks"""
        text_lower = text.lower()
        
        # Hitung skor untuk setiap emosi
        scores = {}
        for emotion_name, keywords in self.EMOTION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[emotion_name] = score
        
        # Ambil emosi dengan skor tertinggi
        if scores:
            best_emotion = max(scores, key=scores.get)
            return EMOTIONS.get(best_emotion, EMOTIONS["neutral"])
        
        return EMOTIONS["neutral"]
    
    def _update_emotion(self, emotion: Emotion):
        """Update current emotion dan history"""
        self.current_emotion = emotion
        self.emotion_history.append(emotion)
        
        # Trim history
        if len(self.emotion_history) > self.max_history:
            self.emotion_history = self.emotion_history[-self.max_history:]
    
    def get_current_emotion(self) -> Emotion:
        """Get current emotion state"""
        return self.current_emotion
    
    def get_dominant_emotion(self) -> Emotion:
        """Get emosi yang paling sering muncul dalam history"""
        if not self.emotion_history:
            return EMOTIONS["neutral"]
        
        # Count occurrences
        counts = {}
        for em in self.emotion_history:
            counts[em.name] = counts.get(em.name, 0) + 1
        
        dominant_name = max(counts, key=counts.get)
        return EMOTIONS.get(dominant_name, EMOTIONS["neutral"])
    
    def reset(self):
        """Reset emotion state"""
        self.current_emotion = EMOTIONS["neutral"]
        self.emotion_history.clear()


class EmotionRenderer:
    """
    Render visual representation of emotions.
    Bisa digunakan untuk update avatar/UI berdasarkan emosi.
    """
    
    def __init__(self, character_expressions: dict):
        """
        Args:
            character_expressions: Dict mapping emotion name -> emoji/avatar state
        """
        self.expressions = character_expressions
    
    def get_expression(self, emotion: Emotion) -> str:
        """Get visual expression untuk emosi tertentu"""
        return self.expressions.get(emotion.name, self.expressions.get("neutral", "😊"))
    
    def get_theme_color(self, emotion: Emotion) -> str:
        """Get warna tema untuk emosi"""
        return emotion.color


# Utility functions
def extract_emotion_and_clean(text: str) -> Tuple[str, str]:
    """
    Quick utility untuk extract emotion name dan clean text.
    
    Returns:
        Tuple (emotion_name, cleaned_text)
    """
    pattern = re.compile(r'\[EMOTION:(\w+)\]', re.IGNORECASE)
    match = pattern.search(text)
    
    if match:
        emotion_name = match.group(1).lower()
        clean_text = pattern.sub('', text).strip()
        return emotion_name, clean_text
    
    return "neutral", text
