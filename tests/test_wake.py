"""T2 "Oke Miku": pencocokan frasa, gerbang VAD, pendengar, dan sambungannya ke mode suara dan GUI."""

import queue
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from core import wake
from core.wake import SpeechSegmenter, WakeListener, match_wake_phrase, wake_phrase_end

SR = 16000


# ── Pencocokan frasa ──

@pytest.mark.parametrize("text, expected", [
    ("Oke Miku", ""),
    ("Oke, Miku. Buka Notepad.", "Buka Notepad."),
    ("OK Miku", ""),
    ("Okay Miku, putar lagu", "putar lagu"),
    ("Okey, Miku-chan, tutup chrome", "tutup chrome"),
    ("eh oke miku tolong kecilkan volume", "tolong kecilkan volume"),
    ("オッケー、ミク", ""),
    ("オーケーミク、メモ帳を開いて", "メモ帳を開いて"),
    ("オッケーミクちゃん、音量を下げて", "音量を下げて"),
    ("ＯＫミク", ""),  # huruf lebar dari Whisper Jepang
    ("Oke Miku sandal", "sandal"),  # "san" di depan kata lain bukan sapaan
    ("Oke, migu", ""),  # ejaan Whisper untuk suara tertentu (experiments/wake_eval)
    ("Oke niku, kecilkan volume", "kecilkan volume"),
    ("Oke, migo.", ""),
    ("OK, Miuku", ""),
    ("OK、ミク、OK、ミク", ""),  # Whisper menulis wake phrase dua kali (uji suara sungguhan)
    ("Oke emigu, kecilkan volume", "kecilkan volume"),  # uji suara sungguhan
    ("Oke, amiku", ""),
    ("Oke Miku, Oke Miku, buka Notepad", "buka Notepad"),
])
def test_wake_phrase_and_command(text, expected):
    assert match_wake_phrase(text) == expected


@pytest.mark.parametrize("text", [
    "Oke, mikir dulu", "Book Miku", "Miku oke", "Hatsune Miku", "oke nanti saja", "Oke, minggu depan ya", "Oke Mikuni", "Oke, emang benar", "Oke, aman kok",
    "ミックスジュース", "オッケー、わかった", "", None,
])
def test_not_a_wake_phrase(text):
    assert match_wake_phrase(text) is None


def test_wake_phrase_end_from_word_timestamps():
    words = [(" Oke", 0.3, 0.55), (" Miku,", 0.55, 0.9), (" buka", 1.2, 1.4), (" Notepad", 1.4, 1.9)]
    assert wake_phrase_end(words) == 0.9
    assert wake_phrase_end([("オッケー", 0.2, 0.6), ("、", 0.6, 0.6), ("ミ", 0.6, 0.7), ("ク", 0.7, 0.85),
                            ("メモ帳", 1.0, 1.4)]) == 0.85
    assert wake_phrase_end([(" Buka", 0.1, 0.3), (" Notepad", 0.3, 0.8)]) is None
    assert wake_phrase_end([]) is None


# ── Gerbang VAD ──

class LoudVad:
    """VAD palsu: frame dianggap ucapan bila cukup keras."""

    def is_speech(self, pcm, sample_rate):
        return np.abs(np.frombuffer(pcm, dtype=np.int16)).mean() > 1000


def speech(seconds):
    return (0.3 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * SR)) / SR)).astype(np.float32)


