/**
 * AI-STEAM Interactive Sheet Music Studio
 * Frontend Business Logic & Web Audio Playback Engine
 */

// ==================== GLOBAL APPLICATION STATE ====================
const state = {
  currentFile: null,
  fileHash: null,
  filename: "",
  isAutoMode: true,
  omrMode: "fast",
  activeJobId: null,
  pollInterval: null,

  // Editor Target & Tools
  targetPartIndex: 0, // 0: Right Hand (RH), 1: Left Hand (LH)
  isEditMode: false,
  isChordAddMode: false,
  currentDuration: 1.0, // Quarter note default
  isDotted: false,
  selectedNote: null, // { measureNumber, noteIndex, offset, pitch, duration, partIndex }
  zoomLevel: 1.0,

  // Audio Playback
  isPlaying: false,
  bpm: 100,
  volume: 0.85,
  useSoundfont: true,
  audioCtx: null,
  soundfontInstrument: null,
  playbackTimeouts: [],
  scoreNotesTimeline: [], // [{ timestamp, pitches: [], duration, measureNum, iteratorStep }]
  currentPlaybackIndex: 0,

  // OSMD
  osmd: null,
  currentXmlUrl: null
};

// ==================== DOM ELEMENTS CACHE ====================
const dom = {
  // Header controls
  themeToggle: document.getElementById("btn-theme-toggle"),
  themeIcon: document.getElementById("theme-icon"),
  autoToggle: document.getElementById("toggle-auto-pipeline"),
  autoBadge: document.getElementById("auto-mode-badge"),
  newScoreBtn: document.getElementById("btn-new-score"),
  clearCacheBtn: document.getElementById("btn-clear-cache"),
  userManualBtn: document.getElementById("btn-user-manual"),
  helpBtn: document.getElementById("btn-help-modal"),
  guideModal: document.getElementById("guide-modal"),
  closeGuideBtn: document.getElementById("btn-close-guide"),
  modalTabBtns: document.querySelectorAll(".modal-tab-btn"),
  guidePanels: document.querySelectorAll(".guide-panel"),

  // Pipeline Card 1
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  dropzonePrompt: document.getElementById("dropzone-prompt"),
  previewBox: document.getElementById("preview-box"),
  imgPreview: document.getElementById("img-preview"),
  clearPreviewBtn: document.getElementById("btn-clear-preview"),
  btnPreprocess: document.getElementById("btn-preprocess"),
  statusPreprocess: document.getElementById("status-preprocess"),

  // Pipeline Card 2
  omrModeRadios: document.querySelectorAll('input[name="omr_mode"]'),
  omrProgressBar: document.getElementById("omr-progress-bar"),
  omrProgressText: document.getElementById("omr-progress-text"),
  omrPercentText: document.getElementById("omr-percent-text"),
  omrLogs: document.getElementById("omr-logs"),
  btnExtract: document.getElementById("btn-extract"),
  btnCancelExtract: document.getElementById("btn-cancel-extract"),
  statusExtract: document.getElementById("status-extract"),
  omrRetryBox: document.getElementById("omr-retry-box"),
  retryErrorMsg: document.getElementById("retry-error-msg"),
  btnRetryExtract: document.getElementById("btn-retry-extract"),
  btnSwitchModeRetry: document.getElementById("btn-switch-mode-retry"),

  // Placeholder hero buttons
  heroUploadBtn: document.getElementById("btn-hero-upload"),
  heroNewScoreBtn: document.getElementById("btn-hero-new-score"),
  heroManualBtn: document.getElementById("btn-hero-manual"),

  // Pipeline Card 3
  valKey: document.getElementById("val-key"),
  valTime: document.getElementById("val-time"),
  valMeasures: document.getElementById("val-measures"),
  valNotes: document.getElementById("val-notes"),
  valParts: document.getElementById("val-parts"),
  btnDlXml: document.getElementById("btn-dl-xml"),
  btnDlMidi: document.getElementById("btn-dl-midi"),
  btnOptimize: document.getElementById("btn-optimize"),
  btnRender: document.getElementById("btn-render"),
  statusOptimize: document.getElementById("status-optimize"),

  // Editor Topbar & Playback
  btnPlayPause: document.getElementById("btn-play-pause"),
  playIcon: document.getElementById("play-icon"),
  playText: document.getElementById("play-text"),
  btnStop: document.getElementById("btn-stop"),
  sliderBpm: document.getElementById("slider-bpm"),
  inputBpm: document.getElementById("input-bpm"),
  sliderVolume: document.getElementById("slider-volume"),
  toggleSoundfont: document.getElementById("toggle-soundfont"),
  btnZoomIn: document.getElementById("btn-zoom-in"),
  btnZoomOut: document.getElementById("btn-zoom-out"),
  btnZoomReset: document.getElementById("btn-zoom-reset"),
  zoomLevelText: document.getElementById("zoom-level-text"),

  // Playback Download Toolbar Buttons
  btnDlWav: document.getElementById("btn-dl-wav"),
  btnDlMidiToolbar: document.getElementById("btn-dl-midi-toolbar"),
  btnDlXmlToolbar: document.getElementById("btn-dl-xml-toolbar"),

  // Staff Switcher & Edit Mode
  btnPartRh: document.getElementById("btn-part-rh"),
  btnPartLh: document.getElementById("btn-part-lh"),
  partIndicator: document.getElementById("current-part-indicator"),
  btnToggleEditMode: document.getElementById("btn-toggle-edit-mode"),
  editModeIcon: document.getElementById("edit-mode-icon"),
  editModeText: document.getElementById("edit-mode-text"),
  btnUndo: document.getElementById("btn-undo"),
  btnRedo: document.getElementById("btn-redo"),

  // Palette
  editorPalette: document.getElementById("editor-palette"),
  selectedNoteDisplay: document.getElementById("selected-note-display"),
  chordBadge: document.getElementById("chord-badge"),
  btnPitchUp: document.getElementById("btn-pitch-up"),
  btnPitchDown: document.getElementById("btn-pitch-down"),
  btnOctUp: document.getElementById("btn-oct-up"),
  btnOctDown: document.getElementById("btn-oct-down"),
  btnAccSharp: document.getElementById("btn-acc-sharp"),
  btnAccFlat: document.getElementById("btn-acc-flat"),
  btnAccNatural: document.getElementById("btn-acc-natural"),
  durationButtons: document.querySelectorAll(".duration-buttons button[data-duration]"),
  btnDotted: document.getElementById("btn-dotted"),
  btnMakeRest: document.getElementById("btn-make-rest"),
  btnDeleteNote: document.getElementById("btn-delete-note"),
  btnChordToggle: document.getElementById("btn-chord-toggle"),

  // Sheet & Piano
  sheetViewport: document.getElementById("sheet-viewport"),
  osmdContainer: document.getElementById("osmd-container"),
  sheetPlaceholder: document.getElementById("sheet-placeholder"),
  pianoKeyboard: document.getElementById("piano-keyboard")
};

// ==================== INITIALIZATION ====================
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initAutoModeToggle();
  initVirtualPiano();
  initAudioEngine();
  setupEventListeners();
  setupKeyboardShortcuts();
  tryRestoreFromLocalStorage();
});

// 브라우저 자동 재생 정책(Autoplay Policy) 해제를 위한 전역 제스처 언락 리스너
const unlockAudioOnGesture = () => {
  ensureAudioContext();
  window.removeEventListener("click", unlockAudioOnGesture);
  window.removeEventListener("keydown", unlockAudioOnGesture);
  window.removeEventListener("touchstart", unlockAudioOnGesture);
};
window.addEventListener("click", unlockAudioOnGesture);
window.addEventListener("keydown", unlockAudioOnGesture);
window.addEventListener("touchstart", unlockAudioOnGesture);

// ==================== THEME & UI HELPERS ====================
function initTheme() {
  const savedTheme = localStorage.getItem("ai_steam_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  dom.themeIcon.textContent = savedTheme === "dark" ? "🌙" : "☀️";

  dom.themeToggle.addEventListener("click", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem("ai_steam_theme", nextTheme);
    dom.themeIcon.textContent = nextTheme === "dark" ? "🌙" : "☀️";
  });
}

function initAutoModeToggle() {
  state.isAutoMode = dom.autoToggle.checked;
  dom.autoToggle.addEventListener("change", (e) => {
    state.isAutoMode = e.target.checked;
    dom.autoBadge.textContent = state.isAutoMode ? "ON (자동)" : "OFF (디버그)";
    dom.autoBadge.style.color = state.isAutoMode ? "var(--accent-cyan)" : "var(--text-dim)";
  });
}

