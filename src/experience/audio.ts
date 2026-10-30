import type { PieceType } from "../chess/pieces"

export type AudioCue = PieceType | "capture" | "check" | "mate"
type Strike = {
  frequency: number
  duration: number
  level: number
  delay?: number
  noise?: number
}

/** Original synthesized wood/percussion voices; no recordings or external audio. */
export const PIECE_VOICES: Record<PieceType, Strike[]> = {
  Tướng: [{ frequency: 110, duration: 0.24, level: 0.7, noise: 0.18 }],
  Sĩ: [{ frequency: 940, duration: 0.07, level: 0.2, noise: 0.08 }],
  Tượng: [{ frequency: 270, duration: 0.18, level: 0.35, noise: 0.1 }],
  Mã: [
    { frequency: 390, duration: 0.09, level: 0.4, noise: 0.22 },
    { frequency: 310, duration: 0.11, level: 0.36, delay: 0.1, noise: 0.2 },
  ],
  Xe: [
    { frequency: 580, duration: 0.16, level: 0.2, noise: 0.5 },
    { frequency: 180, duration: 0.12, level: 0.5, delay: 0.09, noise: 0.2 },
  ],
  Pháo: [{ frequency: 155, duration: 0.11, level: 0.7, noise: 0.7 }],
  Tốt: [{ frequency: 720, duration: 0.065, level: 0.28, noise: 0.12 }],
}

export class ChessAudio {
  private context: AudioContext | null = null
  private master: GainNode | null = null
  private sources = new Set<AudioScheduledSourceNode>()
  private enabled = false
  private volume = 0.35
  private quiet = true

  configure(volume: number, quiet: boolean) {
    this.volume = Math.max(0, Math.min(1, volume))
    this.quiet = quiet
    if (this.context && this.master) {
      this.master.gain.setTargetAtTime(
        this.enabled ? this.gain : 0,
        this.context.currentTime,
        0.025,
      )
    }
  }

  private get gain() {
    return this.volume * (this.quiet ? 0.14 : 0.3)
  }

  async enable() {
    if (!window.AudioContext)
      throw new Error("Trình duyệt này chưa hỗ trợ âm thanh Web Audio.")
    if (!this.context || this.context.state === "closed") {
      this.context = new AudioContext()
      this.master = this.context.createGain()
      this.master.connect(this.context.destination)
    }
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(
        () =>
          reject(
            new Error(
              "Trình duyệt chưa cho phát âm thanh. Hãy bấm bật lại để tiếp tục.",
            ),
          ),
        2000,
      )
      this.context!.resume().then(
        () => {
          clearTimeout(timer)
          resolve()
        },
        (error) => {
          clearTimeout(timer)
          reject(error)
        },
      )
    })
    if (this.context.state !== "running")
      throw new Error(
        "Chưa thể bật âm thanh. Hãy bấm bật lại trong trình duyệt.",
      )
    this.enabled = true
    this.master!.gain.setValueAtTime(this.gain, this.context.currentTime)
  }

  mute() {
    this.enabled = false
    this.stop()
    if (this.master && this.context)
      this.master.gain.setValueAtTime(0, this.context.currentTime)
  }

  stop() {
    this.sources.forEach((source) => {
      try {
        source.stop()
      } catch {
        /* Already ended. */
      }
    })
    this.sources.clear()
  }

  dispose() {
    this.mute()
    void this.context?.close()
    this.context = null
    this.master = null
  }

  playMove(type: PieceType, captured = false) {
    this.play(type)
    if (captured) this.play("capture", 0.12)
  }

  play(cue: AudioCue, delay = 0) {
    const context = this.context
    if (
      !this.enabled ||
      !context ||
      context.state !== "running" ||
      this.volume === 0 ||
      document.hidden
    )
      return
    const at = context.currentTime + delay
    if (cue in PIECE_VOICES) {
      PIECE_VOICES[(cue as PieceType)].forEach((strike) =>
        this.strike(strike, at),
      )
    } else if (cue === "capture") {
      this.strike(
        { frequency: 230, duration: 0.14, level: 0.65, noise: 0.4 },
        at,
      )
      this.strike(
        { frequency: 125, duration: 0.16, level: 0.35, delay: 0.065 },
        at,
      )
    } else if (cue === "check") {
      this.strike({ frequency: 490, duration: 0.19, level: 0.38 }, at)
      this.strike(
        { frequency: 660, duration: 0.24, level: 0.32, delay: 0.15 },
        at,
      )
    } else {
      ;[330, 440, 550, 660].forEach((frequency, i) =>
        this.strike(
          { frequency, duration: 0.45, level: 0.24, delay: i * 0.12 },
          at,
        ),
      )
      this.strike(
        { frequency: 110, duration: 0.6, level: 0.3, noise: 0.05 },
        at,
      )
    }
  }

  private strike(strike: Strike, start: number) {
    const context = this.context!
    const at = start + (strike.delay || 0)
    const duration = this.quiet ? strike.duration * 0.8 : strike.duration
    const envelope = context.createGain()
    envelope.connect(this.master!)
    envelope.gain.setValueAtTime(0.0001, at)
    envelope.gain.exponentialRampToValueAtTime(
      Math.max(0.0002, strike.level),
      at + 0.006,
    )
    envelope.gain.exponentialRampToValueAtTime(0.0001, at + duration)
    const oscillator = context.createOscillator()
    oscillator.type = "sine"
    oscillator.frequency.setValueAtTime(strike.frequency * 1.2, at)
    oscillator.frequency.exponentialRampToValueAtTime(
      strike.frequency,
      at + 0.04,
    )
    oscillator.connect(envelope)
    this.sources.add(oscillator)
    oscillator.onended = () => {
      oscillator.disconnect()
      envelope.disconnect()
      this.sources.delete(oscillator)
    }
    oscillator.start(at)
    oscillator.stop(at + duration + 0.02)
    if (strike.noise && !this.quiet) {
      const buffer = context.createBuffer(
        1,
        Math.ceil(context.sampleRate * duration),
        context.sampleRate,
      )
      const values = buffer.getChannelData(0)
      for (let i = 0; i < values.length; i++)
        values[i] = (Math.random() * 2 - 1) * Math.exp((-i / values.length) * 7)
      const noise = context.createBufferSource()
      const filter = context.createBiquadFilter()
      const gain = context.createGain()
      noise.buffer = buffer
      filter.type = "bandpass"
      filter.frequency.value = strike.frequency * 3
      filter.Q.value = 1.2
      gain.gain.value = strike.noise * 0.35
      noise.connect(filter).connect(gain).connect(this.master!)
      this.sources.add(noise)
      noise.onended = () => {
        noise.disconnect()
        filter.disconnect()
        gain.disconnect()
        this.sources.delete(noise)
      }
      noise.start(at)
      noise.stop(at + duration)
    }
  }
}
