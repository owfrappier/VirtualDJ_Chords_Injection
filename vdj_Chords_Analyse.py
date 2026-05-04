#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import html
import unicodedata
from pathlib import Path
import xml.etree.ElementTree as ET

# ============================================================
# VDJ CHORD INJECTOR V13 BEATGRID SAFE - PYTHON ENGINE
# - V12 chord engine
# - V13 uses VirtualDJ BeatGrid when available
# - Supports fixed BPM/Phase and fluid BeatGrid formats
# - NO Song deletion
# - NO duplicate cleanup / merge
# - patches only ONE full existing Song block
# ============================================================

DB_PATH = Path(sys.argv[1])
AUDIO_FOLDER = Path(sys.argv[2])
CACHE_PATH = Path(sys.argv[3])
COLOR = sys.argv[4]
SEARCH_WORD = sys.argv[5].lower().strip() if len(sys.argv) > 5 else ''
REANALYSE = sys.argv[6] == '1' if len(sys.argv) > 6 else False
FIRST_LETTER = sys.argv[7].lower().strip() if len(sys.argv) > 7 else ''

AUDIO_EXTS = ['.wav','.flac','.aif','.aiff','.mp3','.aac','.m4a','.alac','.webm','.mkv','.mov','.mp4']


q = chr(34)
NL = chr(10)


def auto_max_workers():
    try:
        import os
        env = os.environ.get('VDJ_MAX_WORKERS', '').strip()
        if env:
            return max(1, int(env))
        cpu = os.cpu_count() or 4
        return max(1, min(8, cpu))
    except Exception:
        return 6


def auto_write_every():
    try:
        import os
        env = os.environ.get('VDJ_WRITE_EVERY', '').strip()
        if env:
            return max(1, int(env))
        return 20
    except Exception:
        return 20


MAX_WORKERS = auto_max_workers()
WRITE_EVERY = auto_write_every()


def norm_key(p):
    s = Path(str(p)).stem.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split())


def get_xml_attr(block, attr):
    key = attr + '=' + q
    p = block.find(key)
    if p == -1:
        return ''
    p += len(key)
    e = block.find(q, p)
    if e == -1:
        return ''
    return html.unescape(block[p:e])


def get_pos(line):
    key = 'Pos=' + q
    p = line.find(key)
    if p == -1:
        return 999999999.0
    p += len(key)
    e = line.find(q, p)
    if e == -1:
        return 999999999.0
    try:
        return float(line[p:e])
    except Exception:
        return 999999999.0


def detect_indent(block):
    for line in block.splitlines():
        if '<Poi ' in line:
            return line[:len(line) - len(line.lstrip())]
    for line in block.splitlines():
        if '<Scan ' in line:
            return line[:len(line) - len(line.lstrip())]
    return '  '


def song_ref(block):
    for attr in ['FilePath','File','Path']:
        v = get_xml_attr(block, attr)
        if v:
            return v
    return ''


def is_full_song_block(block):
    return '<Scan ' in block


def iter_song_blocks(text):
    pos = 0
    while True:
        s = text.find('<Song ', pos)
        if s == -1:
            break
        e = text.find('</Song>', s)
        if e == -1:
            break
        e2 = e + len('</Song>')
        yield s, e2, text[s:e2]
        pos = e2


def build_song_index(text):
    index = {}
    total_blocks = 0
    patchable_blocks = 0
    for start, end, block in iter_song_blocks(text):
        total_blocks += 1
        ref = song_ref(block)
        if not ref or not is_full_song_block(block):
            continue
        patchable_blocks += 1
        key = norm_key(Path(ref).name)
        index.setdefault(key, []).append((start, end, block))
    return index, total_blocks, patchable_blocks


def chord_regex():
    import re
    root = r'(?:C#|Db|D#|Eb|F#|Gb|G#|Ab|A#|Bb|C|D|E|F|G|A|B)'
    suffix = r'(?:maj11|maj9|maj7|madd9|m11|m9|m7|m6|dim7|dim|aug|7sus4|sus2|sus4|add9|11|9|7|6|m)?'
    bass = r'(?:/' + root + r')?'
    return re.compile(r'^' + root + suffix + bass + r'$')


def is_chord_name(name):
    name = html.unescape(str(name)).strip()
    if not name:
        return False
    if name.startswith('pitch') or '%' in name or name == 'AutoPitch':
        return False
    return chord_regex().match(name) is not None


def has_existing_chords(block):
    for line in block.splitlines():
        if '<Poi ' not in line:
            continue
        name = get_xml_attr(line, 'Name')
        if is_chord_name(name):
            return True
    return False


def remove_old_chord_pois(lines):
    clean = []
    for line in lines:
        if '<Poi ' in line:
            name = get_xml_attr(line, 'Name')
            typ = get_xml_attr(line, 'Type')
            action = get_xml_attr(line, 'Action')
            color = get_xml_attr(line, 'Color')

            if is_chord_name(name):
                continue
            if typ == 'action' and ('pitch_zero' in action or name.startswith('pitch') or '%' in name or name == 'AutoPitch'):
                continue
            if typ == 'action' and color == COLOR:
                continue

        clean.append(line)
    return clean


