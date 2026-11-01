#!/usr/bin/env bash
# Installer satu-langkah MikuVision untuk Linux (setara install.ps1).
#
# Menyiapkan:
#   1. Paket sistem lewat apt, dnf, pacman, atau zypper (ditanya dulu): git, PortAudio,
#      dan tool desktop
#   2. uv (versi dipatok, checksum diverifikasi)
#   3. Python terisolasi + virtualenv
#   4. PyTorch (CUDA bila ada GPU NVIDIA, CPU bila tidak) + requirements.txt
#      (+ rvc-python bila model RVC sudah diletakkan di models/miku_default_rvc)
#   5. Kamus unidic untuk MeloTTS
#   6. Ollama + model LLM dari config.py (OLLAMA_MODEL)
#   7. Peluncur MikuVision di menu aplikasi dan Desktop
#   8. Verifikasi dengan `miku.py --test`
#
# Lokasi env: bila folder repo ada di partisi NTFS/FAT (misalnya dipakai bersama Windows),
# uv, Python, dan venv disimpan di ~/.local/share/mikuvision karena venv di NTFS lambat.
# Selain itu di .tools/ dan .venv/ dalam folder repo. Timpa dengan MIKU_VENV=/path/venv.
#
# Aman dijalankan ulang: langkah yang sudah beres dilewati.
# Log lengkap ada di logs/install-<waktu>.log.
#
# Pemakaian: ./install.sh [opsi]
#   --yes              Jawab "ya" otomatis (paket sistem dan Ollama)
#   --cpu              Paksa PyTorch versi CPU walaupun ada GPU NVIDIA
#   --with-rvc         Pasang rvc-python walau model RVC belum ada
#   --skip-ollama      Lewati Ollama dan pull model (verifikasi ikut dilewati)
#   --skip-shortcut    Jangan buat peluncur di Desktop (tanpa --menu-entry: menu aplikasi juga dilewati)
#   --menu-entry       Buat peluncur di menu aplikasi (bersama --skip-shortcut: hanya di menu)
#   --skip-test        Jangan jalankan `miku.py --test` di akhir
#   --python-version V Versi Python env (default 3.10; fairseq/RVC tidak jalan di 3.11)
#   --model-dir DIR    Cache Hugging Face (Whisper, MeloTTS) di DIR/huggingface. Model Ollama ke
#                      DIR/ollama bila Ollama dijalankan user sendiri; Ollama yang berjalan sebagai
#                      layanan sistem (installer resmi) tetap memakai lokasinya
#   --with-vision      Unduh juga model visi (VISION_MODEL di config.py) untuk membaca layar
#   --rvc-model PTH    File bobot RVC (.pth), disalin ke models/miku_default_rvc; bersama --rvc-index
#   --rvc-index INDEX  File index RVC (.index), disalin ke models/miku_default_rvc; bersama --rvc-model
#   --sudo-cmd CMD     Perintah untuk hak root (bawaan sudo; MikuVision Setup memakai pkexec)
#   --progress         Untuk MikuVision Setup: cetak juga satu baris "##MIKU {json}" per kejadian
#                      (step, warn, error, done), format sama dengan install.ps1 -Progress
#
# Kode keluar: 0 selesai, 1 gagal yang sudah dijelaskan, 2 error tak terduga.

set -u -o pipefail

# ---------------------------------------------------------------- konstanta
UV_VERSION="0.11.2"
UV_SHA256="7ac2ca0449c8d68dae9b99e635cd3bc9b22a4cb1de64b7c43716398447d42981"
UV_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
TORCH_VERSION="2.11.0"
RVC_PYTHON_VERSION="0.1.5"   # 0.1.0 memakai API load_model lama yang tidak cocok dengan core/voice_converter.py
OLLAMA_INSTALL_URL="https://ollama.com/install.sh"
APP_NAME="MikuVision"
# Nama file index yang dibaca config.py (RVCConfig.index_path); --rvc-index disalin dengan nama ini
RVC_INDEX_NAME="added_IVF4457_Flat_nprobe_1_miku_default_rvc_v2.index"

YES=0; CPU=0; WITH_RVC=0; SKIP_OLLAMA=0; SKIP_SHORTCUT=0; SKIP_TEST=0
MENU_ENTRY=0; WITH_VISION=0; PROGRESS=0; SELF_CHECK=0
PYTHON_VERSION="3.10"
MODEL_DIR=""; RVC_MODEL=""; RVC_INDEX=""; SUDO_CMD="sudo"
while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) YES=1 ;;
        --cpu) CPU=1 ;;
        --with-rvc) WITH_RVC=1 ;;
        --skip-ollama) SKIP_OLLAMA=1 ;;
        --skip-shortcut) SKIP_SHORTCUT=1 ;;
        --menu-entry) MENU_ENTRY=1 ;;
        --skip-test) SKIP_TEST=1 ;;
        --python-version) shift; PYTHON_VERSION="${1:?--python-version butuh nilai}" ;;
        --model-dir) shift; MODEL_DIR="${1:?--model-dir butuh folder}" ;;
        --with-vision) WITH_VISION=1 ;;
        --rvc-model) shift; RVC_MODEL="${1:?--rvc-model butuh file .pth}" ;;
        --rvc-index) shift; RVC_INDEX="${1:?--rvc-index butuh file .index}" ;;
        --sudo-cmd) shift; SUDO_CMD="${1:?--sudo-cmd butuh perintah}" ;;
        --progress) PROGRESS=1 ;;
        # Untuk tests/test_install_sh.py: hanya memancarkan tiga baris ##MIKU lalu keluar
        --self-check) SELF_CHECK=1 ;;
        -h|--help) sed -n '2,/^$/s/^# \{0,1\}//p' "$0"; exit 0 ;;
        *) echo "Opsi tidak dikenal: $1 (lihat --help)" >&2; exit 2 ;;
    esac
    shift