def silence(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_silence_makes_no_segment():
    segmenter = SpeechSegmenter(vad=LoudVad())
    assert segmenter.feed(silence(5)) == []
    assert not segmenter.active


def test_segment_keeps_the_onset_and_ends_after_silence():
    segmenter = SpeechSegmenter(vad=LoudVad(), end_silence_ms=600)
    segments = segmenter.feed(np.concatenate([silence(1), speech(1.0), silence(1)]))

    assert len(segments) == 1
    seconds = len(segments[0]) / SR
    # 0,8 s sebelum segmen dimulai (VAD baru yakin ±0,18 s setelah ucapan mulai) + sisa ucapan
    # + 0,6 s hening penutup
    assert 2.1 <= seconds <= 2.3
    # Seluruh ucapan ada di segmen, termasuk awalnya
    assert np.abs(segments[0]).max() > 0.2 and np.abs(segments[0][:int(0.5 * SR)]).max() == 0
    assert not segmenter.active


def test_short_pause_does_not_split_a_segment():
    segmenter = SpeechSegmenter(vad=LoudVad(), end_silence_ms=600)
    audio = np.concatenate([speech(0.8), silence(0.3), speech(0.8), silence(1)])
    assert len(segmenter.feed(audio)) == 1


def test_long_speech_is_cut_at_max_length():
    segmenter = SpeechSegmenter(vad=LoudVad(), max_segment_sec=3.0)
    segments = segmenter.feed(speech(7.0))
    assert len(segments) == 2
    assert all(len(s) / SR == pytest.approx(3.0, abs=0.05) for s in segments)


# ── Pendengar ──

class FakeWhisper:
    """Teks per panggilan; panjang audio yang ditranskripsi dicatat."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.lengths = []

    def __call__(self, audio):
        self.lengths.append(len(audio) / SR)
        return self.texts.pop(0) if self.texts else ""


def listener(whisper, busy=lambda: False, **kwargs):
    wakes = []
    clock = SimpleNamespace(now=100.0)
    lst = WakeListener(whisper, wakes.append, is_busy=busy, clock=lambda: clock.now,
                       segmenter=SpeechSegmenter(vad=LoudVad()), **kwargs)
    lst.feed(silence(0.01))  # mulai hitung jeda sesudah sibuk
    clock.now += 10
    return lst, wakes, clock


def feed_in_chunks(lst, audio, chunk_sec=0.1):
    step = int(chunk_sec * SR)
    for i in range(0, len(audio), step):
        lst.feed(audio[i:i + step])


def test_silence_never_calls_whisper():
    whisper = FakeWhisper()
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, silence(30))
    assert whisper.lengths == [] and wakes == []
    assert lst.stats.audio_seconds == pytest.approx(30, abs=0.1)


def test_wake_phrase_alone():
    whisper = FakeWhisper("Oke Miku.")
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))
    assert wakes == [""]
    assert len(whisper.lengths) == 1


def test_command_spoken_together_with_wake_phrase():
    whisper = FakeWhisper("Oke Miku, buka Notepad.")
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1)]))
    assert wakes == []  # ditahan sebentar, siapa tahu perintahnya berlanjut
    feed_in_chunks(lst, silence(0.5))
    assert wakes == ["buka Notepad."]
    assert len(whisper.lengths) == 1  # segmen di bawah 2,5 s: sekali transkripsi saat selesai


def test_other_speech_does_not_wake():
    whisper = FakeWhisper("Nanti kita makan di luar ya.")
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1)]))
    assert wakes == [] and len(whisper.lengths) == 1


def test_long_command_waits_for_the_end_of_speech():
    # Jendela pertama (2,5 s) sudah memuat "Oke Miku"; perintah utuh diambil saat segmen selesai
    whisper = FakeWhisper("Oke Miku, tolong buka", "Oke Miku, tolong buka YouTube lalu cari lagu Hatsune Miku")
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(5.0), silence(1.5)]))

    assert wakes == ["tolong buka YouTube lalu cari lagu Hatsune Miku"]
    assert len(whisper.lengths) == 2
    assert whisper.lengths[1] > 5  # transkripsi kedua = seluruh segmen


def test_wake_phrase_in_the_middle_of_long_talk():
    # Jendela 1 (0-2,5 s): obrolan; jendela 2 (1,5-5 s, dengan tumpang tindih): wake phrase
    whisper = FakeWhisper("jadi tadi aku bilang", "Oke Miku matikan lagu", "Oke Miku matikan lagunya")
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(6.0), silence(1.5)]))
    assert wakes == ["matikan lagunya"]


def test_long_talk_is_transcribed_once_per_window():
    whisper = FakeWhisper()
    lst, wakes, _ = listener(whisper)
    feed_in_chunks(lst, np.concatenate([speech(10.0), silence(1)]))

    # 10,2 s ucapan: jendela di 2,5 / 5 / 7,5 / 10 s, lalu sisa ekor saat segmen selesai
    assert len(whisper.lengths) == 5
    assert max(whisper.lengths) <= 3.6  # jendela 2,5 s + tumpang tindih 1 s
    assert wakes == []


def test_cheap_check_then_full_transcription_for_the_command():
    # Cek wake phrase dengan Whisper murah (satu bahasa tetap); perintah dari transkripsi lengkap
    check = FakeWhisper("Oke Miku memo cho o hiraite")
    full = FakeWhisper("オッケー、ミク、メモ帳を開いて")
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1.5)]))

    assert wakes == ["メモ帳を開いて"]
    assert len(check.lengths) == 1 and len(full.lengths) == 1


def test_wake_phrase_alone_needs_no_full_transcription():
    check, full = FakeWhisper("Oke Miku."), FakeWhisper()
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))
    assert wakes == [""] and full.lengths == []


def test_other_speech_never_reaches_the_full_transcription():
    check, full = FakeWhisper("nanti malam hujan"), FakeWhisper()
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1)]))
    assert wakes == [] and full.lengths == []


def test_full_transcription_without_wake_phrase_keeps_the_checked_command():
    check = FakeWhisper("Oke Miku buka notepad")
    full = FakeWhisper("Buka Notepad")  # Whisper lengkap kadang membuang sapaan di depan
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1.5)]))
    assert wakes == ["Buka Notepad"]


def test_misheard_wake_phrase_in_full_transcription_keeps_the_command():
    # Uji suara sungguhan: cek "Oke, Miku, putar lagu di Youtube", transkripsi lengkap "Gameku, …";
    # ucapan > 2,5 s, jadi lewat jalur jendela
    check = FakeWhisper("Oke, Miku, putar lagu di")
    full = FakeWhisper("Gameku, putar lagu di Youtube")
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(3.0), silence(1.5)]))
    assert wakes == ["putar lagu di Youtube"]


def test_command_continued_after_a_short_pause_is_joined():
    # "Oke Miku, kecilkan volume … ke tiga puluh": jeda 0,7 s memotong segmen
    check = FakeWhisper("Oke Miku kecilkan volume")
    full = FakeWhisper("Oke Miku, kecilkan volume", "Oke Miku, kecilkan volume ke tiga puluh")
    lst, wakes, _ = listener(check, transcribe_command=full)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(0.7), speech(0.8), silence(1.5)]))

    assert wakes == ["kecilkan volume ke tiga puluh"]
    assert len(full.lengths) == 2 and full.lengths[1] > full.lengths[0]


def test_held_command_is_dropped_when_miku_gets_busy():
    state = SimpleNamespace(busy=False)
    lst, wakes, _ = listener(FakeWhisper("Oke Miku buka notepad"), busy=lambda: state.busy)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(0.7)]))
    state.busy = True
    feed_in_chunks(lst, silence(1))
    assert wakes == []


def test_command_is_transcribed_without_the_wake_phrase():
    # Uji suara sungguhan: "Oke Miku, buka Notepad" utuh tertulis 「OK、ミク、ブカ、Notepad」,
    # karena "Oke Miku" membuat Whisper memilih bahasa Jepang
    check = FakeWhisper("Oke Miku. Tukaramota")
    full = FakeWhisper("buka Notepad")
    lst, wakes, _ = listener(check, transcribe_command=full, wake_end=lambda: 0.9)
    feed_in_chunks(lst, np.concatenate([speech(1.5), silence(1.5)]))

    assert wakes == ["buka Notepad"]
    segment_seconds = check.lengths[0]
    assert full.lengths[0] == pytest.approx(segment_seconds - 0.9, abs=0.01)


def test_cut_on_a_long_segment_counts_from_the_window_start():
    check = FakeWhisper("bla bla", "Oke Miku putar")  # jendela 1 tanpa wake, jendela 2 dengan
    full = FakeWhisper("putar lagu di YouTube")
    lst, wakes, _ = listener(check, transcribe_command=full, wake_end=lambda: 1.2)
    feed_in_chunks(lst, np.concatenate([speech(7.0), silence(1.5)]))

    assert wakes == ["putar lagu di YouTube"]
    # Segmen 7,6 s (ucapan 7 s + hening penutup 0,6 s). Jendela 2 mulai di 2,5 - 1 = 1,5 s dan wake
    # phrase berakhir 1,2 s sesudahnya, jadi perintah = audio sesudah 2,7 s
    assert full.lengths[0] == pytest.approx(7.6 - 2.7, abs=0.1)


def test_loud_microphone_is_reported_once():
    warnings = []
    lst, _, _ = listener(FakeWhisper(), on_warning=warnings.append)
    rng = np.random.default_rng(0)
    feed_in_chunks(lst, (0.4 * rng.standard_normal(5 * SR)).astype(np.float32))
    assert len(warnings) == 1 and "terlalu tinggi" in warnings[0]


def test_normal_microphone_is_not_reported():
    warnings = []
    lst, _, _ = listener(FakeWhisper(), on_warning=warnings.append)
    rng = np.random.default_rng(0)
    feed_in_chunks(lst, (0.01 * rng.standard_normal(5 * SR)).astype(np.float32))
    assert warnings == []


def test_audio_while_busy_is_dropped_then_cooldown():
    whisper = FakeWhisper("Oke Miku", "Oke Miku")
    state = SimpleNamespace(busy=True)
    lst, wakes, clock = listener(whisper, busy=lambda: state.busy)

    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))  # Miku sedang bicara
    assert whisper.lengths == [] and wakes == []

    state.busy = False
    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))  # masih dalam jeda 0,5 s
    assert wakes == []

    clock.now += 1
    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))
    assert wakes == [""]


def test_transcription_error_does_not_stop_the_listener():
    def broken(audio):
        raise RuntimeError("CUDA OOM")

    lst, wakes, _ = listener(broken)
    feed_in_chunks(lst, np.concatenate([speech(0.9), silence(1)]))
    assert wakes == [] and lst.stats.transcriptions == 1


def test_start_and_stop_with_microphone_stream():
    lst = WakeListener(FakeWhisper(), lambda command: None)
    assert lst.start() is None  # stream palsu dari conftest
    assert lst._thread.is_alive()
    lst.stop()
    assert lst._thread is None


def test_microphone_error_is_reported(monkeypatch):
    def no_mic(sample_rate, callback):
        raise OSError("No Default Input Device Available")

    monkeypatch.setattr(wake, "_open_input_stream", no_mic)
    error = WakeListener(FakeWhisper(), lambda command: None).start()
    assert "mikrofon tidak bisa dibuka" in error


# ── Mode suara (miku.py) ──

voice_mode = pytest.mark.skipif(sys.platform == "win32", reason="miku.py membungkus stdout di Windows")


class NoTriggers:
    hotkey_active = False

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return []

    def stop(self):
        pass


class FakeWake:
    command = ""
    instances = []

    def __init__(self, transcribe, on_wake, is_busy, transcribe_command, wake_end, on_warning):
        self.transcribe, self.on_wake, self.is_busy = transcribe, on_wake, is_busy
        self.transcribe_command, self.wake_end, self.on_warning = transcribe_command, wake_end, on_warning
        self.stopped = False
        FakeWake.instances.append(self)

    def start(self):
        threading.Timer(0.2, lambda: self.on_wake(FakeWake.command)).start()
        return None

    def stop(self):
        self.stopped = True


def _voice_mode(monkeypatch, tmp_path, command, enabled=True):
    from core import desktop
    monkeypatch.setattr(desktop, "user_dir", lambda key: tmp_path)
    import miku

    monkeypatch.setattr(miku, "ListenTriggers", NoTriggers)
    monkeypatch.setattr(miku, "WakeListener", FakeWake)
    monkeypatch.setattr(miku, "WAKE_PHRASE_ENABLED", enabled)
    monkeypatch.setattr(FakeWake, "command", command)
    monkeypatch.setattr(FakeWake, "instances", [])
    monkeypatch.setattr(miku, "initialize_avatar_window", lambda *a, **k: MagicMock())
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    cli = miku.MikuCLI()
    cli.ai_brain = MagicMock()
    cli.ai_brain.get_greeting.return_value = ("Halo", "happy")
    cli.voice_output = MagicMock()
    cli.voice_input = MagicMock()
    cli.system_control = MagicMock()

    def stop(*args, **kwargs):
        cli._quit_event = True
        return np.array([])

    cli.voice_input.listen_until_silence.side_effect = stop
    cli._process_ai_response = MagicMock(side_effect=stop)
    if not enabled:
        threading.Timer(0.3, lambda: setattr(cli, "_quit_event", True)).start()
    cli.chat_voice_mode()
    return cli


@voice_mode
def test_voice_mode_runs_command_spoken_with_wake_phrase(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "buka Notepad")

    cli._process_ai_response.assert_called_once_with("buka Notepad")
    cli.voice_input.listen_until_silence.assert_not_called()
    assert [c.args[0] for c in cli.voice_output.speak.call_args_list] == ["Halo"]


@voice_mode
def test_voice_mode_wake_phrase_alone_answers_then_listens(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "")

    assert [c.args[0] for c in cli.voice_output.speak.call_args_list] == ["Halo", "はい、何でしょうか？"]
    cli.voice_input.listen_until_silence.assert_called_once()


@voice_mode
def test_voice_mode_wake_listener_is_busy_while_handling_or_speaking(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "buka Notepad")
    lst = FakeWake.instances[0]

    cli.voice_output = SimpleNamespace(is_speaking=False)
    cli._handling = False
    assert not lst.is_busy()
    cli._handling = True
    assert lst.is_busy()
    cli._handling = False
    cli.voice_output.is_speaking = True
    assert lst.is_busy()


@voice_mode
def test_voice_mode_checks_cheaply_then_transcribes_the_command_fully(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "buka Notepad")
    lst = FakeWake.instances[0]
    audio = np.zeros(SR, dtype=np.float32)

    lst.transcribe(audio)
    assert cli.voice_input.transcribe.call_args.kwargs == {"lang": "id", "beam_size": 1, "prompt": "Oke Miku.",
                                                          "word_timestamps": True, "verbose_logging": False}
    lst.transcribe_command(audio)
    assert cli.voice_input.transcribe.call_args.kwargs == {"languages": ["ja", "id"], "verbose_logging": False}


@voice_mode
def test_voice_mode_without_wake_phrase(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "", enabled=False)
    assert FakeWake.instances == [] and cli.wake is None


@voice_mode
def test_voice_mode_cleanup_stops_the_wake_listener(monkeypatch, tmp_path):
    cli = _voice_mode(monkeypatch, tmp_path, "buka Notepad")
    cli.cleanup()
    assert FakeWake.instances[0].stopped


# ── GUI ──

real_customtkinter = pytest.mark.skipif(
    isinstance(sys.modules.get("customtkinter"), MagicMock), reason="butuh customtkinter asli")


def _gui_app(**state):
    app = SimpleNamespace(message_queue=queue.Queue(), is_listening=False, is_processing=False,
                          voice_output=SimpleNamespace(is_speaking=False), _process_input=MagicMock(),
                          _listen_after_wake=MagicMock(), _add_chat_message=MagicMock())
    for key, value in state.items():
        setattr(app, key, value)
    return app


def _join_threads():
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(timeout=1)


@real_customtkinter
def test_gui_wake_from_listener_thread_only_queues():
    import gui
    app = _gui_app()
    gui.MikuGUIv4._on_wake_phrase(app, "buka Notepad")
    assert app.message_queue.get_nowait() == ("wake", "buka Notepad")


@real_customtkinter
def test_gui_wake_with_command_processes_it():
    import gui
    app = _gui_app()
    gui.MikuGUIv4._on_wake(app, "buka Notepad")
    _join_threads()
    app._process_input.assert_called_once_with("buka Notepad")
    app._add_chat_message.assert_called_once_with("You", "🎤 buka Notepad", "")


@real_customtkinter
def test_gui_wake_alone_listens_and_busy_wake_is_ignored():
    import gui
    app = _gui_app()
    gui.MikuGUIv4._on_wake(app, "")
    _join_threads()
    app._listen_after_wake.assert_called_once()
    assert app.is_listening  # tetap benar sampai rekaman selesai

    busy = _gui_app(is_processing=True)
    gui.MikuGUIv4._on_wake(busy, "buka Notepad")
    busy._process_input.assert_not_called()
    busy._listen_after_wake.assert_not_called()


@real_customtkinter
def test_gui_listen_after_wake_answers_records_and_hands_over(monkeypatch):
    import gui
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    audio = np.ones(SR, dtype=np.float32)
    app = _gui_app(is_listening=True, current_character=SimpleNamespace(lang="ja"),
                   voice_output=MagicMock(), voice_input=MagicMock(), _update_status=MagicMock(),
                   _handle_recorded_audio=MagicMock())
    app.voice_input.listen_until_silence.return_value = audio

    gui.MikuGUIv4._listen_after_wake(app)

    app.voice_output.speak.assert_called_once_with("はい、何でしょうか？", blocking=True)
    app._handle_recorded_audio.assert_called_once_with(audio)
    assert not app.is_listening


@real_customtkinter
def test_gui_wake_busy_while_listening_processing_or_speaking():
    import gui
    assert not gui.MikuGUIv4._wake_busy(_gui_app())
    assert gui.MikuGUIv4._wake_busy(_gui_app(is_listening=True))
    assert gui.MikuGUIv4._wake_busy(_gui_app(is_processing=True))
    assert gui.MikuGUIv4._wake_busy(_gui_app(voice_output=SimpleNamespace(is_speaking=True)))