def make_poi(name, pos, indent):
    pos = format(float(pos), '.3f')
    if str(name).startswith('pitch_zero'):
        action_raw = str(name)
        display_name = action_raw.split(' & pitch ')[-1]
        action = html.escape(action_raw, quote=True)
        display_name = html.escape(display_name, quote=True)
        return indent + '<Poi Name=' + q + display_name + q + ' Pos=' + q + pos + q + ' Num=' + q + '-1' + q + ' Color=' + q + COLOR + q + ' Type=' + q + 'action' + q + ' Action=' + q + action + q + ' />' + NL
    name = html.escape(str(name), quote=True)
    return indent + '<Poi Name=' + q + name + q + ' Pos=' + q + pos + q + ' Num=' + q + '-1' + q + ' Color=' + q + COLOR + q + ' Type=' + q + 'action' + q + ' />' + NL


# ============================================================
# VirtualDJ BeatGrid helpers
# ============================================================

def extract_vdj_beat_info(block):
    try:
        if not block:
            return None
        scan_line = ''
        for line in block.splitlines():
            if '<Scan ' in line:
                scan_line = line
                break
        song_length = get_xml_attr(block, 'SongLength')
        song_length = float(song_length) if song_length else 0.0
        beatgrid = get_xml_attr(scan_line, 'BeatGrid')
        if beatgrid:
            return {'mode': 'fluid', 'beatgrid': beatgrid, 'song_length': song_length}
        bpm_step = get_xml_attr(scan_line, 'Bpm')
        phase = get_xml_attr(scan_line, 'Phase')
        if bpm_step and phase:
            return {'mode': 'fixed', 'bpm_step': float(bpm_step), 'phase': float(phase), 'song_length': song_length}
    except Exception:
        pass
    return None


def parse_vdj_fluid_beatgrid(beatgrid):
    import re
    tokens = []
    for m in re.finditer(r'\[([0-9.]+):([0-9]+)(?:,([0-9.]+))?(?:,([^\]]+))?\]', str(beatgrid)):
        try:
            start = float(m.group(1))
            count = int(m.group(2))
            step = float(m.group(3)) if m.group(3) else None
            tokens.append((start, count, step))
        except Exception:
            continue
    beats = []
    last_step = None
    for idx, (start, count, step) in enumerate(tokens):
        if count <= 0:
            continue
        if step is None:
            if idx + 1 < len(tokens):
                next_start = tokens[idx + 1][0]
                inferred = (next_start - start) / float(count)
                if inferred > 0.05:
                    step = inferred
            if step is None:
                step = last_step
        if step is None or step <= 0:
            continue
        for i in range(count):
            beats.append(start + (i * step))
        last_step = step
    return sorted(set(round(b, 6) for b in beats if b >= 0))


def build_fixed_vdj_beats(bpm_step, phase, song_length):
    beats = []
    try:
        step = float(bpm_step)
        phase = float(phase)
        song_length = float(song_length) if song_length else 0.0
        if step <= 0:
            return beats
        t = phase
        while t > 0:
            t -= step
        end = song_length if song_length > 0 else phase + 3600.0
        while t <= end + step:
            if t >= 0:
                beats.append(round(t, 6))
            t += step
    except Exception:
        pass
    return beats


def build_vdj_beats(beat_info):
    if not beat_info:
        return []
    try:
        if beat_info.get('mode') == 'fluid':
            return parse_vdj_fluid_beatgrid(beat_info.get('beatgrid', ''))
        if beat_info.get('mode') == 'fixed':
            return build_fixed_vdj_beats(beat_info.get('bpm_step'), beat_info.get('phase'), beat_info.get('song_length', 0.0))
    except Exception:
        return []
    return []


def best_song_block_for_audio(song_index, audio):
    key = norm_key(Path(audio).name)
    matches = song_index.get(key, [])
    if not matches:
        return None
    matches = sorted(matches, key=lambda item: song_block_score(item[2]), reverse=True)
    return matches[0][2]