done

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/mikuvision"

# venv di filesystem Windows lewat FUSE (ntfs-3g) lambat dan tidak mendukung semua fitur POSIX
case "$(stat -f -c %T "$ROOT" 2>/dev/null)" in
    fuseblk|ntfs|ntfs3|msdos|vfat|exfat) TOOLS_DIR="$DATA_HOME"; DEFAULT_VENV="$DATA_HOME/venv" ;;
    *) TOOLS_DIR="$ROOT/.tools"; DEFAULT_VENV="$ROOT/.venv" ;;
esac
VENV_DIR="${MIKU_VENV:-$DEFAULT_VENV}"
VENV_PY="$VENV_DIR/bin/python"
UV_DIR="$TOOLS_DIR/uv"
UV="$UV_DIR/uv"
RVC_DIR="$ROOT/models/miku_default_rvc"
if [ "$SELF_CHECK" -eq 1 ]; then
    LOG_DIR="${TMPDIR:-/tmp}/mikuvision-selfcheck"
else
    LOG_DIR="$ROOT/logs"
fi
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
OLLAMA_URL="http://127.0.0.1:11434"
# --model-dir: HF_HOME dan OLLAMA_MODELS untuk sesi login berikutnya (systemd environment.d),
# setara variabel user di Windows. run.sh membacanya, jadi berlaku sejak MikuVision dibuka lagi.
MODEL_ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-mikuvision.conf"

# Data uv (Python, cache unduhan) di samping venv: filesystem sama, jadi uv memakai hardlink
export UV_PYTHON_INSTALL_DIR="$TOOLS_DIR/python"
export UV_CACHE_DIR="$TOOLS_DIR/uv-cache"
export UV_NO_PROGRESS=1
export PATH="$PATH:/usr/sbin:/sbin"   # ldconfig

# ---------------------------------------------------------------- helper
if [ -t 1 ]; then
    C_RED=$'\e[31m'; C_YEL=$'\e[33m'; C_GRN=$'\e[32m'; C_OFF=$'\e[0m'
else
    C_RED=""; C_YEL=""; C_GRN=""; C_OFF=""
fi

# --progress: baris mesin untuk MikuVision Setup, satu JSON per baris (miku_setup/runner.py parse_progress)
STEP_INDEX=0
STEP_TOTAL=0

json_str() {
    local s="$1"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
    # Karakter kontrol lain tidak boleh mentah di JSON; tidak ada di pesan installer, jadi dibuang
    s="$(printf '%s' "$s" | tr -d '\000-\010\013\014\016-\037')"
    printf '"%s"' "$s"
}

emit() {
    [ "$PROGRESS" -eq 1 ] || [ "$SELF_CHECK" -eq 1 ] || return 0
    printf '##MIKU %s\n' "$1"
}

# NO_EVENT=1 log ...: baris penutup error (lokasi log) tidak menimpa pesan error di wizard
log() {
    local level="$1"; shift
    local line
    line="[$(date +%H:%M:%S)] [$level] $*"
    printf '%s\n' "$line" >>"$LOG_FILE"
    case "$level" in
        WARN) printf '%s\n' "$C_YEL$line$C_OFF" ;;
        ERROR) printf '%s\n' "$C_RED$line$C_OFF" ;;
        OK) printf '%s\n' "$C_GRN$line$C_OFF" ;;
        *) printf '%s\n' "$line" ;;
    esac
    if { [ "$level" = WARN ] || [ "$level" = ERROR ]; } && [ "${NO_EVENT:-0}" -ne 1 ]; then
        local event
        event="$(printf '%s' "$level" | tr '[:upper:]' '[:lower:]')"
        emit "{\"event\":\"$event\",\"message\":$(json_str "$*")}"
    fi
}

step() {
    STEP_INDEX=$((STEP_INDEX + 1))
    log INFO ""
    log INFO "==== $1 ===="
    emit "{\"event\":\"step\",\"index\":$STEP_INDEX,\"total\":$STEP_TOTAL,\"title\":$(json_str "$1")}"
}

# 1 setelah die atau selesai; selain itu EXIT berarti error tak terduga (kode 2)
FINISHED=0

die() {
    log ERROR "$1"
    NO_EVENT=1 log ERROR "Instalasi berhenti. Perbaiki masalah di atas lalu jalankan installer lagi (langkah yang sudah beres akan dilewati)."
    NO_EVENT=1 log ERROR "Log lengkap: $LOG_FILE"
    FINISHED=1
    emit '{"event":"done","ok":false}'
    exit 1
}

# Keluar tanpa die (misalnya variabel tak terdefinisi di bawah set -u): error tak terduga
on_exit() {
    local code=$?
    [ "$FINISHED" -eq 1 ] && return
    FINISHED=1
    log ERROR "Error tak terduga di installer (kode $code). Kirim log saat melapor."
    NO_EVENT=1 log ERROR "Log lengkap: $LOG_FILE"
    emit '{"event":"done","ok":false}'
    exit 2
}

on_signal() {
    FINISHED=1
    NO_EVENT=1 log WARN "Installer dihentikan."
    exit 130
}

