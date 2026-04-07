import sys

path = "E:/A DIVA PROJECT/MikuWin/v10/config.py"
with open(path, "r", encoding="utf-8") as f:
    body = f.read()

# Buang sintaks lama, ganti ke sintaks baru (menambahkan fitur macro v10)
body = body.replace(
    '- get_system_info: {} - システム情報を取得',
    '- get_system_info: {} - システム情報を取得\n- create_word_document: {"filename": "nama_file", "content": "isi teks"} - Word Documentを作成\n- create_powerpoint: {"filename": "nama_file", "title": "judul", "content": "isi"} - PPTを作成\n- send_whatsapp_message: {"contact_name": "name", "message": "text"} - WhatsAppを送信\n- send_telegram_message: {"contact_name": "name", "message": "text"} - Telegramを送信'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(body)

print("INJECTION SUCCESS")