def detect_fine_pitch_cents(y, sr):
    try:
        import numpy as np
        import librosa
        if y is None or len(y) < 2048:
            return 0.0
        if float(np.mean(np.abs(y))) < 1e-5:
            return 0.0
        bins_per_oct = 48
        hop = 2048
        bpc = bins_per_oct / 1200.0
        Q = {'M': [0, 16, 28], 'm': [0, 12, 28], '7': [0, 16, 28, 40], 'm7': [0, 12, 28, 40]}
        step = bins_per_oct // 12
        T = []
        for offs in Q.values():
            for r in range(12):
                v = np.zeros(bins_per_oct)
                root = int(r * step)
                for o in offs:
                    v[(root + o) % bins_per_oct] += 1.0
                T.append(v / (np.linalg.norm(v) + 1e-12))

        def circ_shift_frac(X, s_bins):
            k = int(np.floor(s_bins))
            frac = s_bins - k
            Xk = np.roll(X, k, axis=0)
            if frac == 0:
                return Xk
            Xk1 = np.roll(Xk, 1, axis=0)
            return (1 - frac) * Xk + frac * Xk1

        def estimate_segment(yseg):
            if yseg is None or len(yseg) < sr * 8:
                return None
            if float(np.mean(np.abs(yseg))) < 1e-5:
                return None
            try:
                import scipy.signal as signal
                low = 150 / (sr / 2)
                high = 3000 / (sr / 2)
                b, a = signal.butter(4, [low, high], btype='band')
                yseg = signal.filtfilt(b, a, yseg)
                yseg = librosa.effects.harmonic(yseg)
            except Exception:
                pass
            chroma = librosa.feature.chroma_cqt(y=yseg, sr=sr, tuning=0.0, bins_per_octave=bins_per_oct, n_chroma=bins_per_oct, hop_length=hop, cqt_mode='full')
            if chroma is None or chroma.size == 0:
                return None
            eng = chroma.sum(axis=0)
            thr = np.percentile(eng, 25.0)
            keep = eng > thr
            C = chroma[:, keep] if np.count_nonzero(keep) >= 10 else chroma

            def score(Cin):
                Cn = Cin / (np.linalg.norm(Cin, axis=0, keepdims=True) + 1e-12)
                return max(float(np.sum(Cn * t[:, None])) for t in T)

            scores_scan = []
            for c in np.arange(-50, 50.5, 0.5):
                s = score(circ_shift_frac(C, c * bpc))
                scores_scan.append((s, c))
            scores_scan.sort(reverse=True)
            best_s, best_c = scores_scan[0]
            second_s = -1.0
            for s, c in scores_scan[1:]:
                if abs(c - best_c) >= 8.0:
                    second_s = s
                    break
            confidence = best_s - second_s
            if confidence < 0.020:
                return None
            if abs(best_c) > 50:
                return None
            fine = np.arange(best_c - 6, best_c + 6.1, 0.1)
            svals = [score(circ_shift_frac(C, c * bpc)) for c in fine]
            i = int(np.argmax(svals))
            c_best = fine[i]
            if 0 < i < len(fine) - 1:
                x1, x2, x3 = fine[i - 1], fine[i], fine[i + 1]
                y1, y2, y3 = svals[i - 1], svals[i], svals[i + 1]
                denom = (x1 - x2) * (x1 - x3) * (x2 - x3)
                if abs(denom) > 1e-12:
                    A = (x3 * (y2 - y1) + x2 * (y1 - y3) + x1 * (y3 - y2)) / denom
                    B = (x3**2 * (y1 - y2) + x2**2 * (y3 - y1) + x1**2 * (y2 - y3)) / denom
                    if A != 0:
                        c_peak = -B / (2 * A)
                        if abs(c_peak - c_best) <= 1:
                            c_best = c_peak
            return float(c_best), float(confidence)

        seg_sec = 30.0
        step_sec = 15.0
        seg_len = int(seg_sec * sr)
        step_len = int(step_sec * sr)
        estimates = []
        if len(y) <= seg_len:
            r = estimate_segment(y)
            if r:
                estimates.append(r)
        else:
            for start in range(0, max(1, len(y) - seg_len), step_len):
                yseg = y[start:start + seg_len]
                r = estimate_segment(yseg)
                if r:
                    estimates.append(r)
        if len(estimates) < 2:
            r = estimate_segment(y)
            return 0.0 if r is None else float(r[0])
        cents_vals = np.array([x[0] for x in estimates], dtype=float)
        conf_vals = np.array([x[1] for x in estimates], dtype=float)
        median_cents = float(np.median(cents_vals))
        mad = float(np.median(np.abs(cents_vals - median_cents)))
        if mad > 6.0:
            return 0.0
        good = np.abs(cents_vals - median_cents) <= 6.0
        if np.count_nonzero(good) < 2:
            return 0.0
        return float(np.average(cents_vals[good], weights=conf_vals[good]))
    except Exception:
        return 0.0


def analyze_wrapper(job):
    try:
        audio, beat_info = job
        return (str(audio), analyze_chords(audio, beat_info), None)
    except Exception as e:
        try:
            return (str(job[0]), [], str(e))
        except Exception:
            return ('', [], str(e))

def load_audio_mono(audio_path, sr_target):
    import numpy as np

    ext = audio_path.suffix.lower()

    # 🚀 FORCER librosa pour formats compressés
    if ext in ['.mp3', '.m4a', '.aac', '.mp4', '.mov', '.webm', '.mkv']:
        import librosa
        return librosa.load(str(audio_path), sr=sr_target, mono=True)

    # ⚡ Fast path pour formats lossless
    try:
        import soundfile as sf
        import librosa

        y, sr = sf.read(str(audio_path), always_2d=False)

        if getattr(y, 'ndim', 1) > 1:
            y = np.mean(y, axis=1)

        if sr != sr_target:
            y = librosa.resample(y.astype(float), orig_sr=sr, target_sr=sr_target)
            sr = sr_target

        return y.astype(float), sr

    except Exception:
        # 🔁 fallback sécurité
        import librosa
        return librosa.load(str(audio_path), sr=sr_target, mono=True)