function logToConsole(message, type = "info") {
  const entry = document.createElement("div");
  entry.className = `log-entry ${type}`;
  const timestamp = new Date().toLocaleTimeString();
  entry.textContent = `[${timestamp}] ${message}`;
  dom.omrLogs.appendChild(entry);
  dom.omrLogs.scrollTop = dom.omrLogs.scrollHeight;
}

// ==================== CLIENT STORAGE & CACHE MANAGEMENT ====================
function backupCurrentState() {
  if (!state.fileHash) return;
  try {
    const backupData = {
      fileHash: state.fileHash,
      filename: state.filename,
      currentXmlUrl: state.currentXmlUrl,
      targetPartIndex: state.targetPartIndex,
      savedAt: Date.now()
    };
    localStorage.setItem("ai_steam_last_meta", JSON.stringify(backupData));
  } catch (e) {
    console.warn("로컬스토리지 백업 실패:", e);
  }
}

async function tryRestoreFromLocalStorage() {
  let restored = false;
  try {
    const saved = localStorage.getItem("ai_steam_last_meta");
    if (saved) {
      const backupData = JSON.parse(saved);
      if (backupData && backupData.fileHash) {
        // 24시간 이내의 캐시인지 확인
        if (Date.now() - (backupData.savedAt || 0) <= 24 * 60 * 60 * 1000) {
          const checkUrl = `/api/cache/${backupData.fileHash}_opt.musicxml`;
          const checkRes = await fetch(checkUrl, { method: "HEAD" });
          if (checkRes.ok) {
            state.fileHash = backupData.fileHash;
            state.filename = backupData.filename || "복원된 악보";
            state.targetPartIndex = backupData.targetPartIndex || 0;
            state.currentXmlUrl = checkUrl;

            setStepStatus(dom.statusPreprocess, "ready", "복원됨");
            setStepStatus(dom.statusExtract, "ready", "복원됨");
            setStepStatus(dom.statusOptimize, "ready", "복원됨");

            updateDownloadLinks(state.fileHash);
            await renderOsmdScore(`${checkUrl}?t=${Date.now()}`);
            logToConsole("📦 이전 편집 세션 악보를 로컬 스토리지에서 자동 복원했습니다.", "system");
            restored = true;
          } else {
            localStorage.removeItem("ai_steam_last_meta");
          }
        } else {
          localStorage.removeItem("ai_steam_last_meta");
        }
      }
    }
  } catch (e) {
    console.log("이전 세션 복원 건너뜀:", e);
  }

  // 복원된 이전 세션이 없다면, 즉시 연주/체험 가능한 기본 데모 악보(베토벤 환희의 송가) 자동 로드
  if (!restored && !state.osmd) {
    await loadDefaultDemoScore();
  }
}

async function loadDefaultDemoScore() {
  if (state.osmd) return;
  try {
    logToConsole("🎼 기본 데모 악보(베토벤 환희의 송가)를 불러오는 중...", "system");
    const demoUrl = `/api/cache/demo.musicxml?t=${Date.now()}`;
    const res = await fetch(demoUrl);
    const targetUrl = res.ok ? demoUrl : `/static/default.musicxml?t=${Date.now()}`;

    state.fileHash = "demo";
    state.filename = "Beethoven_Demo.musicxml";
    state.targetPartIndex = 0;
    state.currentXmlUrl = targetUrl;

    setStepStatus(dom.statusPreprocess, "ready", "데모 준비됨");
    setStepStatus(dom.statusExtract, "ready", "데모 준비됨");
    setStepStatus(dom.statusOptimize, "ready", "데모 준비됨");

    dom.valKey.textContent = "C Major";
    dom.valTime.textContent = "4/4";
    dom.valMeasures.textContent = "4";
    dom.valNotes.textContent = "16";
    dom.valParts.textContent = "2 파트";

    updateDownloadLinks("demo");
    await renderOsmdScore(targetUrl);
    logToConsole("✨ 기본 데모 악보가 성공적으로 로드되었습니다! [▶ 재생] 버튼을 누르면 즉시 음악이 연주됩니다.", "system");
  } catch (e) {
    console.warn("기본 데모 로드 실패:", e);
  }
}

function updateDownloadLinks(fileHash) {
  const hash = fileHash || state.fileHash || "demo";
  const xmlUrl = `/api/cache/${hash}_opt.musicxml`;
  const midiUrl = `/api/cache/${hash}.mid`;

  if (dom.btnDlXml) {
    dom.btnDlXml.href = xmlUrl;
    dom.btnDlXml.classList.remove("disabled");
  }
  if (dom.btnDlMidi) {
    dom.btnDlMidi.href = midiUrl;
    dom.btnDlMidi.classList.remove("disabled");
  }
  if (dom.btnDlXmlToolbar) {
    dom.btnDlXmlToolbar.href = xmlUrl;
    dom.btnDlXmlToolbar.setAttribute("download", `${hash}.musicxml`);
  }
  if (dom.btnDlMidiToolbar) {
    dom.btnDlMidiToolbar.href = midiUrl;
    dom.btnDlMidiToolbar.setAttribute("download", `${hash}.mid`);
  }
}

async function executeClearCache() {
  if (!confirm("서버의 모든 임시 분석 캐시를 삭제하고 기본 상태로 초기화하시겠습니까?")) return;
  try {
    const res = await fetch("/api/cache", { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).detail || "캐시 삭제 실패");
    const data = await res.json();
    logToConsole("🗑️ 서버 캐시가 성공적으로 초기화되었습니다.", "system");
    localStorage.removeItem("ai_steam_last_meta");
    resetFileUpload();
    dom.sheetPlaceholder.classList.remove("hidden");
    dom.osmdContainer.innerHTML = "";
    state.fileHash = null;
    state.osmd = null;
    alert("캐시가 초기화되었습니다. 새 악보를 생성하거나 새 악보 이미지를 업로드해 주세요.");
  } catch (err) {
    logToConsole(`캐시 삭제 오류: ${err.message}`, "error");
    alert(`캐시 삭제 실패: ${err.message}`);
  }
}

// ==================== 61-KEY VIRTUAL PIANO (C2 ~ C7) ====================
function initVirtualPiano() {
  // C2 (MIDI 36) to C7 (MIDI 96) -> 61 keys
  const notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const startMidi = 36; // C2
  const endMidi = 96;   // C7
  dom.pianoKeyboard.innerHTML = "";

  let whiteKeyIndex = 0;
  const whiteKeyWidth = 28; // CSS와 일치

  for (let midi = startMidi; midi <= endMidi; midi++) {
    const noteIndex = midi % 12;
    const noteName = notes[noteIndex];
    const octave = Math.floor(midi / 12) - 1;
    const pitchName = `${noteName}${octave}`;
    const isBlack = noteName.includes("#");

    const keyEl = document.createElement("div");
    keyEl.dataset.pitch = pitchName;
    keyEl.dataset.midi = midi;

    if (!isBlack) {
      keyEl.className = "piano-key white";
      keyEl.innerHTML = `<span>${noteName === "C" ? `C${octave}` : ""}</span>`;
      dom.pianoKeyboard.appendChild(keyEl);
      whiteKeyIndex++;
    } else {
      keyEl.className = "piano-key black";
      // 검은 건반은 직전 흰 건반의 오른쪽 경계에 걸치도록 위치 계산
      const leftPos = (whiteKeyIndex * whiteKeyWidth) - 10 + 4; // 4px padding
      keyEl.style.left = `${leftPos}px`;
      dom.pianoKeyboard.appendChild(keyEl);
    }

    // 마우스 클릭 시 소리 재생 및 음표 수정
    keyEl.addEventListener("mousedown", (e) => {
      e.preventDefault();
      handlePianoKeyClick(pitchName, midi);
    });
  }
}

function handlePianoKeyClick(pitchName, midi) {
  playTone(pitchName, 0.5);
  highlightPianoKey(pitchName, 400);

  // 음표가 선택되어 있고 수정 모드인 경우 악보 변경 전송
  if (state.isEditMode && state.selectedNote) {
    dispatchScoreEdit({
      new_pitch: pitchName,
      is_chord_add: state.isChordAddMode
    });
  }
}

function highlightPianoKey(pitchName, durationMs = 300) {
  // Enharmonic name handling (Db -> C#, Eb -> D#, etc.)
  const normalizedPitch = normalizePitchForPiano(pitchName);
  const keyEl = dom.pianoKeyboard.querySelector(`[data-pitch="${normalizedPitch}"]`);
  if (keyEl) {
    keyEl.classList.add("active-playing");
    setTimeout(() => {
      keyEl.classList.remove("active-playing");
    }, durationMs);
  }
}

