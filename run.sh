#!/usr/bin/env bash
# Menjalankan GUI MikuVision di Linux (setara run.bat)
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Dibuka dari menu aplikasi (tanpa terminal): output dicatat ke file log
if [ ! -t 1 ]; then
    mkdir -p data/logs
    exec >>data/logs/gui.log 2>&1
fi

echo "================================================"
echo "  MikuVision - Hatsune Miku Edition"
echo "================================================"
echo

# Folder model dari install.sh --model-dir (HF_HOME, OLLAMA_MODELS). environment.d baru terbaca di
# sesi login berikutnya, jadi dibaca di sini juga; yang sudah ada di environment tidak ditimpa
env_file="${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-mikuvision.conf"
if [ -r "$env_file" ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            HF_HOME|OLLAMA_MODELS)
                if [ -z "${!key:-}" ] && [ -n "$value" ]; then export "$key=$value"; fi ;;
        esac
    done <"$env_file"
fi

# Pakai env dari install.sh bila ada (lokasinya sama dengan yang dipilih install.sh);
# selain itu python dari env yang sedang aktif
for python in \
    "${MIKU_VENV:+$MIKU_VENV/bin/python}" \
    ".venv/bin/python" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/mikuvision/venv/bin/python"; do
    if [ -n "$python" ] && [ -x "$python" ]; then
        exec "$python" gui.py "$@"
    fi
done
exec python3 gui.py "$@"