# Menjalankan program; stdout+stderr masuk ke log. Mengembalikan exit code program.
run() {
    local quiet=0 code
    if [ "${1:-}" = "--quiet" ]; then quiet=1; shift; fi
    log INFO "> $*"
    if [ "$quiet" -eq 1 ]; then
        "$@" >>"$LOG_FILE" 2>&1
        code=$?
    else
        "$@" 2>&1 | sed -u 's/^/    /' | tee -a "$LOG_FILE"
        code=${PIPESTATUS[0]}
    fi
    return "$code"
}

# Hak root lewat --sudo-cmd (sudo di terminal, pkexec dari MikuVision Setup)
as_root() { run "$SUDO_CMD" "$@"; }

# Tanpa terminal (misalnya dijalankan dari skrip lain) jawabannya "tidak"
confirm() {
    local answer=""
    if [ "$YES" -eq 1 ]; then
        log INFO "$1 -> ya (--yes)"
        return 0
    fi
    # /dev/tty selalu ada, tapi gagal dibuka bila proses tidak punya terminal
    if { exec 3</dev/tty; } 2>/dev/null; then
        read -r -p "$1 (y/n) " answer <&3 || answer=""
        exec 3<&-
    else
        answer="n (tanpa terminal)"
    fi
    log INFO "$1 -> $answer"
    [[ "$answer" =~ ^([yY]|ya|yes)$ ]]
}

# Tanpa -q: grep -q berhenti lebih awal, ldconfig kena SIGPIPE, dan pipefail menganggapnya gagal
have_lib() { ldconfig -p 2>/dev/null | grep "$1" >/dev/null; }

# Package manager distro ini (apt, dnf, pacman, zypper), atau kosong bila tidak dikenal.
# ID lalu ID_LIKE di os-release: Linux Mint -> "ubuntu debian", Manjaro -> "arch".
pkg_manager() {
    local file="${1:-/etc/os-release}" ids="" id cmd
    [ -r "$file" ] && ids="$(. "$file" && echo "${ID:-} ${ID_LIKE:-}")"
    for id in $ids; do
        case "$id" in
            debian|ubuntu) echo apt; return ;;
            fedora|rhel|centos) echo dnf; return ;;
            arch) echo pacman; return ;;
            suse|opensuse|opensuse-*|sles) echo zypper; return ;;
        esac
    done
    for cmd in apt-get dnf pacman zypper; do
        if command -v "$cmd" >/dev/null; then
            [ "$cmd" = apt-get ] && cmd=apt
            echo "$cmd"
            return
        fi
    done
}

# Nama paket Debian -> nama paket di package manager $1 (dicek di repo Fedora 42, Arch,
# openSUSE Tumbleweed/Leap 15.6). Nama yang tidak dipetakan sama di semua distro.
pkg_names() {
    local pm="$1" name; shift
    for name in "$@"; do
        case "$pm:$name" in
            dnf:libportaudio2|pacman:libportaudio2) echo portaudio ;;
            dnf:build-essential|zypper:build-essential) echo gcc-c++ make ;;
            pacman:build-essential) echo base-devel ;;
            *) echo "$name" ;;
        esac
    done
}

# Perintah pasang paket untuk package manager $1 (tanpa nama paket), diawali --sudo-cmd
pkg_install_cmd() {
    case "$1" in
        apt) echo "$SUDO_CMD apt-get install -y" ;;
        dnf) echo "$SUDO_CMD dnf install -y" ;;
        # Tanpa -y (sinkron database): -Sy tanpa -u bisa membuat sistem setengah ter-upgrade
        pacman) echo "$SUDO_CMD pacman -S --needed --noconfirm" ;;
        zypper) echo "$SUDO_CMD zypper --non-interactive install" ;;
    esac
}

# ver_ge A B: A >= B
ver_ge() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]; }

free_gb() {
    local dir="$1"
    while [ ! -d "$dir" ]; do dir="$(dirname "$dir")"; done
    df -Pk "$dir" | awk 'NR==2 {printf "%.1f", $4 / 1048576}'
}

rvc_model_present() {
    [ -f "$RVC_DIR/weights/miku_default_rvc.pth" ] && compgen -G "$RVC_DIR/logs/miku_default_rvc/*.index" >/dev/null
}

# Nilai string di config.py, misalnya config_value OLLAMA_MODEL -> qwen3:4b-instruct
config_value() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$ROOT/config.py" | head -n1
}

# Nilai $1 (HF_HOME, OLLAMA_MODELS) di MODEL_ENV_FILE, atau kosong
model_env_value() {
    [ -r "$MODEL_ENV_FILE" ] || return 0
    sed -n "s/^$1=//p" "$MODEL_ENV_FILE" | tail -n1
}

# Tulis $1=$2 ke MODEL_ENV_FILE (baris lama untuk $1 diganti)
set_model_env() {
    local name="$1" value="$2" tmp
    mkdir -p "$(dirname "$MODEL_ENV_FILE")" || die "Folder $(dirname "$MODEL_ENV_FILE") tidak bisa dibuat."
    tmp="$(mktemp "$MODEL_ENV_FILE.XXXXXX")" || die "File sementara di $(dirname "$MODEL_ENV_FILE") tidak bisa dibuat."
    { grep -v "^$name=" "$MODEL_ENV_FILE" 2>/dev/null; printf '%s=%s\n' "$name" "$value"; } >"$tmp"
    mv -f "$tmp" "$MODEL_ENV_FILE"
}

# Variabel dari --model-dir sebelumnya: environment.d baru terbaca di sesi login berikutnya.
# Yang sudah ada di environment proses ini tidak ditimpa.
load_model_env() {
    local name value
    for name in HF_HOME OLLAMA_MODELS; do
        value="$(model_env_value "$name")"
        if [ -z "${!name:-}" ] && [ -n "$value" ]; then
            export "$name=$value"
        fi
    done
}

