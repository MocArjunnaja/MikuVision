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