function normalizePitchForPiano(pitch) {
  if (!pitch) return "";
  const enharmonics = {
    "DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#",
    "B#": "C", "E#": "F", "CB": "B", "FB": "E"
  };
  const step = pitch.slice(0, -1).toUpperCase();
  const oct = pitch.slice(-1);
  if (enharmonics[step]) {
    return `${enharmonics[step]}${oct}`;
  }
  return pitch;
}

// ==================== WEB AUDIO & SOUNDFONT ENGINE ====================
function extractPitchFromOsmdNote(note) {
  if (!note) return null;
  if (typeof note.isRest === "function" && note.isRest()) return null;
  if (note.IsRest === true || note.isRest === true) return null;

  const pitch = note.Pitch || note.pitch || (note.sourceNote && (note.sourceNote.Pitch || note.sourceNote.pitch));
  if (!pitch) return null;

  // 1. halfTone (standard MIDI number 12..127) - OSMD 내부 절대 피치
  const halfTone = (typeof pitch.halfTone === "number" && !isNaN(pitch.halfTone)) ? pitch.halfTone :
                   (typeof note.halfTone === "number" && !isNaN(note.halfTone)) ? note.halfTone : null;
  if (halfTone !== null) {
    const noteNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
    const semitone = ((halfTone % 12) + 12) % 12;
    const octave = Math.floor(halfTone / 12) - 1;
    return `${noteNames[semitone]}${octave}`;
  }

  // 2. fundamentalNote & octave
  if (pitch.fundamentalNote !== undefined && pitch.octave !== undefined) {
    const noteNames = ["C", "D", "E", "F", "G", "A", "B"];
    const base = noteNames[pitch.fundamentalNote] || "C";
    let acc = "";
    if (pitch.accidentalHalfTones > 0) acc = "#";
    else if (pitch.accidentalHalfTones < 0) acc = "b";
    return `${base}${acc}${pitch.octave}`;
  }

  // 3. OSMD ToStringShort(0) -> "C4", "G#4", "Bb3"
  if (typeof pitch.ToStringShort === "function") {
    try {
      const s = pitch.ToStringShort(0);
      if (s && /^[A-G][#b]?-?\d+$/i.test(s.trim())) {
        return s.trim();
      }
    } catch (e) {}
  }
  if (pitch.ToStringShortGet && /^[A-G][#b]?-?\d+$/i.test(pitch.ToStringShortGet.trim())) {
    return pitch.ToStringShortGet.trim();
  }

  // 4. Fallback from debug ToString(): "Key: C, Note: 0, octave: 4"
  if (typeof pitch.ToString === "function") {
    try {
      const str = pitch.ToString();
      const m = str.match(/Key:\s*([A-G][#b]?).*?octave:\s*(-?\d+)/i);
      if (m) {
        return `${m[1].toUpperCase()}${m[2]}`;
      }
    } catch (e) {}
  }

  return "C4";
}

function pitchToMidi(pitchStr) {
  if (typeof pitchStr === "number") return pitchStr;
  if (!pitchStr) return 60;
  const noteMap = { C: 0, "C#": 1, DB: 1, D: 2, "D#": 3, EB: 3, E: 4, F: 5, "F#": 6, GB: 6, G: 7, "G#": 8, AB: 8, A: 9, "A#": 10, BB: 10, B: 11 };
  const match = pitchStr.match(/^([A-G][#b]?)(-?\d+)$/i);
  if (!match) return 60;
  const step = match[1].toUpperCase();
  const oct = parseInt(match[2], 10);
  const semi = noteMap[step] !== undefined ? noteMap[step] : 0;
  return (oct + 1) * 12 + semi;
}

function pitchToFrequency(pitchStr) {
  if (typeof pitchStr === "number") {
    return 440 * Math.pow(2, (pitchStr - 69) / 12);
  }
  const midi = pitchToMidi(pitchStr);
  return 440 * Math.pow(2, (midi - 69) / 12);
}

async function initAudioEngine() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  if (!state.audioCtx) {
    state.audioCtx = new AudioContextClass();
  }

  // SoundFont 로딩 시도 (외부 CDN 연결 가능 시 보조 레이어로 장착)
  if (window.Soundfont && dom.toggleSoundfont && dom.toggleSoundfont.checked) {
    try {
      logToConsole("Acoustic Grand Piano SoundFont 로딩 시도...", "system");
      state.soundfontInstrument = await Soundfont.instrument(
        state.audioCtx,
        "acoustic_grand_piano",
        { soundfont: "FluidR3_GM" }
      );
      logToConsole("SoundFont 로딩 완료 (고품질 피아노 레이어 활성화)", "system");
    } catch (e) {
      state.soundfontInstrument = null;
    }
  }
}

async function ensureAudioContext() {
  if (!state.audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      state.audioCtx = new AudioContextClass();
    }
  }
  if (state.audioCtx && state.audioCtx.state === "suspended") {
    try {
      await state.audioCtx.resume();
    } catch (e) {
      console.warn("AudioContext resume failed:", e);
    }
  }
}

function playTone(pitchName, durationSeconds = 0.5) {
  if (!pitchName || pitchName.toUpperCase() === "REST") return;

  // AudioContext가 정지 상태이면 즉시 재개
  if (state.audioCtx && state.audioCtx.state === "suspended") {
    state.audioCtx.resume();
  }

  // 100% 무조건 내장 고품질 Web Audio 피아노 신디사이저로 즉각 연주 (소리 누락 방지 보장)
  playSynthTone(pitchName, durationSeconds);

  // SoundFont가 활성화되어 있고 로드 완료된 경우 보조 레이어로 추가 연주 (옵션)
  if (state.soundfontInstrument && dom.toggleSoundfont && dom.toggleSoundfont.checked) {
    try {
      state.soundfontInstrument.play(pitchName, state.audioCtx.currentTime, {
        duration: durationSeconds,
        gain: state.volume * 0.7
      });
    } catch (e) {
      // ignore
    }
  }
}

function playSynthTone(pitchName, durationSeconds = 0.5) {
  const freq = pitchToFrequency(pitchName);
  if (!freq || isNaN(freq)) return;

  if (!state.audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) state.audioCtx = new AudioContextClass();
  }
  const ctx = state.audioCtx;
  if (!ctx) return;
  if (ctx.state === "suspended") {
    ctx.resume();
  }

  const now = ctx.currentTime;
  const masterVolume = Math.max(0.1, (typeof state.volume === "number" ? state.volume : 0.85));

  // 1. 기본음 바디 (Triangle wave for warm piano body resonance)
  const osc1 = ctx.createOscillator();
  osc1.type = "triangle";
  osc1.frequency.setValueAtTime(freq, now);

  // 2. 기본 순음 (Sine wave for fundamental low-end clarity)
  const osc2 = ctx.createOscillator();
  osc2.type = "sine";
  osc2.frequency.setValueAtTime(freq, now);

  // 3. 2차 배음 (Sine wave for acoustic brightness & string shimmer)
  const osc3 = ctx.createOscillator();
  osc3.type = "sine";
  osc3.frequency.setValueAtTime(freq * 2, now);

  // 4. 피아노 해머 타건 어택 (Subtle tactile transient)
  const oscHammer = ctx.createOscillator();
  oscHammer.type = "triangle";
  oscHammer.frequency.setValueAtTime(freq * 4, now);

  // Gains & Envelopes
  const gain1 = ctx.createGain();
  const gain2 = ctx.createGain();
  const gain3 = ctx.createGain();
  const gainHammer = ctx.createGain();
  const masterGain = ctx.createGain();

  const attackTime = 0.006;
  const decayTime = Math.max(0.25, durationSeconds * 1.5);

  gain1.gain.setValueAtTime(0.0001, now);
  gain1.gain.linearRampToValueAtTime(0.55, now + attackTime);
  gain1.gain.exponentialRampToValueAtTime(0.0001, now + decayTime);

  gain2.gain.setValueAtTime(0.0001, now);
  gain2.gain.linearRampToValueAtTime(0.35, now + attackTime);
  gain2.gain.exponentialRampToValueAtTime(0.0001, now + decayTime * 0.9);

  gain3.gain.setValueAtTime(0.0001, now);
  gain3.gain.linearRampToValueAtTime(0.18, now + attackTime);
  gain3.gain.exponentialRampToValueAtTime(0.0001, now + decayTime * 0.5);

  gainHammer.gain.setValueAtTime(0.0001, now);
  gainHammer.gain.linearRampToValueAtTime(0.12, now + 0.003);
  gainHammer.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);

  masterGain.gain.setValueAtTime(masterVolume, now);

  osc1.connect(gain1);
  osc2.connect(gain2);
  osc3.connect(gain3);
  oscHammer.connect(gainHammer);

  gain1.connect(masterGain);
  gain2.connect(masterGain);
  gain3.connect(masterGain);
  gainHammer.connect(masterGain);

  masterGain.connect(ctx.destination);

  osc1.start(now);
  osc2.start(now);
  osc3.start(now);
  oscHammer.start(now);

  const stopTime = now + decayTime + 0.08;
  osc1.stop(stopTime);
  osc2.stop(stopTime);
  osc3.stop(stopTime);
  oscHammer.stop(stopTime);
}

// ==================== EVENT LISTENERS SETUP ====================
function setupEventListeners() {
  // File Drop & Upload
  dom.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dom.dropzone.classList.add("dragover");
  });
  dom.dropzone.addEventListener("dragleave", () => {
    dom.dropzone.classList.remove("dragover");
  });
  dom.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dom.dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });
  dom.fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });
  dom.clearPreviewBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    resetFileUpload();
  });

  // Step Buttons (Manual mode)
  dom.btnPreprocess.addEventListener("click", () => executePreprocess());
  dom.btnExtract.addEventListener("click", () => executeExtract());
  dom.btnCancelExtract.addEventListener("click", () => cancelExtractJob());
  dom.btnOptimize.addEventListener("click", () => executeOptimize());
  dom.btnRender.addEventListener("click", () => executeRender());

  // New Score & Retry Buttons
  if (dom.newScoreBtn) dom.newScoreBtn.addEventListener("click", () => createNewScore());
  if (dom.heroNewScoreBtn) dom.heroNewScoreBtn.addEventListener("click", () => createNewScore());
  if (dom.heroUploadBtn) dom.heroUploadBtn.addEventListener("click", () => dom.fileInput.click());
  if (dom.btnRetryExtract) dom.btnRetryExtract.addEventListener("click", () => retryExtract(false));
  if (dom.btnSwitchModeRetry) dom.btnSwitchModeRetry.addEventListener("click", () => retryExtract(true));
  if (dom.clearCacheBtn) dom.clearCacheBtn.addEventListener("click", () => executeClearCache());

  // User Manual Modal & Tabs
  const openManual = (tabId = null) => {
    dom.guideModal.classList.remove("hidden");
    if (tabId) switchGuideTab(tabId);
  };
  const closeManual = () => dom.guideModal.classList.add("hidden");

  if (dom.userManualBtn) dom.userManualBtn.addEventListener("click", () => openManual("tab-start"));
  if (dom.helpBtn) dom.helpBtn.addEventListener("click", () => openManual("tab-shortcuts"));
  if (dom.heroManualBtn) dom.heroManualBtn.addEventListener("click", () => openManual("tab-start"));
  if (dom.closeGuideBtn) dom.closeGuideBtn.addEventListener("click", closeManual);

  dom.guideModal.addEventListener("click", (e) => {
    if (e.target === dom.guideModal) closeManual();
  });

  dom.modalTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.dataset.tab;
      switchGuideTab(targetTab);
    });
  });

  // Playback Controls
  dom.btnPlayPause.addEventListener("click", () => togglePlayPause());
  dom.btnStop.addEventListener("click", () => stopPlayback());
  if (dom.btnDlWav) dom.btnDlWav.addEventListener("click", () => exportScoreToWav());

  dom.sliderBpm.addEventListener("input", (e) => {
    state.bpm = parseInt(e.target.value, 10);
    dom.inputBpm.value = state.bpm;
  });
  dom.inputBpm.addEventListener("change", (e) => {
    state.bpm = Math.max(40, Math.min(200, parseInt(e.target.value, 10) || 100));
    dom.sliderBpm.value = state.bpm;
  });
  dom.sliderVolume.addEventListener("input", (e) => {
    state.volume = parseInt(e.target.value, 10) / 100;
  });

  // Zoom Controls
  dom.btnZoomIn.addEventListener("click", () => changeZoom(0.15));
  dom.btnZoomOut.addEventListener("click", () => changeZoom(-0.15));
  dom.btnZoomReset.addEventListener("click", () => resetZoom());

  // Staff Switcher
  dom.btnPartRh.addEventListener("click", () => setTargetPart(0));
  dom.btnPartLh.addEventListener("click", () => setTargetPart(1));

  // Edit Mode Toggle
  dom.btnToggleEditMode.addEventListener("click", () => toggleEditMode());

  // Undo / Redo Buttons
  dom.btnUndo.addEventListener("click", () => executeRestore("undo"));
  dom.btnRedo.addEventListener("click", () => executeRestore("redo"));

  // Editing Palette Actions
  dom.btnPitchUp.addEventListener("click", () => dispatchScoreEdit({ action: "semitone_up" }));
  dom.btnPitchDown.addEventListener("click", () => dispatchScoreEdit({ action: "semitone_down" }));
  dom.btnOctUp.addEventListener("click", () => dispatchScoreEdit({ action: "octave_up" }));
  dom.btnOctDown.addEventListener("click", () => dispatchScoreEdit({ action: "octave_down" }));
  dom.btnMakeRest.addEventListener("click", () => dispatchScoreEdit({ action: "delete" }));
  dom.btnDeleteNote.addEventListener("click", () => dispatchScoreEdit({ action: "delete" }));

  dom.btnAccSharp.addEventListener("click", () => applyAccidental("#"));
  dom.btnAccFlat.addEventListener("click", () => applyAccidental("b"));
  dom.btnAccNatural.addEventListener("click", () => applyAccidental(""));

  dom.durationButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      dom.durationButtons.forEach(b => b.classList.remove("active-duration"));
      btn.classList.add("active-duration");
      state.currentDuration = parseFloat(btn.dataset.duration);
      if (state.isEditMode && state.selectedNote) {
        dispatchScoreEdit({ new_duration: state.currentDuration });
      }
    });
  });

  dom.btnChordToggle.addEventListener("click", () => {
    state.isChordAddMode = !state.isChordAddMode;
    updateChordBadge();
  });
}

