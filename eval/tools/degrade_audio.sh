#!/bin/sh
# Controlled noisy-audio test set : degrade a clean recording the ways a meeting room does.
# Usage: sh eval/tools/degrade_audio.sh clean.wav outdir/   (needs ffmpeg)
set -e
IN=$1; OUT=${2:-.}; mkdir -p "$OUT"; F="ffmpeg -loglevel error -y -i $IN"
cp "$IN" "$OUT/tts-01-clean-synthetic.wav"
$F -filter_complex "anoisesrc=color=pink:amplitude=0.08:r=16000[n];[0][n]amix=inputs=2:duration=first:weights=1 1" "$OUT/tts-02-noise.wav"
$F -filter_complex "anoisesrc=color=brown:amplitude=0.25:r=16000[n];[0]volume=0.5[v];[v][n]amix=inputs=2:duration=first:weights=1 1" "$OUT/tts-03-loud-noise.wav"
$F -af "atempo=1.45" "$OUT/tts-04-fast.wav"
$F -af "volume=0.35,aecho=0.8:0.85:60|120:0.45|0.3,highpass=f=300,lowpass=f=3000" "$OUT/tts-05-far-end.wav"
$F -filter_complex "atempo=1.3,highpass=f=400,lowpass=f=2800[a];anoisesrc=color=pink:amplitude=0.12:r=16000[n];[a][n]amix=inputs=2:duration=first:weights=1 1" "$OUT/tts-06-fast-phone-noise.wav"
$F -filter_complex "anoisesrc=color=pink:amplitude=0.30:r=16000[n];[0]volume=0.6[v];[v][n]amix=inputs=2:duration=first:weights=1 1" "$OUT/tts-07-very-loud-noise.wav"
$F -filter_complex "atempo=1.7,highpass=f=500,lowpass=f=2400,volume=0.4[a];anoisesrc=color=brown:amplitude=0.3:r=16000[n];[a][n]amix=inputs=2:duration=first:weights=1 1" "$OUT/tts-08-worst.wav"