# Ollama berjalan sebagai layanan sistem (installer resmi: user "ollama", model di home user itu)
ollama_system_service() {
    command -v systemctl >/dev/null && systemctl cat ollama.service >/dev/null 2>&1
}

# Lokasi model layanan sistem Ollama: OLLAMA_MODELS di unit, atau ~/.ollama/models milik user layanannya
ollama_service_models_dir() {
    local env user home
    env="$(systemctl show ollama -p Environment --value 2>/dev/null)"
    if [[ " $env " =~ \ OLLAMA_MODELS=([^ ]+)\  ]]; then
        echo "${BASH_REMATCH[1]}"
        return
    fi
    user="$(systemctl show ollama -p User --value 2>/dev/null)"
    home="$(getent passwd "${user:-ollama}" 2>/dev/null | cut -d: -f6)"
    echo "${home:-/usr/share/ollama}/.ollama/models"
}

# ---------------------------------------------------------------- langkah
# Setiap fungsi langkah memanggil step tepat sekali (dicek tests/test_install_sh.py), supaya total
# langkah di --progress sama dengan daftar dari install_steps.
install_steps() {
    local steps=(check_system)
    [ -n "$MODEL_DIR" ] && steps+=(set_model_dir)
    { [ -n "$RVC_MODEL" ] || [ -n "$RVC_INDEX" ]; } && steps+=(copy_rvc_model)
    steps+=(install_uv install_python_env install_python_packages install_unidic check_imports)
    if [ "$SKIP_OLLAMA" -eq 0 ]; then
        steps+=(install_ollama_model)
        [ "$WITH_VISION" -eq 1 ] && steps+=(install_vision_model)
    fi
    steps+=(show_rvc_status)
    { [ "$SKIP_SHORTCUT" -eq 0 ] || [ "$MENU_ENTRY" -eq 1 ]; } && steps+=(create_launcher)
    { [ "$SKIP_TEST" -eq 0 ] && [ "$SKIP_OLLAMA" -eq 0 ]; } && steps+=(run_self_test)
    echo "${steps[*]}"
}

PKG_MANAGER=""   # diisi check_system: apt, dnf, pacman, zypper, atau kosong