function switchGuideTab(tabId) {
  dom.modalTabBtns.forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tabId);
  });
  dom.guidePanels.forEach(panel => {
    panel.classList.toggle("active", panel.id === tabId);
  });
}

function setupKeyboardShortcuts() {
  window.addEventListener("keydown", (e) => {
    // 텍스트 인풋 포커스 시 단축키 무시
    if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;

    if (e.code === "Space") {
      e.preventDefault();
      togglePlayPause();
      return;
    }

    if (e.key === "Shift") {
      state.isChordAddMode = true;
      updateChordBadge();
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      executeRestore("undo");
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
      e.preventDefault();
      executeRestore("redo");
      return;
    }

    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      if (state.isEditMode && state.selectedNote) {
        dispatchScoreEdit({ action: "delete" });
      }
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (state.isEditMode && state.selectedNote) {
        dispatchScoreEdit({ action: "semitone_up" });
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (state.isEditMode && state.selectedNote) {
        dispatchScoreEdit({ action: "semitone_down" });
      }
      return;
    }

    if (e.key === "ArrowRight") {
      e.preventDefault();
      stepCursor(1);
      return;
    }

    if (e.key === "ArrowLeft") {
      e.preventDefault();
      stepCursor(-1);
      return;
    }

    // Direct pitch input C~B
    const upperKey = e.key.toUpperCase();
    if (["C", "D", "E", "F", "G", "A", "B"].includes(upperKey)) {
      e.preventDefault();
      const currentOctave = state.selectedNote ? extractOctave(state.selectedNote.pitch) : 4;
      const targetPitch = `${upperKey}${currentOctave}`;
      handlePianoKeyClick(targetPitch);
      return;
    }

    // Duration shortcuts 1, 2, 4, 8, 6
    const durMap = { "1": 4.0, "2": 2.0, "4": 1.0, "8": 0.5, "6": 0.25 };
    if (durMap[e.key]) {
      e.preventDefault();
      state.currentDuration = durMap[e.key];
      dom.durationButtons.forEach(b => {
        b.classList.toggle("active-duration", parseFloat(b.dataset.duration) === state.currentDuration);
      });
      if (state.isEditMode && state.selectedNote) {
        dispatchScoreEdit({ new_duration: state.currentDuration });
      }
    }
  });

  window.addEventListener("keyup", (e) => {
    if (e.key === "Shift") {
      state.isChordAddMode = false;
      updateChordBadge();
    }
  });
}

function updateChordBadge() {
  dom.chordBadge.classList.toggle("hidden", !state.isChordAddMode);
  dom.btnChordToggle.classList.toggle("active-duration", state.isChordAddMode);
}

function extractOctave(pitchStr) {
  if (!pitchStr) return 4;
  const match = pitchStr.match(/\d+$/);
  return match ? parseInt(match[0], 10) : 4;
}

