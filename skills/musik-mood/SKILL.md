---
name: musik mood
description: Memutar musik YouTube sesuai suasana hati user dan mengatur volume
triggers: [musik buat, lagu buat, musik santai, musik semangat, lagu sedih, mood music, 作業用bgm, bgm, リラックスできる曲, 元気が出る曲]
tools: [youtube_search, set_volume]
---
1. Jangan bertanya dulu. Tentukan suasana dari ucapan user dan langsung pilih dari daftar ini:
   - belajar/kerja/fokus: query "lofi hip hop study music", volume 30
   - santai/tidur: query "relaxing piano music", volume 25
   - semangat/olahraga: query "upbeat energetic music mix", volume 60
   - sedih/galau: query "calm acoustic songs", volume 35
   - lainnya: susun query YouTube singkat dari ucapan user, volume 40
2. Bila user menyebut genre, penyanyi, atau angka volume sendiri, pakai itu.
3. Panggil set_volume dulu, lalu youtube_search dalam giliran yang sama.