def analyze_chords(audio_path, beat_info=None):
    try:
        import numpy as np
        import librosa
    except Exception as e:
        print('IMPORT_FAIL', e)
        return []

    SR_TARGET = 22050
    HOP = 2048
    AUTO_PITCH_POI_POS = 0.010
    VDJ_PITCH_FACTOR = 0.05946
    VDJ_PITCH_ACTION_PREFIX = 'pitch_zero & wait 10ms & pitch '
    PREFER_FLATS = True
    NOTE_NAMES_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    NOTE_NAMES_FLAT  = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']
    CHROMA_FMIN = 'C2'
    BASS_FMIN = 'C1'
    BINS_PER_OCTAVE = 24
    QUICK_SMOOTH_FRAMES = 3
    SLOW_SMOOTH_FRAMES = 9
    BASS_SMOOTH_FRAMES = 5
    QUICK_WEIGHT = 0.42
    SLOW_WEIGHT = 0.58
    MIN_ENERGY = 0.25
    MIN_BEST_SCORE = 0.55
    MIN_AVG_SCORE = 0.55
    MIN_SEGMENT_SEC = 0.25
    CONFIDENCE_GAP_MIN = 0.018
    MAJORITY_FILTER_WIN = 3
    MIN_CHANGE_GAP = 0.12
    PASSING_CHORD_MIN_SCORE = 0.64
    EARLY_CHORD_LIMIT_SEC = 1.2
    EARLY_CHORD_ADVANCE_SEC = 0.16
    NORMAL_CHORD_ADVANCE_SEC = 0.35
    BEAT_SNAP_TOLERANCE_SEC = 0.22
    BASS_MIN_STRENGTH = 0.54
    BASS_ROOT_RATIO = 1.05
    BASS_ISOLATION_RATIO = 1.35
    ROOT_BONUS = 0.34
    FIFTH_BONUS = 0.15
    THIRD_BONUS = 0.32
    MINOR_BIAS = 0.005
    OUTSIDE_NOTE_PENALTY = 0.060
    TONALITY_ROOT_BONUS = 0.020
    MAJ7_REQUIRED_RATIO = 0.85
    DOM7_REQUIRED_RATIO = 0.58
    M7_REQUIRED_RATIO = 0.54
    MAJ7_TRIAD_MARGIN = 0.075
    MICRO_MAJ7_SEC = 0.35
    THIRD_MIN_RATIO = 0.42
    DIM_REQUIRED_RATIO = 0.36
    AUG_REQUIRED_RATIO = 0.36
    DIM_AUG_BOOST = 0.085

    def note_name(pc):
        return NOTE_NAMES_FLAT[pc] if PREFER_FLATS else NOTE_NAMES_SHARP[pc]

    def snap_to_beat(t):
        if not beat_times:
            return t
        nearest = min(beat_times, key=lambda b: abs(b - t))
        if abs(nearest - t) <= BEAT_SNAP_TOLERANCE_SEC:
            return float(nearest)
        return t

    def accept_segment(start_t, dur, avg_score):
        return dur >= MIN_SEGMENT_SEC and avg_score >= MIN_AVG_SCORE

    def place_chord_time(start_t):
        if start_t < EARLY_CHORD_LIMIT_SEC:
            return round(max(0.0, start_t - EARLY_CHORD_ADVANCE_SEC), 3)
        return round(max(0.0, snap_to_beat(start_t - NORMAL_CHORD_ADVANCE_SEC)), 3)

    try:
        y, sr = load_audio_mono(audio_path, SR_TARGET)
    except Exception as e:
        print('LOAD_FAIL', audio_path, e)
        return []
    if y is None or len(y) < sr:
        return []
    cents = -detect_fine_pitch_cents(y, sr)
    print('FINE_PITCH_CENTS', format(cents, '+.2f'), audio_path)
    try:
        if abs(cents) > 0.5:
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=-(cents / 100.0))
    except Exception:
        pass
    try:
        y_harm, _ = librosa.effects.hpss(y)
    except Exception:
        y_harm = y

    beat_times = build_vdj_beats(beat_info)
    if beat_times:
        try:
            print('VDJ_BEATGRID_USED', beat_info.get('mode'), len(beat_times), audio_path)
        except Exception:
            pass
    else:
        try:
            tempo, beat_frames = librosa.beat.beat_track(y=y_harm, sr=sr, hop_length=HOP)
            beat_times = list(librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP))
        except Exception:
            beat_times = []

    try:
        chroma_fast = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=HOP, bins_per_octave=BINS_PER_OCTAVE, n_chroma=12, fmin=librosa.note_to_hz(CHROMA_FMIN))
        bass_chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=HOP, bins_per_octave=BINS_PER_OCTAVE, n_chroma=12, fmin=librosa.note_to_hz(BASS_FMIN))
    except Exception as e:
        print('CHROMA_FAIL', audio_path, e)
        vdj_pitch = -cents * VDJ_PITCH_FACTOR
        pitch_action = VDJ_PITCH_ACTION_PREFIX + format(vdj_pitch, '+.2f') + '%'
        return [(AUTO_PITCH_POI_POS, pitch_action, 1.0)]

    chroma_fast = np.maximum(chroma_fast, 0)
    chroma_fast = chroma_fast / (np.max(chroma_fast, axis=0, keepdims=True) + 1e-9)
    bass_chroma = np.maximum(bass_chroma, 0)
    bass_chroma = bass_chroma / (np.max(bass_chroma, axis=0, keepdims=True) + 1e-9)
    kernel_quick = np.ones(QUICK_SMOOTH_FRAMES) / QUICK_SMOOTH_FRAMES
    kernel_slow = np.ones(SLOW_SMOOTH_FRAMES) / SLOW_SMOOTH_FRAMES
    kernel_bass = np.ones(BASS_SMOOTH_FRAMES) / BASS_SMOOTH_FRAMES
    chroma_quick = np.vstack([np.convolve(chroma_fast[i], kernel_quick, mode='same') for i in range(12)])
    chroma_slow = np.vstack([np.convolve(chroma_fast[i], kernel_slow, mode='same') for i in range(12)])
    bass_smooth = np.vstack([np.convolve(bass_chroma[i], kernel_bass, mode='same') for i in range(12)])
    times = librosa.frames_to_time(np.arange(chroma_fast.shape[1]), sr=sr, hop_length=HOP)
    chord_templates = [('',[0,4,7],1.00),('m',[0,3,7],1.00),('5',[0,7],0.72),('7',[0,4,7,10],0.94),('m7',[0,3,7,10],0.94),('maj7',[0,4,7,11],0.80),('6',[0,4,7,9],0.88),('m6',[0,3,7,9],0.88),('sus2',[0,2,7],0.86),('sus4',[0,5,7],0.86),('7sus4',[0,5,7,10],0.84),('dim',[0,3,6],0.84),('dim7',[0,3,6,9],0.82),('aug',[0,4,8],0.82)]
    global_chroma = np.mean(chroma_slow, axis=1)
    likely_roots = list(np.argsort(global_chroma)[-7:])
    labels = []
    scores = []
    for i in range(chroma_slow.shape[1]):
        vec = (SLOW_WEIGHT * chroma_slow[:, i]) + (QUICK_WEIGHT * chroma_quick[:, i])
        bass_vec = bass_smooth[:, i]
        energy = float(np.sum(vec))
        if energy < MIN_ENERGY:
            labels.append(None); scores.append(0.0); continue
        candidates = []
        for root in range(12):
            for suffix, intervals, weight in chord_templates:
                root_e = float(vec[root]); maj3_e = float(vec[(root+4)%12]); min3_e = float(vec[(root+3)%12]); fifth_e = float(vec[(root+7)%12]); dim5_e = float(vec[(root+6)%12]); aug5_e = float(vec[(root+8)%12]); dom7_e = float(vec[(root+10)%12]); maj7_e = float(vec[(root+11)%12])
                if suffix == '' and maj3_e < root_e * THIRD_MIN_RATIO: continue
                if suffix == 'm' and min3_e < root_e * THIRD_MIN_RATIO: continue
                if suffix == 'maj7':
                    if maj3_e < root_e * THIRD_MIN_RATIO: continue
                    if maj7_e < max(root_e, maj3_e) * MAJ7_REQUIRED_RATIO: continue
                    if maj7_e > root_e * 1.15: continue
                if suffix == '7':
                    if maj3_e < root_e * THIRD_MIN_RATIO: continue
                    if dom7_e < max(root_e, maj3_e) * DOM7_REQUIRED_RATIO: continue
                if suffix == 'm7':
                    if min3_e < root_e * THIRD_MIN_RATIO: continue
                    if dom7_e < max(root_e, min3_e) * M7_REQUIRED_RATIO: continue
                if suffix == '6' and maj3_e < root_e * THIRD_MIN_RATIO: continue
                if suffix == 'm6' and min3_e < root_e * THIRD_MIN_RATIO: continue
                
                if suffix == 'dim':
                    if min3_e < root_e * 0.32:
                        continue
                    if dim5_e < max(root_e, min3_e) * 0.32:
                        continue
                    if fifth_e > dim5_e * 1.15:
                        continue

                if suffix == 'dim7':
                    dim7_e = float(vec[(root + 9) % 12])
                    if min3_e < root_e * 0.32:
                        continue
                    if dim5_e < max(root_e, min3_e) * 0.32:
                        continue
                    if dim7_e < max(root_e, min3_e) * 0.30:
                        continue
                    if fifth_e > dim5_e * 1.15:
                        continue
      
                if suffix == 'aug':
                    if maj3_e < root_e * THIRD_MIN_RATIO: continue
                    if aug5_e < max(root_e, maj3_e) * AUG_REQUIRED_RATIO: continue
                    if fifth_e > aug5_e * 1.15: continue
                tmpl = np.zeros(12)
                for interval in intervals: tmpl[(root + interval) % 12] = 1.0
                tmpl[root] += ROOT_BONUS; tmpl[(root+7)%12] += FIFTH_BONUS
                if suffix.startswith('m'): tmpl[(root+3)%12] += THIRD_BONUS
                elif suffix in ('','7','maj7','6','aug'): tmpl[(root+4)%12] += THIRD_BONUS
                tmpl = tmpl / (np.linalg.norm(tmpl) + 1e-9)
                score = float(np.dot(vec, tmpl)) * weight
                if suffix.startswith('m'): score += MINOR_BIAS
                
                # Si une quinte diminuée est plus forte que la quinte juste,
                # on évite que le mineur classique gagne à tort.
                if suffix == 'm' and dim5_e > fifth_e * 1.05:
                    score -= 0.10
                
                if suffix in ('dim', 'dim7'):
                # Boost spécifique diminués : évite qu'ils soient absorbés par m / inversions.
                    if min3_e > root_e * 0.32 and dim5_e > root_e * 0.32:
                        score += 0.12
                    else:
                        score += DIM_AUG_BOOST

                if suffix == 'aug':
                    score += DIM_AUG_BOOST
                
     
                chord_pcs = [(root+x)%12 for x in intervals]
                outside = sum(vec[pc] for pc in range(12) if pc not in chord_pcs)
                score -= outside * OUTSIDE_NOTE_PENALTY
                if root in likely_roots: score += TONALITY_ROOT_BONUS
                candidates.append((score, root, suffix, intervals))
        if not candidates:
            labels.append(None); scores.append(0.0); continue
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_root, best_suffix, best_intervals = candidates[0]
        if best_suffix == 'maj7':
            fallback = None
            for cand in candidates:
                s2, r2, suf2, inter2 = cand
                if r2 == best_root and suf2 in ('','m','5') and s2 >= best_score - MAJ7_TRIAD_MARGIN:
                    if fallback is None or s2 > fallback[0]: fallback = cand
            if fallback is not None:
                best_score, best_root, best_suffix, best_intervals = fallback
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        confidence_gap = best_score - second_score
        if best_score < MIN_BEST_SCORE:
            labels.append(None); scores.append(best_score); continue
        display_suffix = '' if best_suffix == '5' else best_suffix
        best_name = note_name(best_root) + display_suffix
        if confidence_gap < CONFIDENCE_GAP_MIN and labels:
            prev = labels[-1]
            if prev is not None:
                labels.append(prev); scores.append(best_score); continue
        chord_pcs = [(best_root+x)%12 for x in best_intervals]
        bass_sorted = list(np.argsort(bass_vec)[::-1])
        bass_pc = int(bass_sorted[0])
        bass_strength = float(bass_vec[bass_pc])
        root_strength = float(bass_vec[best_root])
        inversion_allowed = best_suffix in ('','m')
        bass_support = sum(float(vec[pc]) for pc in chord_pcs if pc != bass_pc)
        bass_isolated = bass_strength > bass_support * BASS_ISOLATION_RATIO
        bass_is_valid = inversion_allowed and bass_pc != best_root and bass_pc in chord_pcs and bass_strength >= BASS_MIN_STRENGTH and bass_strength >= root_strength * BASS_ROOT_RATIO and not bass_isolated
        labels.append(best_name + '/' + note_name(bass_pc) if bass_is_valid else best_name)
        scores.append(best_score)

    def majority_filter(seq, win=3):
        out = []; half = win // 2
        for i in range(len(seq)):
            chunk = seq[max(0, i-half):min(len(seq), i+half+1)]
            vals = [x for x in chunk if x is not None]
            out.append(seq[i] if not vals else max(set(vals), key=vals.count))
        return out
    labels = majority_filter(labels, win=MAJORITY_FILTER_WIN)
    results = []
    current = None; start_i = None; seg_scores = []
    for i, label in enumerate(labels):
        if label != current:
            if current is not None and start_i is not None:
                start_t = float(times[start_i]); end_t = float(times[i-1]); dur = end_t - start_t; avg_score = float(np.mean(seg_scores)) if seg_scores else 0.0
                if accept_segment(start_t, dur, avg_score): results.append((place_chord_time(start_t), current, round(avg_score, 3)))
            current = label; start_i = i; seg_scores = []
        if label is not None: seg_scores.append(scores[i])
    if current is not None and start_i is not None:
        start_t = float(times[start_i]); end_t = float(times[-1]); dur = end_t - start_t; avg_score = float(np.mean(seg_scores)) if seg_scores else 0.0
        if accept_segment(start_t, dur, avg_score): results.append((place_chord_time(start_t), current, round(avg_score, 3)))
    cleaned = []
    def base_chord(name):
        if '/' in name: name = name.split('/')[0]
        for s in ['maj7','m7','dim7','7sus4','sus2','sus4','dim','aug','m6','6','7','m']:
            if name.endswith(s):
                name = name[:-len(s)]; break
        return name
    for t, name, score in results:
        if not cleaned:
            cleaned.append((t, name, score)); continue
        prev_t, prev_name, prev_score = cleaned[-1]
        if name == prev_name: continue
        if 'maj7' in name and (t - prev_t) < MICRO_MAJ7_SEC: continue
        if abs(prev_t - t) < 0.05:
            if score > prev_score: cleaned[-1] = (t, name, score)
            continue
        if t - prev_t < MIN_CHANGE_GAP:
            if base_chord(name) == base_chord(prev_name): continue
            if score < PASSING_CHORD_MIN_SCORE: continue
        cleaned.append((t, name, score))
    vdj_pitch = -cents * VDJ_PITCH_FACTOR
    pitch_action = VDJ_PITCH_ACTION_PREFIX + format(vdj_pitch, '+.2f') + '%'
    return [(AUTO_PITCH_POI_POS, pitch_action, 1.0)] + cleaned