// ==================== HYBRID PIPELINE LOGIC ====================
function handleFileSelected(file) {
  state.currentFile = file;
  state.filename = file.name;

  // Preview display
  if (file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (e) => {
      dom.imgPreview.src = e.target.result;
      dom.previewBox.classList.remove("hidden");
      dom.dropzonePrompt.classList.add("hidden");
    };
    reader.readAsDataURL(file);
  } else {
    dom.imgPreview.src = "";
    dom.previewBox.classList.add("hidden");
    dom.dropzonePrompt.classList.remove("hidden");
  }

  dom.btnPreprocess.disabled = false;
  logToConsole(`파일 업로드 준비됨: ${file.name}`);

  // ⚡ 원클릭 자동 진행 모드일 경우 연속 실행 체인 트리거
  if (state.isAutoMode) {
    runAutoPipelineChain();
  }
}

function resetFileUpload() {
  state.currentFile = null;
  state.fileHash = null;
  dom.fileInput.value = "";
  dom.previewBox.classList.add("hidden");
  dom.dropzonePrompt.classList.remove("hidden");
  dom.btnPreprocess.disabled = true;
  dom.btnExtract.disabled = true;
  dom.btnOptimize.disabled = true;
  dom.btnRender.disabled = true;
}

async function runAutoPipelineChain() {
  logToConsole("⚡ [원클릭 자동 진행] 전체 파이프라인 시작...", "system");
  try {
    // 1. Preprocess
    const preRes = await executePreprocess();
    if (!preRes) return;

    // 2. Extract & Poll
    const extSuccess = await executeExtract();
    if (!extSuccess) return;

    // 3. Optimize
    const optRes = await executeOptimize();
    if (!optRes) return;

    // 4. Render
    await executeRender();
    logToConsole("🎉 악보 OMR 및 렌더링이 성공적으로 완료되었습니다!", "system");
  } catch (err) {
    logToConsole(`파이프라인 체인 오류: ${err.message}`, "error");
  }
}

async function executePreprocess() {
  if (!state.currentFile) return null;
  setStepStatus(dom.statusPreprocess, "processing", "전처리 중...");
  logToConsole("[1단계] 악보 기울기 보정 및 해상도 최적화 중...");

  const formData = new FormData();
  formData.append("file", state.currentFile);

  try {
    const res = await fetch("/api/preprocess", { method: "POST", body: formData });
    if (!res.ok) throw new Error((await res.json()).detail || "전처리 실패");
    const data = await res.json();
    state.fileHash = data.file_hash;

    setStepStatus(dom.statusPreprocess, "ready", "완료");
    dom.btnExtract.disabled = false;
    logToConsole(`전처리 완료. File Hash: ${data.file_hash.substring(0, 10)}...`);
    return data;
  } catch (e) {
    setStepStatus(dom.statusPreprocess, "error", "실패");
    logToConsole(`전처리 오류: ${e.message}`, "error");
    throw e;
  }
}

async function executeExtract() {
  if (!state.fileHash) return false;

  const mode = document.querySelector('input[name="omr_mode"]:checked').value;
  setStepStatus(dom.statusExtract, "processing", "OMR 구동 중...");
  dom.btnCancelExtract.classList.remove("hidden");
  dom.btnExtract.disabled = true;
  if (dom.omrRetryBox) dom.omrRetryBox.classList.add("hidden");
  logToConsole(`[2단계] AI OMR 인식 시작 (모드: ${mode})...`);

  try {
    const res = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_hash: state.fileHash, filename: state.filename, mode })
    });
    if (!res.ok) throw new Error((await res.json()).detail || "OMR 작업 시작 실패");
    const data = await res.json();
    state.activeJobId = data.job_id;

    // 진행률 폴링 시작 (Promise 반환)
    return await pollExtractStatus(data.job_id);
  } catch (e) {
    setStepStatus(dom.statusExtract, "error", "실패");
    dom.btnCancelExtract.classList.add("hidden");
    dom.btnExtract.disabled = false;
    showOmrFailure(e.message);
    logToConsole(`OMR 시작 실패: ${e.message}`, "error");
    throw e;
  }
}

function showOmrFailure(errorMsg) {
  if (dom.omrRetryBox) {
    dom.omrRetryBox.classList.remove("hidden");
    if (dom.retryErrorMsg) {
      dom.retryErrorMsg.textContent = errorMsg || "악보 인식 중 오류가 발생했습니다. 재시도를 권장합니다.";
    }
  }
}

function pollExtractStatus(jobId) {
  return new Promise((resolve, reject) => {
    if (state.pollInterval) clearInterval(state.pollInterval);

    let pollCount = 0;
    const MAX_POLLS = 400; // 400 * 1.5초 = 600초 (10분 타임아웃, 백엔드 엔진 최대 처리 시간과 일치)
    let consecutiveErrors = 0;

    state.pollInterval = setInterval(async () => {
      pollCount++;
      if (pollCount > MAX_POLLS) {
        clearInterval(state.pollInterval);
        dom.btnCancelExtract.classList.add("hidden");
        dom.btnExtract.disabled = false;
        setStepStatus(dom.statusExtract, "error", "시간 초과");
        const timeoutMsg = "악보 분석 시간이 초과되었습니다 (10분 초과). [모드 전환 후 재시도]를 권장합니다.";
        showOmrFailure(timeoutMsg);
        logToConsole(timeoutMsg, "error");
        reject(new Error(timeoutMsg));
        return;
      }

      try {
        const res = await fetch(`/api/extract/status/${jobId}`);
        if (!res.ok) {
          consecutiveErrors++;
          if (consecutiveErrors >= 8) {
            clearInterval(state.pollInterval);
            dom.btnCancelExtract.classList.add("hidden");
            dom.btnExtract.disabled = false;
            setStepStatus(dom.statusExtract, "error", "서버 응답 없음");
            const serverErrMsg = "서버 응답이 없습니다 (연결 끊김 감지). [다시 시도]를 눌러주세요.";
            showOmrFailure(serverErrMsg);
            logToConsole(serverErrMsg, "error");
            reject(new Error(serverErrMsg));
            return;
          }
          return;
        }

        consecutiveErrors = 0;
        const statusData = await res.json();

        // UI 갱신
        const pct = statusData.percent || 0;
        dom.omrProgressBar.style.width = `${pct}%`;
        dom.omrPercentText.textContent = `${pct}%`;
        dom.omrProgressText.textContent = statusData.message || "분석 중...";
        if (statusData.message) {
          logToConsole(statusData.message);
        }

        if (statusData.status === "completed") {
          clearInterval(state.pollInterval);
          dom.btnCancelExtract.classList.add("hidden");
          dom.btnExtract.disabled = false;
          if (dom.omrRetryBox) dom.omrRetryBox.classList.add("hidden");
          setStepStatus(dom.statusExtract, "ready", "완료 (100%)");
          dom.btnOptimize.disabled = false;
          logToConsole("MusicXML OMR 추출 완료!", "system");
          resolve(true);
        } else if (statusData.status === "failed") {
          clearInterval(state.pollInterval);
          dom.btnCancelExtract.classList.add("hidden");
          dom.btnExtract.disabled = false;
          setStepStatus(dom.statusExtract, "error", "실패");
          showOmrFailure(statusData.error || statusData.message);
          logToConsole(`OMR 분석 실패: ${statusData.error}`, "error");
          reject(new Error(statusData.error || "OMR 실패"));
        } else if (statusData.status === "cancelled") {
          clearInterval(state.pollInterval);
          dom.btnCancelExtract.classList.add("hidden");
          dom.btnExtract.disabled = false;
          setStepStatus(dom.statusExtract, "error", "취소됨");
          logToConsole("OMR 작업이 취소되었습니다.");
          resolve(false);
        }
      } catch (err) {
        clearInterval(state.pollInterval);
        dom.btnCancelExtract.classList.add("hidden");
        dom.btnExtract.disabled = false;
        showOmrFailure(err.message);
        reject(err);
      }
    }, 1500);
  });
}

async function cancelExtractJob() {
  if (!state.activeJobId) return;
  try {
    await fetch(`/api/extract/${state.activeJobId}/cancel`, { method: "POST" });
    logToConsole("작업 취소 신호를 보냈습니다.", "system");
  } catch (e) {
    console.error(e);
  }
}