check_system() {
    step "Cek sistem"
    [ "$(uname -m)" = "x86_64" ] || die "Butuh Linux x86_64 (terdeteksi $(uname -m))."
    local distro="Linux"
    [ -r /etc/os-release ] && distro="$(. /etc/os-release && echo "$PRETTY_NAME")"
    log INFO "$distro, kernel $(uname -r), sesi ${XDG_SESSION_TYPE:-tidak diketahui}"
    log INFO "Folder aplikasi: $ROOT"
    log INFO "Lokasi env: $VENV_DIR"
    if [ "$TOOLS_DIR" = "$DATA_HOME" ]; then
        log INFO "Folder aplikasi ada di partisi Windows (NTFS/FAT); uv, Python, dan venv disimpan di $DATA_HOME."
    fi
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
        log WARN "Sesi Wayland: aksi keyboard/mouse (pyautogui, xdotool) tidak jalan. Pilih sesi X11 di layar login untuk fitur lengkap."
    fi

    local free
    free="$(free_gb "$VENV_DIR")"
    log INFO "Ruang kosong di lokasi env: $free GB"
    # Saat dijalankan ulang env sudah memakai ruangnya; cukup cek pada instalasi pertama
    if [ ! -x "$VENV_PY" ] && ! ver_ge "$free" "12"; then
        log WARN "Butuh sekitar 12 GB (Python env + model). Ruang tersisa $free GB."
        confirm "Lanjutkan walau ruang disk mungkin kurang?" || die "Dibatalkan: ruang disk kurang."
    fi

    PKG_MANAGER="$(pkg_manager)"
    if [ -n "$PKG_MANAGER" ] && command -v "${PKG_MANAGER/apt/apt-get}" >/dev/null; then
        log INFO "Package manager: $PKG_MANAGER"
    else
        log WARN "Package manager tidak dikenali (didukung: apt, dnf, pacman, zypper); paket sistem harus dipasang sendiri."
        PKG_MANAGER=""
    fi

    local required=() optional=()
    command -v git >/dev/null || required+=(git)            # MeloTTS diunduh dari GitHub
    command -v curl >/dev/null || required+=(curl)
    have_lib libportaudio.so.2 || required+=(libportaudio2)  # sounddevice tidak membawa PortAudio di Linux
    # Untuk aksi desktop di Linux (lihat docs/PLAN_LINUX.md)
    local tool
    for tool in xdotool wmctrl playerctl xclip; do
        command -v "$tool" >/dev/null || optional+=("$tool")
    done
    # fairseq (dependency rvc-python) dikompilasi saat instalasi
    if { [ "$WITH_RVC" -eq 1 ] || [ -n "$RVC_MODEL" ] || rvc_model_present; } && ! command -v g++ >/dev/null; then
        optional+=(build-essential)
    fi

    if [ ${#required[@]} -gt 0 ] || [ ${#optional[@]} -gt 0 ]; then
        # Daftar di atas memakai nama Debian; terjemahkan ke nama di distro ini
        local need=() want=() cmd=()
        read -r -a need <<<"$(pkg_names "$PKG_MANAGER" "${required[@]}" | tr '\n' ' ')"
        read -r -a want <<<"$(pkg_names "$PKG_MANAGER" "${optional[@]}" | tr '\n' ' ')"
        read -r -a cmd <<<"$(pkg_install_cmd "$PKG_MANAGER")"
        local all=("${need[@]}" "${want[@]}")
        [ ${#need[@]} -gt 0 ] && log WARN "Paket wajib belum ada: ${need[*]}"
        [ ${#want[@]} -gt 0 ] && log WARN "Paket disarankan belum ada: ${want[*]}"
        if [ ${#cmd[@]} -gt 0 ] && confirm "Pasang sekarang lewat $PKG_MANAGER (${cmd[*]} ${all[*]})?"; then
            run "${cmd[@]}" "${all[@]}" || die "$PKG_MANAGER gagal memasang ${all[*]}."
        elif [ ${#need[@]} -gt 0 ]; then
            die "Paket wajib belum terpasang: ${need[*]}. Pasang lewat package manager lalu jalankan installer lagi."
        else
            log WARN "Dilewati. Sebagian aksi desktop atau RVC mungkin tidak jalan."
        fi
    fi
    log INFO "Git: $(git --version)"
}

# --model-dir: dijalankan sebelum miku.py --test, yang membaca HF_HOME. OLLAMA_MODELS diatur di
# install_ollama_model, karena baru di sana ketahuan apakah Ollama layanan sistem atau milik user.
set_model_dir() {
    step "Folder model"
    case "$MODEL_DIR" in *'"'*) die "Folder model tidak boleh berisi tanda kutip: $MODEL_DIR" ;; esac
    MODEL_DIR="$(realpath -m -- "$MODEL_DIR")"
    use_model_env HF_HOME "$MODEL_DIR/huggingface"
}

# $1 (HF_HOME/OLLAMA_MODELS) = folder $2: buat foldernya, catat di MODEL_ENV_FILE, dan pakai di proses ini
OLLAMA_MODELS_CHANGED=0
use_model_env() {
    local name="$1" path="$2" previous
    mkdir -p "$path" || die "Folder $path tidak bisa dibuat."
    previous="$(model_env_value "$name")"
    if [ "$previous" != "$path" ]; then
        set_model_env "$name" "$path"
        [ "$name" = OLLAMA_MODELS ] && OLLAMA_MODELS_CHANGED=1
        [ -n "$previous" ] && log WARN "$name sebelumnya $previous. Isinya tidak dipindah; model yang belum ada di folder baru akan diunduh lagi."
    fi
    export "$name=$path"
    log OK "$name = $path"
}

copy_rvc_file() {
    local source="$1" ext="$2" target="$3"
    [ -f "$source" ] || die "File RVC tidak ditemukan: $source"
    # Huruf besar-kecil ekstensi diabaikan, sama seperti install.ps1
    [[ "${source,,}" == *"$ext" ]] || die "File RVC harus berakhiran $ext: $source"
    mkdir -p "$(dirname "$target")" || die "Folder $(dirname "$target") tidak bisa dibuat."
    if [ -e "$target" ] && [ "$source" -ef "$target" ]; then
        log OK "Sudah di tempatnya: $source"
        return
    fi
    cp -f -- "$source" "$target" || die "Gagal menyalin $source ke $target."
    log OK "Disalin: $source -> $target"
}

copy_rvc_model() {
    step "Model RVC"
    if [ -z "$RVC_MODEL" ] || [ -z "$RVC_INDEX" ]; then
        die "--rvc-model dan --rvc-index harus dipakai bersama: file bobot .pth dan file .index."
    fi
    copy_rvc_file "$(realpath -m -- "$RVC_MODEL")" .pth "$RVC_DIR/weights/miku_default_rvc.pth"
    copy_rvc_file "$(realpath -m -- "$RVC_INDEX")" .index "$RVC_DIR/logs/miku_default_rvc/$RVC_INDEX_NAME"
}

install_uv() {
    step "uv $UV_VERSION"
    if [ -x "$UV" ]; then
        local current
        current="$("$UV" --version 2>/dev/null)"
        if [[ "$current" == "uv $UV_VERSION"* ]]; then
            log OK "Sudah terpasang: $current"
            return
        fi
        log INFO "Versi lain ditemukan ($current), diganti."
    fi
    local tmp
    tmp="$(mktemp -d)"
    log INFO "Mengunduh $UV_URL"
    if ! curl -fsSL --retry 3 -o "$tmp/uv.tar.gz" "$UV_URL"; then
        rm -rf "$tmp"
        die "Gagal mengunduh uv. Cek koneksi internet."
    fi
    local hash
    hash="$(sha256sum "$tmp/uv.tar.gz" | cut -d' ' -f1)"
    if [ "$hash" != "$UV_SHA256" ]; then
        rm -rf "$tmp"
        die "Checksum uv tidak cocok (dapat $hash). Unduhan rusak atau dimodifikasi."
    fi
    tar -xzf "$tmp/uv.tar.gz" -C "$tmp" || { rm -rf "$tmp"; die "Gagal mengekstrak uv."; }
    mkdir -p "$UV_DIR"
    mv -f "$tmp"/uv-*/uv "$tmp"/uv-*/uvx "$UV_DIR/"
    rm -rf "$tmp"
    log OK "Terpasang: $("$UV" --version)"
}

install_python_env() {
    step "Python $PYTHON_VERSION + virtualenv"
    run "$UV" python install "$PYTHON_VERSION" --no-bin || die "uv gagal memasang Python $PYTHON_VERSION."
    local base
    base="$("$UV" python find "$PYTHON_VERSION" --python-preference only-managed 2>/dev/null)"
    [ -n "$base" ] || die "Python $PYTHON_VERSION terpasang tapi tidak ditemukan oleh uv."

    if [ -d "$VENV_DIR" ]; then
        local version=""
        # pyvenv.cfg hilang = venv rusak (misalnya pembuatan sebelumnya terputus)
        if [ -x "$VENV_PY" ] && [ -f "$VENV_DIR/pyvenv.cfg" ]; then
            version="$("$VENV_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
        fi
        if [ "$version" = "$PYTHON_VERSION" ]; then
            log OK "venv sudah ada (Python $version)"
            return
        fi
        log WARN "venv (Python '$version') dibuat ulang."
        rm -rf "$VENV_DIR"
    fi
    mkdir -p "$(dirname "$VENV_DIR")"
    run "$base" -m venv --without-pip "$VENV_DIR" || die "Gagal membuat virtualenv di $VENV_DIR."
}

# Mengisi BACKEND: cu128 (default), cu126 untuk driver lama, cpu tanpa GPU NVIDIA
BACKEND=""
torch_backend() {
    if [ "$CPU" -eq 1 ]; then
        log WARN "--cpu dipakai: PyTorch versi CPU."
        BACKEND=cpu; return
    fi
    if ! command -v nvidia-smi >/dev/null; then
        log WARN "GPU NVIDIA tidak terdeteksi. Memakai PyTorch CPU: Whisper dan TTS akan jauh lebih lambat. Pertimbangkan WHISPER_MODEL = 'small' di config.py."
        BACKEND=cpu; return
    fi
    local header
    if ! header="$(nvidia-smi 2>&1)"; then
        # Contoh: driver baru dipasang tapi belum reboot, nouveau masih aktif
        die "nvidia-smi gagal: driver NVIDIA terpasang tapi belum aktif. Reboot dulu, atau jalankan ulang dengan --cpu."
    fi
    log INFO "GPU: $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader)"
    local cuda
    cuda="$(printf '%s' "$header" | sed -n 's/.*CUDA Version: *\([0-9]*\.[0-9]*\).*/\1/p' | head -n1)"
    if [ -z "$cuda" ]; then
        log WARN "Versi CUDA dari nvidia-smi tidak terbaca. Memakai cu128."
        BACKEND=cu128; return
    fi
    log INFO "Driver mendukung CUDA sampai $cuda"
    if ver_ge "$cuda" "12.8"; then BACKEND=cu128; return; fi
    if ver_ge "$cuda" "12.6"; then BACKEND=cu126; return; fi
    log WARN "Driver NVIDIA terlalu lama untuk PyTorch $TORCH_VERSION (butuh CUDA >= 12.6). Memakai CPU; perbarui driver lalu jalankan installer lagi untuk GPU."
    BACKEND=cpu
}

RVC_INSTALLED=0

install_python_packages() {
    # Sebelum judul langkah: judulnya memuat backend (cu128/cu126/cpu)
    torch_backend
    local backend="$BACKEND"
    step "PyTorch $TORCH_VERSION ($backend) + requirements.txt"
    local want="$TORCH_VERSION+$backend" installed
    installed="$("$VENV_PY" -c 'import torch; print(torch.__version__)' 2>/dev/null)"
    local args=(pip install --python "$VENV_PY"
        -r "$ROOT/requirements.txt"
        "torch==$TORCH_VERSION" "torchaudio==$TORCH_VERSION"
        --torch-backend "$backend")
    if [ -n "$installed" ] && [ "$installed" != "$want" ]; then
        log INFO "torch $installed terpasang, diganti ke $want."
        args+=(--reinstall-package torch --reinstall-package torchaudio)
    fi

    # rvc-python ikut satu resolusi dengan requirements.txt supaya versi numpy/scipy
    # tidak bolak-balik di setiap jalan ulang
    if [ "$WITH_RVC" -eq 1 ] || rvc_model_present; then
        log INFO "Model RVC ditemukan (atau --with-rvc): rvc-python ikut dipasang."
        if run "$UV" "${args[@]}" "rvc-python==$RVC_PYTHON_VERSION" --override "$ROOT/overrides-rvc.txt"; then
            RVC_INSTALLED=1
        else
            log WARN "rvc-python gagal dipasang. fairseq harus dikompilasi dan butuh compiler C++ ($(pkg_install_cmd "${PKG_MANAGER:-apt}") $(pkg_names "${PKG_MANAGER:-apt}" build-essential | tr '\n' ' ')). Lanjut tanpa RVC."
        fi
    fi
    if [ "$RVC_INSTALLED" -eq 0 ]; then
        run "$UV" "${args[@]}" || die "Instalasi paket Python gagal. Lihat detail di log."
    fi

    installed="$("$VENV_PY" -c 'import torch; print(torch.__version__)' 2>/dev/null)"
    [ "$installed" = "$want" ] || die "torch yang terpasang '$installed', seharusnya '$want'."
    if [ "$backend" != "cpu" ]; then
        local cuda_ok
        cuda_ok="$("$VENV_PY" -c 'import torch; print(torch.cuda.is_available())' 2>/dev/null)"
        [ "$cuda_ok" = "True" ] || die "torch $installed terpasang tapi CUDA tidak bisa dipakai. Cek driver NVIDIA (nvidia-smi), atau jalankan ulang dengan --cpu."
    fi
    log OK "torch $installed siap"
}

install_unidic() {
    step "Kamus unidic (MeloTTS Jepang)"
    local dicdir
    dicdir="$("$VENV_PY" -c 'import unidic; print(unidic.DICDIR)' 2>/dev/null)"
    [ -n "$dicdir" ] || die "Paket unidic tidak terpasang."
    if [ -f "$dicdir/mecabrc" ]; then
        log OK "Sudah diunduh: $dicdir"
        return
    fi
    log INFO "Mengunduh kamus (sekitar 500 MB, sekali saja)..."
    if ! run --quiet "$VENV_PY" -m unidic download || [ ! -f "$dicdir/mecabrc" ]; then
        die "Gagal mengunduh kamus unidic. Coba manual: $VENV_PY -m unidic download"
    fi
    log OK "Kamus unidic siap"
}

check_imports() {
    step "Cek import modul"
    run "$VENV_PY" -c "import torch, faster_whisper, melo.api, customtkinter, pygame, ollama, sounddevice, webrtcvad, psutil; print('import OK')" \
        || die "Ada modul yang gagal di-import. Lihat log."
}

ollama_up() { curl -fsS --max-time 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

wait_ollama() {
    local deadline=$((SECONDS + 45))
    until ollama_up; do
        [ "$SECONDS" -lt "$deadline" ] || die "Server Ollama tidak merespons di $OLLAMA_URL. Jalankan 'ollama serve' lalu jalankan installer lagi."
        sleep 2
    done
}

# Ollama milik user (bukan layanan sistem) yang sedang jalan dengan lokasi model lama: matikan,
# karena Ollama membaca OLLAMA_MODELS hanya saat start
stop_user_ollama() {
    pkill -u "$(id -u)" -x ollama 2>/dev/null
    local deadline=$((SECONDS + 15))
    while ollama_up; do
        [ "$SECONDS" -lt "$deadline" ] || die "Ollama tidak bisa dimatikan. Hentikan 'ollama serve' lalu jalankan installer lagi."
        sleep 1
    done
}

ollama_pull() {
    local model="$1"
    if curl -fsS --max-time 10 "$OLLAMA_URL/api/tags" \
        | "$VENV_PY" -c 'import json, sys; print("\n".join(m["name"] for m in json.load(sys.stdin)["models"]))' \
        | grep -Fx "$model" >/dev/null; then
        log OK "Model $model sudah ada"
        return
    fi
    log INFO "Mengunduh model $model (beberapa GB)..."
    run --quiet ollama pull "$model" || die "ollama pull $model gagal."
    log OK "Model $model siap"
}

install_ollama_model() {
    step "Ollama + model LLM"
    if ! command -v ollama >/dev/null; then
        confirm "Ollama belum terpasang. Pasang sekarang lewat skrip resmi ($OLLAMA_INSTALL_URL, butuh hak root)?" \
            || die "Ollama dibutuhkan. Pasang secara manual (https://ollama.com/download/linux) lalu jalankan installer ini lagi."
        local tmp
        tmp="$(mktemp -d)"
        curl -fsSL --retry 3 -o "$tmp/ollama-install.sh" "$OLLAMA_INSTALL_URL" || { rm -rf "$tmp"; die "Gagal mengunduh skrip Ollama."; }
        # Lewat sudo di terminal (skrip memanggil sudo sendiri bila perlu); lewat --sudo-cmd lain
        # (pkexec dari Setup) seluruh skrip dijalankan sebagai root, satu kali minta password
        if [ "$SUDO_CMD" = sudo ]; then
            run sh "$tmp/ollama-install.sh"
        else
            as_root sh "$tmp/ollama-install.sh"
        fi
        local code=$?
        rm -rf "$tmp"
        [ "$code" -eq 0 ] || die "Skrip Ollama gagal (exit $code)."
        hash -r
        command -v ollama >/dev/null || die "Ollama sudah dipasang tapi tidak ada di PATH. Buka terminal baru lalu jalankan installer lagi."
    fi
    log INFO "Ollama: $(ollama --version 2>&1 | tail -n1)"

    local service=0
    ollama_system_service && service=1
    if [ -n "$MODEL_DIR" ]; then
        if [ "$service" -eq 1 ]; then
            # Memindahkan model layanan sistem butuh chown ke user "ollama" dan drop-in systemd,
            # dan folder di dalam /home biasanya tidak bisa dibaca user lain: tidak dilakukan
            log WARN "Ollama berjalan sebagai layanan sistem; modelnya tetap di $(ollama_service_models_dir). Hanya cache Whisper dan MeloTTS yang dipindah ke $MODEL_DIR/huggingface."
        else
            use_model_env OLLAMA_MODELS "$MODEL_DIR/ollama"
            if [ "$OLLAMA_MODELS_CHANGED" -eq 1 ] && ollama_up; then
                log INFO "Ollama sedang jalan dengan lokasi model lama; dinyalakan ulang."
                stop_user_ollama
            fi
        fi
    fi

    if ! ollama_up; then
        log INFO "Server Ollama belum jalan, menyalakan..."
        if [ "$service" -eq 1 ]; then
            as_root systemctl start ollama
        else
            mkdir -p "$LOG_DIR"
            nohup ollama serve >>"$LOG_DIR/ollama-serve.log" 2>&1 &
        fi
        wait_ollama
    fi
    if [ "$service" -eq 1 ] && systemctl is-active --quiet ollama 2>/dev/null; then
        log INFO "Ollama jalan sebagai service systemd; model disimpan di $(ollama_service_models_dir) (atur OLLAMA_MODELS lewat 'sudo systemctl edit ollama')."
    fi

    local model
    model="$(config_value OLLAMA_MODEL)"
    [ -n "$model" ] || die "OLLAMA_MODEL tidak ditemukan di config.py."
    ollama_pull "$model"
}

install_vision_model() {
    step "Model visi (membaca layar)"
    local model
    model="$(config_value VISION_MODEL)"
    [ -n "$model" ] || die "VISION_MODEL tidak ditemukan di config.py."
    ollama_pull "$model"
}

show_rvc_status() {
    step "Suara Miku (RVC, opsional)"
    if ! rvc_model_present; then
        log INFO "Model RVC tidak di-bundle. Tanpa RVC, Miku memakai suara MeloTTS Jepang. Letakkan model sendiri (lihat README bagian 'Suara Miku (RVC)') lalu jalankan installer lagi."
    elif [ "$RVC_INSTALLED" -eq 1 ]; then
        log OK "Model RVC ditemukan dan rvc-python terpasang."
    else
        log WARN "Model RVC ditemukan tapi rvc-python tidak terpasang; Miku memakai suara MeloTTS."
    fi
}

create_launcher() {
    step "Peluncur di menu aplikasi"
    local icon="$TOOLS_DIR/mikuvision.png"
    mkdir -p "$TOOLS_DIR"
    if ! (cd "$ROOT" && run --quiet "$VENV_PY" -c '
import sys
from PIL import Image
import config
sheet = Image.open(config.MIKU_SPRITE_SHEET).convert("RGBA")
frame = sheet.crop((0, 0, config.MIKU_FRAME_W, config.MIKU_FRAME_H))
side = max(frame.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(frame, ((side - frame.width) // 2, (side - frame.height) // 2))
square.resize((256, 256), Image.LANCZOS).save(sys.argv[1])
' "$icon"); then
        log WARN "Ikon gagal dibuat, peluncur memakai ikon bawaan."
        icon="utilities-terminal"
    fi

    local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    local entry="$apps/mikuvision.desktop"
    mkdir -p "$apps"
    # run.sh mencatat output ke data/logs/gui.log bila dibuka tanpa terminal
    cat >"$entry" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=$APP_NAME - asisten desktop Hatsune Miku
Exec=/bin/bash "$ROOT/run.sh"
Path=$ROOT
Icon=$icon
Terminal=false
Categories=Utility;
EOF
    chmod +x "$entry"
    command -v update-desktop-database >/dev/null && update-desktop-database "$apps" >/dev/null 2>&1
    log OK "Menu aplikasi: $entry"

    if [ "$SKIP_SHORTCUT" -eq 1 ]; then
        log INFO "--skip-shortcut: peluncur Desktop dilewati."
        return
    fi
    local desktop
    desktop="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
    if [ -d "$desktop" ] && [ "$desktop" != "$HOME" ]; then
        cp -f "$entry" "$desktop/$APP_NAME.desktop"
        chmod +x "$desktop/$APP_NAME.desktop"
        # Nemo/Nautilus hanya menjalankan peluncur di Desktop yang ditandai tepercaya
        gio set "$desktop/$APP_NAME.desktop" metadata::trusted true 2>/dev/null
        log OK "Desktop: $desktop/$APP_NAME.desktop"
    fi
}

run_self_test() {
    step "Verifikasi: miku.py --test"
    log INFO "Jalankan pertama kali mengunduh Whisper large-v3-turbo (sekitar 1,6 GB) bila belum ada di cache Hugging Face."
    log INFO "Cache Hugging Face: ${HF_HOME:-$HOME/.cache/huggingface} (atur HF_HOME untuk memindahkannya)"
    local out
    out="$(mktemp)"
    (cd "$ROOT" && "$VENV_PY" miku.py --test) 2>&1 | tee "$out" | sed -u 's/^/    /' | tee -a "$LOG_FILE"
    local code=${PIPESTATUS[0]}
    if [ "$code" -ne 0 ] || ! grep -qF "Test mode - Initialization successful" "$out"; then
        rm -f "$out"
        die "miku.py --test gagal (exit $code). Lihat log."
    fi
    log OK "miku.py --test lulus"
    if [ "$RVC_INSTALLED" -eq 1 ] && ! grep -qF "RVC ready" "$out"; then
        log WARN "rvc-python terpasang tapi RVC gagal dimuat; cari '[VoiceConverter]' di log. Miku memakai suara MeloTTS."
    fi
    rm -f "$out"
}

# ---------------------------------------------------------------- main
main() {
    mkdir -p "$LOG_DIR"
    : >"$LOG_FILE"
    trap on_exit EXIT
    trap on_signal INT TERM
    log INFO "$APP_NAME installer - log: $LOG_FILE"

    if [ "$SELF_CHECK" -eq 1 ]; then
        # Jalur yang sama dengan instalasi (step, log WARN, akhir main), tanpa memasang apa pun.
        # Judul berisi huruf Jepang supaya test ikut memeriksa UTF-8.
        STEP_TOTAL=1
        step "Self-check ミク"
        log WARN "Peringatan contoh"
        FINISHED=1
        emit '{"event":"done","ok":true}'
        exit 0
    fi

    load_model_env
    local steps=() name
    read -r -a steps <<<"$(install_steps)"
    STEP_TOTAL=${#steps[@]}
    [ "$SKIP_OLLAMA" -eq 1 ] && log WARN "--skip-ollama: Ollama dilewati."
    { [ "$SKIP_SHORTCUT" -eq 1 ] && [ "$MENU_ENTRY" -eq 0 ]; } && log INFO "--skip-shortcut: peluncur dilewati."
    { [ "$SKIP_TEST" -eq 1 ] || [ "$SKIP_OLLAMA" -eq 1 ]; } && log WARN "Verifikasi miku.py --test dilewati."

    for name in "${steps[@]}"; do
        "$name"
    done

    log INFO ""
    log OK "Instalasi selesai. Buka '$APP_NAME' dari menu aplikasi, atau jalankan: ./run.sh"
    FINISHED=1
    emit '{"event":"done","ok":true}'
    exit 0
}

# Bisa di-source (test memakai pkg_manager/pkg_names) tanpa menjalankan instalasi
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main
fi