def patch_song_block(block, chords):
    lines = block.splitlines(True)
    lines = remove_old_chord_pois(lines)
    if not chords:
        return ''.join(lines)
    indent = detect_indent(block)
    non_poi = []; poi_lines = []
    for line in lines:
        if '<Poi ' in line and '/>' in line:
            poi_lines.append(line if line.endswith(NL) else line + NL)
        else:
            non_poi.append(line)
    fade_end = None; real_start = None
    for line in poi_lines:
        if 'fadeEnd' in line:
            v = get_pos(line)
            if v < 999999: fade_end = v
        if 'realStart' in line:
            v = get_pos(line)
            if v < 999999: real_start = v
    filtered = []
    for item in chords:
        if len(item) == 3: pos, chord, score = item
        else: pos, chord = item; score = None
        if str(chord).startswith('pitch_zero'):
            pos = real_start + 0.05 if real_start is not None else 0.010
            filtered.append((pos, chord, score)); continue
        if fade_end is not None and pos >= fade_end: continue
        filtered.append((pos, chord, score))
    pitch_positions = [pos for pos, chord, score in filtered if str(chord).startswith('pitch_zero')]
    first_allowed_chord_pos = (max(pitch_positions) + 0.250) if pitch_positions else 0.250
    first_chord_done = False; new_filtered = []
    for pos, chord, score in filtered:
        if str(chord).startswith('pitch_zero'):
            new_filtered.append((pos, chord, score)); continue
        if not first_chord_done:
            pos = max(pos, first_allowed_chord_pos)
            first_chord_done = True
            new_filtered.append((pos, chord, score)); continue
        if pos < first_allowed_chord_pos: continue
        new_filtered.append((pos, chord, score))
    filtered = new_filtered
    for pos, chord, score in filtered:
        poi_lines.append(make_poi(chord, pos, indent))
    poi_lines.sort(key=get_pos)
    out = []; inserted = False
    for line in non_poi:
        if '</Song>' in line and not inserted:
            out.extend(poi_lines); inserted = True
        out.append(line)
    return ''.join(out)