async function executeOptimize() {
  if (!state.fileHash) return null;
  setStepStatus(dom.statusOptimize, "processing", "교정 중...");
  logToConsole("[3단계] 음악 규칙 기반 자동 교정(노이즈 제거, 옥타브 클램핑) 실행 중...");

  try {
    const res = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_hash: state.fileHash })
    });
    if (!res.ok) throw new Error((await res.json()).detail || "최적화 실패");
    const data = await res.json();
    setStepStatus(dom.statusOptimize, "ready", "교정 완료");
    dom.btnRender.disabled = false;
    logToConsole("악보 규칙 교정 완료!");
    return data;
  } catch (e) {
    setStepStatus(dom.statusOptimize, "error", "실패");
    logToConsole(`교정 오류: ${e.message}`, "error");
    throw e;
  }
}

async function executeRender() {
  if (!state.fileHash) return;
  logToConsole("[4단계] 악보 렌더링 및 MIDI 사운드 준비 중...");

  try {
    const res = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_hash: state.fileHash })
    });
    if (!res.ok) throw new Error((await res.json()).detail || "렌더링 실패");
    const data = await res.json();

    // 분석 메타데이터 반영
    updateAnalysisUI(data.analysis);

    // 다운로드 링크 활성화
    updateDownloadLinks(state.fileHash);

    // OSMD 악보 렌더링
    state.currentXmlUrl = data.xml_url;
    await renderOsmdScore(data.xml_url);
    backupCurrentState();

    logToConsole("악보 렌더링 완료! 에디터에서 바로 재생 및 편집할 수 있습니다.", "system");
  } catch (e) {
    logToConsole(`렌더링 오류: ${e.message}`, "error");
    throw e;
  }
}

async function createNewScore() {
  logToConsole("새 4마디 빈 악보(대보표) 생성 중...", "system");
  try {
    const res = await fetch("/api/score/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "새 악보",
        time_signature: "4/4",
        key_signature: "C",
        measures_count: 4,
        is_grand_staff: true
      })
    });
    if (!res.ok) throw new Error((await res.json()).detail || "새 악보 생성 실패");
    const data = await res.json();
    state.fileHash = data.file_hash;
    state.filename = data.filename;

    setStepStatus(dom.statusPreprocess, "ready", "새 악보");
    setStepStatus(dom.statusExtract, "ready", "새 악보");
    setStepStatus(dom.statusOptimize, "ready", "초기화됨");

    updateAnalysisUI(data.analysis);
    updateDownloadLinks(data.file_hash);

    state.currentXmlUrl = data.xml_url;
    await renderOsmdScore(data.xml_url);
    backupCurrentState();

    setEditMode(true);
    logToConsole("✨ 새 악보가 생성되었습니다! 악보 위의 쉼표를 클릭하거나 건반을 눌러 즉시 편집/작곡을 시작하세요.", "system");
  } catch (err) {
    logToConsole(`새 악보 생성 오류: ${err.message}`, "error");
  }
}

async function retryExtract(switchMode = false) {
  if (!state.fileHash) {
    logToConsole("재시도할 업로드 악보가 없습니다. 먼저 악보 파일을 업로드해 주세요.", "error");
    return;
  }

  if (switchMode) {
    const currentMode = document.querySelector('input[name="omr_mode"]:checked').value;
    const nextMode = currentMode === "fast" ? "deep" : "fast";
    const radioToSelect = document.querySelector(`input[name="omr_mode"][value="${nextMode}"]`);
    if (radioToSelect) radioToSelect.checked = true;
    logToConsole(`🔄 OMR 인식 모드를 [${nextMode === "fast" ? "⚡ 빠름 (Fast)" : "🔬 정밀 (Deep CLAHE)"}]로 전환했습니다.`, "system");
  }

  if (dom.omrRetryBox) dom.omrRetryBox.classList.add("hidden");
  logToConsole("🔄 OMR 인식을 다시 시도합니다...", "system");

  try {
    const extSuccess = await executeExtract();
    if (extSuccess) {
      await executeOptimize();
      await executeRender();
      logToConsole("🎉 악보 OMR 재시도 및 렌더링이 성공적으로 완료되었습니다!", "system");
    }
  } catch (err) {
    logToConsole(`재시도 실패: ${err.message}`, "error");
  }
}

function setStepStatus(el, statusClass, text) {
  el.className = `status-indicator ${statusClass}`;
  el.textContent = text;
}

function updateAnalysisUI(analysis) {
  if (!analysis) return;
  dom.valKey.textContent = analysis.key_signature || "-";
  dom.valTime.textContent = analysis.time_signature || "-";
  dom.valMeasures.textContent = analysis.total_measures || "0";
  dom.valNotes.textContent = analysis.total_notes || "0";
  dom.valParts.textContent = `${analysis.total_parts || 1} 파트`;

  // 단일 선율일 경우 보표 버튼 상태 자동 조정
  if (analysis.total_parts <= 1) {
    dom.btnPartLh.disabled = true;
    dom.btnPartLh.title = "단일 파트 악보에서는 왼손 보표를 선택할 수 없습니다.";
  } else {
    dom.btnPartLh.disabled = false;
    dom.btnPartLh.title = "";
  }
}

// ==================== OPEN SHEET MUSIC DISPLAY (OSMD) ====================
async function renderOsmdScore(xmlUrl) {
  dom.sheetPlaceholder.classList.add("hidden");
  dom.osmdContainer.innerHTML = "";

  state.osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(dom.osmdContainer, {
    autoResize: true,
    backend: "svg",
    drawingParameters: "compacttight",
    drawPartNames: true,
    drawTitle: true,
    followCursor: true,
    renderSingleHorizontalPage: false
  });

  try {
    await state.osmd.load(xmlUrl);
    state.osmd.zoom = state.zoomLevel;
    state.osmd.render();

    // 커서 활성화
    state.osmd.cursor.show();
    state.osmd.cursor.reset();

    // 악보 인터랙티브 클릭 이벤트 및 연주 타임라인 빌드
    setupOsmdClickEvents();
    buildPlaybackTimeline();
    updateCursorSelection();
  } catch (err) {
    console.error("OSMD 렌더링 실패:", err);
    logToConsole(`OSMD 렌더링 실패: ${err.message}`, "error");
  }
}

function changeZoom(delta) {
  state.zoomLevel = Math.max(0.5, Math.min(2.0, state.zoomLevel + delta));
  dom.zoomLevelText.textContent = `${Math.round(state.zoomLevel * 100)}%`;
  if (state.osmd) {
    state.osmd.zoom = state.zoomLevel;
    state.osmd.render();
  }
}

function resetZoom() {
  state.zoomLevel = 1.0;
  dom.zoomLevelText.textContent = "100%";
  if (state.osmd) {
    state.osmd.zoom = 1.0;
    state.osmd.render();
  }
}

let osmdClickSetupDone = false;
function setupOsmdClickEvents() {
  if (osmdClickSetupDone) return;
  osmdClickSetupDone = true;
  const container = dom.osmdContainer;
  container.addEventListener("click", (e) => {
    // SVG 엘리먼트 클릭 시 가장 가까운 그래픽 음표/기호 탐색
    if (!state.osmd || !state.osmd.cursor) return;

    // 클릭 위치에 가까운 마디/음표를 선택하도록 커서 동기화
    updateCursorSelection();
  });
}

function stepCursor(direction) {
  if (!state.osmd || !state.osmd.cursor) return;
  if (direction > 0) {
    state.osmd.cursor.next();
  } else {
    state.osmd.cursor.previous();
  }
  updateCursorSelection();
}

function updateCursorSelection() {
  if (!state.osmd || !state.osmd.cursor) return;
  const iterator = state.osmd.cursor.iterator;
  if (!iterator) return;

  const currentMeasure = iterator.CurrentMeasureNumber || (iterator.currentMeasureIndex + 1);
  const currentVoiceEntries = iterator.CurrentVoiceEntries || [];
  const currentFraction = iterator.currentTimeStamp;
  const measureOffset = currentFraction ? currentFraction.RealValue : 0.0;

  let foundPitch = null;
  let foundDuration = 1.0;
  let isRest = false;

  // 타겟팅된 partIndex의 음표 탐색
  for (const ve of currentVoiceEntries) {
    for (const note of ve.Notes || []) {
      if (note.isRest && note.isRest()) {
        isRest = true;
      } else {
        const p = extractPitchFromOsmdNote(note);
        if (p) {
          foundPitch = p;
          foundDuration = note.Length ? note.Length.RealValue * 4 : 1.0; // quarter length
          break;
        }
      }
    }
    if (foundPitch || isRest) break;
  }

  state.selectedNote = {
    measureNumber: currentMeasure,
    offset: measureOffset,
    pitch: isRest ? "REST" : (foundPitch || "C4"),
    duration: foundDuration,
    partIndex: state.targetPartIndex
  };

  const partName = state.targetPartIndex === 0 ? "오른손(RH)" : "왼손(LH)";
  const pitchDisplay = isRest ? "𝄽 쉼표 (REST)" : `🎵 ${state.selectedNote.pitch}`;
  dom.selectedNoteDisplay.textContent = 
    `선택: ${currentMeasure}마디 | ${partName} | ${pitchDisplay} | 박자: ${state.selectedNote.duration.toFixed(2)}`;

  if (foundPitch && !state.isPlaying) {
    playTone(foundPitch, 0.35);
    highlightPianoKey(foundPitch, 250);
  }
}

let isEditInFlight = false;

// ==================== SCORE EDITING DISPATCHER ====================
async function dispatchScoreEdit(payload) {
  if (!state.fileHash || !state.selectedNote) {
    alert("편집할 악보와 음표가 선택되지 않았습니다.");
    return;
  }

  if (isEditInFlight) {
    // 빠른 연타/단축키 폭주 방지 (In-Flight Lock & Debounce)
    return;
  }

  isEditInFlight = true;
  if (dom.editorPalette) {
    dom.editorPalette.classList.add("palette-busy");
  }

  const bodyData = {
    file_hash: state.fileHash,
    measure_number: state.selectedNote.measureNumber,
    note_offset: state.selectedNote.offset,
    part_index: state.targetPartIndex,
    new_pitch: payload.new_pitch || state.selectedNote.pitch,
    new_duration: payload.new_duration || state.currentDuration,
    is_chord_add: payload.is_chord_add || false,
    action: payload.action || null
  };

  try {
    const res = await fetch("/api/edit_score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyData)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "음표 수정 실패");
    }

    const result = await res.json();
    logToConsole(result.message);

    // 새 XML로 악보 재렌더링
    const targetUrl = `/api/cache/${state.fileHash}_opt.musicxml?t=${Date.now()}`;
    await renderOsmdScore(targetUrl);

    // 편집 상태 로컬스토리지 백업
    backupCurrentState();

    // Undo 버튼 활성화
    dom.btnUndo.disabled = false;
  } catch (err) {
    alert(`수정 오류: ${err.message}`);
    logToConsole(`음표 수정 실패: ${err.message}`, "error");
  } finally {
    isEditInFlight = false;
    if (dom.editorPalette) {
      dom.editorPalette.classList.remove("palette-busy");
    }
  }
}

async function executeRestore(action) {
  if (!state.fileHash) return;
  try {
    const res = await fetch("/api/restore_score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_hash: state.fileHash, action })
    });
    if (!res.ok) throw new Error("스냅샷 복원 실패");
    const data = await res.json();
    if (data.status === "noop") {
      logToConsole(data.message);
      return;
    }

    logToConsole(`${action === "undo" ? "실행 취소(Undo)" : "다시 실행(Redo)"} 완료`);
    const targetUrl = `/api/cache/${state.fileHash}_opt.musicxml?t=${Date.now()}`;
    await renderOsmdScore(targetUrl);
    backupCurrentState();
  } catch (err) {
    logToConsole(`복원 실패: ${err.message}`, "error");
  }
}

function applyAccidental(accidentalSymbol) {
  if (!state.selectedNote || !state.selectedNote.pitch || state.selectedNote.pitch === "REST") return;
  let p = state.selectedNote.pitch;
  const match = p.match(/^([A-G])([#b]?)(-?\d+)$/i);
  if (!match) return;
  const newPitch = `${match[1]}${accidentalSymbol}${match[3]}`;
  dispatchScoreEdit({ new_pitch: newPitch });
}

function setTargetPart(partIdx) {
  state.targetPartIndex = partIdx;
  dom.btnPartRh.classList.toggle("active", partIdx === 0);
  dom.btnPartLh.classList.toggle("active", partIdx === 1);
  dom.partIndicator.textContent = `Part ${partIdx} 타겟팅`;
  logToConsole(`편집 대상 보표가 [Part ${partIdx}: ${partIdx === 0 ? "오른손" : "왼손"}]으로 변경되었습니다.`);
  updateCursorSelection();
}

function setEditMode(enable) {
  state.isEditMode = enable;
  dom.editorPalette.classList.toggle("disabled-palette", !state.isEditMode);
  dom.btnToggleEditMode.classList.toggle("btn-primary", state.isEditMode);
  dom.btnToggleEditMode.classList.toggle("btn-outline", !state.isEditMode);

  dom.editModeIcon.textContent = state.isEditMode ? "🔒" : "✏️";
  dom.editModeText.textContent = state.isEditMode ? "수정 모드 완료" : "수정 모드 켜기";
}

function toggleEditMode() {
  setEditMode(!state.isEditMode);
}

// ==================== WEB AUDIO PLAYBACK TIMELINE ====================
function buildPlaybackTimeline() {
  if (!state.osmd || !state.osmd.cursor) return;
  state.scoreNotesTimeline = [];

  const cursor = state.osmd.cursor;
  cursor.reset();

  let accumulatedBeats = 0.0;
  let stepIndex = 0;

  while (!cursor.iterator.EndReached) {
    const iterator = cursor.iterator;
    const currentMeasure = iterator.CurrentMeasureNumber || (iterator.currentMeasureIndex + 1) || 1;
    const notesInStep = [];

    // 1. Primary: cursor.NotesUnderCursor() (OSMD 표준 최상위 인터페이스)
    let cursorNotes = [];
    if (typeof cursor.NotesUnderCursor === "function") {
      try {
        cursorNotes = cursor.NotesUnderCursor() || [];
      } catch (e) {
        cursorNotes = [];
      }
    }

    for (const note of cursorNotes) {
      const p = extractPitchFromOsmdNote(note);
      if (p && !notesInStep.includes(p)) {
        notesInStep.push(p);
      }
    }

    // 2. Secondary: CurrentVoiceEntries / currentVoiceEntries
    const voiceEntries = iterator.CurrentVoiceEntries || iterator.currentVoiceEntries || [];
    for (const ve of voiceEntries) {
      const noteList = ve.Notes || ve.notes || [];
      for (const note of noteList) {
        const p = extractPitchFromOsmdNote(note);
        if (p && !notesInStep.includes(p)) {
          notesInStep.push(p);
        }
      }
    }

    // Step duration in beats (quarter lengths)
    let stepDuration = 1.0;
    if (cursorNotes.length > 0) {
      const len = cursorNotes[0].Length || cursorNotes[0].length;
      if (len && typeof len.RealValue === "number" && len.RealValue > 0) {
        stepDuration = len.RealValue * 4;
      }
    } else if (voiceEntries.length > 0) {
      const ve0 = voiceEntries[0];
      const noteList = ve0.Notes || ve0.notes || [];
      if (noteList.length > 0) {
        const len = noteList[0].Length || noteList[0].length;
        if (len && typeof len.RealValue === "number" && len.RealValue > 0) {
          stepDuration = len.RealValue * 4;
        }
      }
    }
    if (!stepDuration || isNaN(stepDuration) || stepDuration <= 0) {
      stepDuration = 1.0;
    }

    state.scoreNotesTimeline.push({
      stepIndex,
      accumulatedBeats,
      pitches: notesInStep,
      duration: stepDuration,
      measureNum: currentMeasure
    });

    accumulatedBeats += stepDuration;
    stepIndex++;
    cursor.next();
  }

  cursor.reset();
  if (state.scoreNotesTimeline.length > 0) {
    logToConsole(`🎵 연주 타임라인 구축 완료: 총 ${state.scoreNotesTimeline.length}개 스텝 준비됨.`, "system");
  }
}

// ==================== WAV AUDIO EXPORT ENGINE (CLIENT OFFLINE CONTEXT) ====================
async function exportScoreToWav() {
  if (!state.osmd) {
    await loadDefaultDemoScore();
  }
  if (!state.scoreNotesTimeline || state.scoreNotesTimeline.length === 0) {
    buildPlaybackTimeline();
  }
  if (!state.scoreNotesTimeline || state.scoreNotesTimeline.length === 0) {
    alert("다운로드할 악보 음표가 없습니다. 악보를 먼저 로드해 주세요.");
    return;
  }

  logToConsole("🎵 악보를 고품질 WAV 음원 파일로 렌더링 중...", "system");
  const secondsPerBeat = 60.0 / (state.bpm || 100);
  const lastEvent = state.scoreNotesTimeline[state.scoreNotesTimeline.length - 1];
  const totalDuration = (lastEvent.accumulatedBeats + lastEvent.duration) * secondsPerBeat + 1.2;
  const sampleRate = 44100;
  const totalSamples = Math.ceil(totalDuration * sampleRate);

  const OfflineAudioCtxClass = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!OfflineAudioCtxClass) {
    alert("이 브라우저는 WAV 오디오 렌더링을 지원하지 않습니다. [🎹 MIDI 받기]를 이용해 주세요.");
    return;
  }

  try {
    const offlineCtx = new OfflineAudioCtxClass(2, totalSamples, sampleRate);
    const masterVolume = Math.max(0.1, (typeof state.volume === "number" ? state.volume : 0.85));

    state.scoreNotesTimeline.forEach(event => {
      const startTime = event.accumulatedBeats * secondsPerBeat;
      const dur = Math.max(0.2, event.duration * secondsPerBeat * 0.95);

      (event.pitches || []).forEach(pitch => {
        const freq = pitchToFrequency(pitch);
        if (!freq || isNaN(freq)) return;

        const osc1 = offlineCtx.createOscillator();
        osc1.type = "triangle";
        osc1.frequency.setValueAtTime(freq, startTime);

        const osc2 = offlineCtx.createOscillator();
        osc2.type = "sine";
        osc2.frequency.setValueAtTime(freq, startTime);

        const osc3 = offlineCtx.createOscillator();
        osc3.type = "sine";
        osc3.frequency.setValueAtTime(freq * 2, startTime);

        const oscH = offlineCtx.createOscillator();
        oscH.type = "triangle";
        oscH.frequency.setValueAtTime(freq * 4, startTime);

        const gain1 = offlineCtx.createGain();
        const gain2 = offlineCtx.createGain();
        const gain3 = offlineCtx.createGain();
        const gainH = offlineCtx.createGain();
        const noteMaster = offlineCtx.createGain();

        const attackTime = 0.006;
        const decayTime = Math.max(0.25, dur * 1.5);

        gain1.gain.setValueAtTime(0.0001, startTime);
        gain1.gain.linearRampToValueAtTime(0.5, startTime + attackTime);
        gain1.gain.exponentialRampToValueAtTime(0.0001, startTime + decayTime);

        gain2.gain.setValueAtTime(0.0001, startTime);
        gain2.gain.linearRampToValueAtTime(0.3, startTime + attackTime);
        gain2.gain.exponentialRampToValueAtTime(0.0001, startTime + decayTime * 0.9);

        gain3.gain.setValueAtTime(0.0001, startTime);
        gain3.gain.linearRampToValueAtTime(0.15, startTime + attackTime);
        gain3.gain.exponentialRampToValueAtTime(0.0001, startTime + decayTime * 0.5);

        gainH.gain.setValueAtTime(0.0001, startTime);
        gainH.gain.linearRampToValueAtTime(0.1, startTime + 0.003);
        gainH.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.04);

        noteMaster.gain.setValueAtTime(masterVolume, startTime);

        osc1.connect(gain1);
        osc2.connect(gain2);
        osc3.connect(gain3);
        oscH.connect(gainH);

        gain1.connect(noteMaster);
        gain2.connect(noteMaster);
        gain3.connect(noteMaster);
        gainH.connect(noteMaster);

        noteMaster.connect(offlineCtx.destination);

        osc1.start(startTime);
        osc2.start(startTime);
        osc3.start(startTime);
        oscH.start(startTime);

        const stopTime = startTime + decayTime + 0.08;
        osc1.stop(stopTime);
        osc2.stop(stopTime);
        osc3.stop(stopTime);
        oscH.stop(stopTime);
      });
    });

    const renderedBuffer = await offlineCtx.startRendering();
    const wavBlob = audioBufferToWavBlob(renderedBuffer);
    const downloadUrl = URL.createObjectURL(wavBlob);

    const a = document.createElement("a");
    a.style.display = "none";
    a.href = downloadUrl;
    const baseName = (state.filename || "museai_score").replace(/\.[^/.]+$/, "");
    a.download = `${baseName}_audio.wav`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(downloadUrl), 5000);

    logToConsole("🎉 고품질 WAV 음원 다운로드가 완료되었습니다!", "system");
  } catch (err) {
    console.error("WAV 렌더링 실패:", err);
    logToConsole(`WAV 렌더링 오류: ${err.message}`, "error");
    alert(`WAV 음원 생성 오류: ${err.message}`);
  }
}