def write_cache(rows):
    root = ET.Element('Data')
    root.set('Type', 'VDJChordCache')
    root.set('Version', 'V13-BEATGRID-SAFE')
    for r in rows:
        tr = ET.SubElement(root, 'Track')
        tr.set('File', r['file'])
        tr.set('Matched', '1' if r['matched'] else '0')
        if not r['matched']: tr.set('Warning', 'UNMATCHED_NOT_IN_VDJ_DATABASE')
        tr.set('Count', str(len(r['chords'])))
        if r.get('error'): tr.set('Error', r['error'])
        for item in r['chords']:
            if len(item) == 3: pos, chord, score = item
            else: pos, chord = item; score = None
            c = ET.SubElement(tr, 'Chord')
            c.set('Name', str(chord)); c.set('Pos', format(float(pos), '.3f'))
            if score is not None: c.set('Score', format(float(score), '.3f'))
    ET.indent(root, space='    ')
    ET.ElementTree(root).write(str(CACHE_PATH), encoding='utf-8', xml_declaration=True)


def count_action_pois(block):
    c = 0
    for line in block.splitlines():
        if '<Poi ' in line and 'Type=' in line and 'action' in line:
            c += 1
    return c


def count_chord_like_pois(block):
    c = 0
    for line in block.splitlines():
        if '<Poi ' not in line: continue
        if is_chord_name(get_xml_attr(line, 'Name')): c += 1
    return c