function audioBufferToWavBlob(buffer) {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;
  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;

  const dataLength = buffer.length * blockAlign;
  const bufferLength = 44 + dataLength;
  const arrayBuffer = new ArrayBuffer(bufferLength);
  const view = new DataView(arrayBuffer);

  function writeString(offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(36, "data");
  view.setUint32(40, dataLength, true);

  const channels = [];
  for (let i = 0; i < numChannels; i++) {
    channels.push(buffer.getChannelData(i));
  }

  let offset = 44;
  for (let i = 0; i < buffer.length; i++) {
    for (let channel = 0; channel < numChannels; channel++) {
      let sample = channels[channel][i];
      sample = Math.max(-1, Math.min(1, sample));
      const intSample = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
      view.setInt16(offset, intSample, true);
      offset += 2;
    }
  }

  return new Blob([arrayBuffer], { type: "audio/wav" });
}

async function togglePlayPause() {
  await ensureAudioContext();
  if (state.isPlaying) {
    pausePlayback();
  } else {
    await startPlayback();
  }
}

async function startPlayback() {
  if (!state.osmd) {
    await loadDefaultDemoScore();
  }
  if (!state.osmd) {
    alert("악보가 로드되지 않았습니다.");
    return;
  }

  // 타임라인이 비어있으면 즉시 재구축
  if (!state.scoreNotesTimeline || state.scoreNotesTimeline.length === 0) {
    buildPlaybackTimeline();
  }

  if (!state.scoreNotesTimeline || state.scoreNotesTimeline.length === 0) {
    alert("재생할 악보 음표가 준비되지 않았습니다. 악보 렌더링 상태를 확인해 주세요.");
    return;
  }

  await ensureAudioContext();
  state.isPlaying = true;
  dom.btnPlayPause.classList.add("is-playing");
  dom.playIcon.textContent = "⏸";
  dom.playText.textContent = "일시정지";

  const cursor = state.osmd.cursor;
  cursor.show();
  cursor.reset();

  const secondsPerBeat = 60.0 / (state.bpm || 100);
  const startTime = state.audioCtx.currentTime + 0.05;

  // Clear existing timeouts
  state.playbackTimeouts.forEach(t => clearTimeout(t));
  state.playbackTimeouts = [];

  state.scoreNotesTimeline.forEach((event, idx) => {
    const noteTime = startTime + event.accumulatedBeats * secondsPerBeat;
    const delayMs = Math.max(0, (noteTime - state.audioCtx.currentTime) * 1000);

    const timeoutId = setTimeout(() => {
      if (!state.isPlaying) return;

      // 1. 커서 이동 (O(1) 단일 스텝 전진)
      if (idx === 0) {
        cursor.reset();
      } else {
        cursor.next();
      }

      // 2. 음표 사운드 재생 및 가상 건반 애니메이션 (100% 무조건 소리 들림)
      if (event.pitches && event.pitches.length > 0) {
        event.pitches.forEach(pitch => {
          playTone(pitch, Math.max(0.2, event.duration * secondsPerBeat * 0.95));
          highlightPianoKey(pitch, Math.max(180, event.duration * secondsPerBeat * 800));
        });
      }

      // 3. 화면 부드러운 스크롤 추적
      autoScrollToCursor();

      // 마지막 음표 연주 후 정지 처리
      if (idx === state.scoreNotesTimeline.length - 1) {
        setTimeout(() => stopPlayback(), event.duration * secondsPerBeat * 1000);
      }
    }, delayMs);

    state.playbackTimeouts.push(timeoutId);
  });
}

function pausePlayback() {
  state.isPlaying = false;
  state.playbackTimeouts.forEach(t => clearTimeout(t));
  state.playbackTimeouts = [];
  dom.btnPlayPause.classList.remove("is-playing");
  dom.playIcon.textContent = "▶";
  dom.playText.textContent = "재생";
}

function stopPlayback() {
  pausePlayback();
  if (state.osmd && state.osmd.cursor) {
    state.osmd.cursor.reset();
    updateCursorSelection();
  }
}

function autoScrollToCursor() {
  const cursorElement = document.getElementById("cursorImg-0") || document.querySelector(".osmd-cursor") || dom.osmdContainer.querySelector("img");
  if (cursorElement) {
    const viewport = dom.sheetViewport;
    const cursorRect = cursorElement.getBoundingClientRect();
    const viewportRect = viewport.getBoundingClientRect();

    if (cursorRect.bottom > viewportRect.bottom - 40 || cursorRect.top < viewportRect.top + 40) {
      viewport.scrollBy({
        top: cursorRect.top - viewportRect.top - 80,
        behavior: "smooth"
      });
    }
  }
}