def song_block_score(block):
    score = 0
    score += count_chord_like_pois(block) * 1000
    score += count_action_pois(block) * 50
    if '<Scan ' in block: score += 100
    if '<Infos ' in block: score += 50
    if '<Tags ' in block: score += 25
    score += min(len(block) // 1000, 100)
    return score


def main():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    raw = DB_PATH.read_bytes()
    text = raw.decode('utf-8', errors='surrogateescape')
    new_text = text
    LOG_PATH = DB_PATH.parent / 'VDJ_CHORD_ANALYSIS.log'
    def log(msg):
        print(msg, flush=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            print(msg, file=f)
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        print('--- VDJ CHORD ANALYSIS V13 BEATGRID SAFE START ---', file=f)
    log('SAFE MODE: no Song cleanup, no Song deletion')
    log('V13 MODE: VirtualDJ BeatGrid aware chord placement')
    log(f'TURBO MODE: MAX_WORKERS={MAX_WORKERS}, WRITE_EVERY={WRITE_EVERY}')
    log('BUILD DATABASE INDEX...')
    song_index, total_blocks, patchable_blocks = build_song_index(text)
    log(f'DATABASE INDEX READY: {len(song_index)} keys / {patchable_blocks} patchable Song blocks / {total_blocks} total Song blocks')
    if AUDIO_FOLDER.is_file():
        audio_files = [AUDIO_FOLDER] if AUDIO_FOLDER.suffix.lower() in AUDIO_EXTS else []
    else:
        audio_files = []
        for p in AUDIO_FOLDER.rglob('*'):
            try:
                if p.is_file() and p.suffix.lower().strip() in AUDIO_EXTS:
                    audio_files.append(p)
            except Exception: pass
    audio_files.sort(key=lambda p: p.name.lower())
    if SEARCH_WORD: audio_files = [p for p in audio_files if SEARCH_WORD in p.name.lower()]
    if FIRST_LETTER: audio_files = [p for p in audio_files if p.name.lower().startswith(FIRST_LETTER)]
    if not audio_files: raise RuntimeError('NO_AUDIO_FILES')
    log(f'TOTAL FILES FOUND: {len(audio_files)}')
    if not REANALYSE:
        log('PRE-SCAN DATABASE FOR EXISTING CHORDS...')
        filtered_audio_files = []
        skipped_before = 0
        prescan_total = len(audio_files)
        for prescan_idx, audio in enumerate(audio_files, start=1):
            if prescan_idx == 1 or prescan_idx == prescan_total or prescan_idx % 100 == 0:
                log(f'PRESCAN {prescan_idx}/{prescan_total} : {audio.name}')
            key = norm_key(audio.name)
            matches = song_index.get(key, [])
            already_has_chords = False
            for _, _, block in sorted(matches, key=lambda item: song_block_score(item[2]), reverse=True):
                if has_existing_chords(block):
                    already_has_chords = True; break
            if already_has_chords: skipped_before += 1
            else: filtered_audio_files.append(audio)
        audio_files = filtered_audio_files
        log(f'SKIPPED BEFORE ANALYSIS: {skipped_before}')
        log(f'REMAINING TO ANALYZE: {len(audio_files)}')
        if not audio_files:
            log('NOTHING TO ANALYZE'); log('--- DONE ---'); return
    analysis_jobs = []
    vdj_beat_count = 0
    for audio in audio_files:
        block = best_song_block_for_audio(song_index, audio)
        beat_info = extract_vdj_beat_info(block) if block else None
        if beat_info: vdj_beat_count += 1
        analysis_jobs.append((audio, beat_info))
    log(f'VDJ BEAT INFO AVAILABLE: {vdj_beat_count}/{len(audio_files)}')
    total = len(audio_files); rows = []; patched_count = 0; pending_patches = 0; pending_reindex = False
    def flush_database(message):
        new_raw = new_text.encode('utf-8', errors='surrogateescape')
        tmp = Path(str(DB_PATH) + '.tmp-v13-safe')
        tmp.write_bytes(new_raw)
        if '</VirtualDJ_Database>' not in tmp.read_text(errors='ignore'):
            raise RuntimeError('VDJ_END_TAG_MISSING')
        DB_PATH.write_bytes(new_raw)
        log(message)
    def patch_one_track_in_db(current_text, current_index, audio_path, chords):
        key = norm_key(audio_path.name)
        matches = current_index.get(key, [])
        if not matches: return current_text, current_index, False, 'NOT_FOUND', False
        matches.sort(key=lambda item: song_block_score(item[2]), reverse=True)
        keep_start, keep_end, keep_block = matches[0]
        if not REANALYSE and has_existing_chords(keep_block):
            return current_text, current_index, False, 'SKIPPED', False
        new_block = patch_song_block(keep_block, chords)
        delta = len(new_block) - (keep_end - keep_start)
        updated_text = current_text[:keep_start] + new_block + current_text[keep_end:]
        updated_index = {}
        for k, items in current_index.items():
            new_items = []
            for s, e, b in items:
                if s == keep_start and e == keep_end:
                    new_items.append((keep_start, keep_start + len(new_block), new_block))
                elif s > keep_start:
                    new_items.append((s + delta, e + delta, b))
                else:
                    new_items.append((s, e, b))
            updated_index[k] = new_items
        return updated_text, updated_index, True, 'PATCHED', False
    try:
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(analyze_wrapper, job) for job in analysis_jobs]
            completed = 0
            for future in as_completed(futures):
                audio_path, chords, error = future.result()
                audio = Path(audio_path)
                completed += 1
                remaining = total - completed
                log(f'PROGRESS {completed}/{total} - remaining {remaining} : {audio.name}')
                row = dict(file=str(audio), matched=False, chords=chords, error=error or '')
                try:
                    new_text, song_index, patched, status, need_reindex = patch_one_track_in_db(new_text, song_index, audio, chords)
                    pending_reindex = pending_reindex or need_reindex
                    if status == 'SKIPPED':
                        log(f'SKIPPED {audio.name}')
                        rows.append(row); write_cache(rows); continue
                    if patched:
                        row['matched'] = True; patched_count += 1; pending_patches += 1
                        if pending_patches >= WRITE_EVERY:
                            flush_database(f'DATABASE UPDATED {completed}/{total} - batch flush')
                            pending_patches = 0
                            if pending_reindex:
                                song_index, _, _ = build_song_index(new_text); pending_reindex = False
                    else:
                        log(f'UNMATCHED {audio.name}')
                    log(f'OK {audio.name} -> {len(chords)} chords')
                except Exception as e:
                    row['error'] = str(e)
                    log(f'ERROR WRITE {audio.name} -> {e}')
                rows.append(row); write_cache(rows)
        if pending_patches > 0:
            flush_database('DATABASE UPDATED FINAL - remaining batch flush')
            pending_patches = 0
    except KeyboardInterrupt:
        log('--- STOPPED BY USER (Ctrl+C) ---')
        return
    log('--- ANALYSIS DONE ---')
    log(f'PATCHED SONGS: {patched_count}')
    log('--- DONE ---')


if __name__ == '__main__':
    main()
