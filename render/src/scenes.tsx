// The scenes the model can ask for, drawn once and shared by every pack.
//
// Each takes the same three things — the beat, the theme, and where we are in
// it — so a pack decides how a scene is dressed, not what it is. Nothing here
// reads a file or fetches anything: props in, pixels out.

import React from "react";
import {Illustration, hasArt} from "./art";
import {Icon} from "./icons";
import {density, overshoot} from "./motion";
import {SKINS, type Beat, type Skin, type Theme} from "./types";

type SceneProps = {beat: Beat; theme: Theme; now: number; skin?: Skin; src?: string};

const font = (theme: Theme, skin: Skin) =>
  skin.mono ? '"Cascadia Mono", Consolas, monospace'
            : `"${theme.font}", system-ui, sans-serif`;

const of = (skin?: Skin) => skin ?? SKINS.talk;

// One card, dressed four ways. Everything that differs between packs lives
// here rather than in five copies of every scene.
const card = (theme: Theme, skin: Skin, hot: boolean): React.CSSProperties => {
  const common: React.CSSProperties = {
    borderRadius: skin.radius,
    transform: skin.tilt ? `rotate(${skin.tilt}deg)` : undefined,
  };
  if (skin.card === "bare") return {...common, padding: 0, minWidth: 0};
  if (skin.card === "paper") {
    return {
      ...common,
      background: "#ffffff",
      minWidth: 0,
      border: "4px solid #1d2027",
      boxShadow: `10px 12px 0 ${hot ? theme.accent : "#1d2027"}`,
      padding: "22px 24px",
    };
  }
  if (skin.card === "solid") {
    return {
      ...common,
      minWidth: 0,
      background: hot ? `${theme.accent}22` : "#ffffff0a",
      border: `1px solid ${hot ? theme.accent : theme.dim}`,
      padding: "24px 26px",
    };
  }
  return {
    ...common,
    minWidth: 0,
    background: hot ? `${theme.accent}18` : "#00000030",
    border: `2px solid ${hot ? theme.accent : theme.dim}`,
    padding: "20px 24px",
  };
};

const inkOf = (theme: Theme, skin: Skin) => skin.ink || theme.ink;

// Ordinary prose breaks between words, and only splits one if it is longer
// than the line itself — "anywhere" would chop «беременность» in half to save
// four pixels, which reads worse than a ragged edge.
const WRAP: React.CSSProperties = {
  overflowWrap: "break-word",
  minWidth: 0,
  maxWidth: "100%",
};

// Logs and error text are a different case: they really do contain single
// tokens longer than the frame — URLs, image digests, compose keys.
const WRAP_HARD: React.CSSProperties = {
  overflowWrap: "anywhere",
  wordBreak: "break-word",
  minWidth: 0,
  maxWidth: "100%",
};
const dimOf = (theme: Theme, skin: Skin) => (skin.ink ? "#8b8f98" : theme.dim);

// Shrink to fit. Five items of two lines each will not fit however hard they
// wrap, so the type gets smaller as the scene gets fuller — the same trick the
// talk pack uses on long beats, applied to every scene that takes items.
const fitScale = (items: string[], perLine = 26) => {
  const lines = items.reduce(
    (sum, item) => sum + Math.max(1, Math.ceil(item.length / perLine)), 0,
  );
  if (lines <= 4) return 1;
  return Math.max(0.62, 1 - (lines - 4) * 0.09);
};

// How far into the beat an item should be, spread over the words it covers:
// item three of five appears when the voice is three fifths through.
const itemProgress = (beat: Beat, now: number, index: number, total: number) => {
  const span = Math.max(0.2, beat.end - beat.start);
  const at = beat.start + (span * index) / Math.max(total, 1);
  return Math.max(0, Math.min(1, (now - at) / 0.45));
};

// ------------------------------------------------------------------- line

export const Line: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const {pulse} = density(now, beat.start, beat.words.map((w) => w.start));
  return (
    <div style={{display: "flex", alignItems: "center", gap: 28, width: "100%"}}>
      {beat.icon && s.icons ? (
        <div style={{
          flex: "none", opacity: 0.9,
          transform: `scale(${1 + pulse * 0.06})`,
        }}>
          <Icon name={beat.icon} size={theme.fontSize * 1.5} color={theme.accent}
            strokeWidth={1.6} />
        </div>
      ) : null}
      <div style={{
        fontFamily: font(theme, s), fontSize: theme.fontSize * 0.92 * s.scale,
        fontWeight: s.weight, lineHeight: 1.12, color: theme.ink, ...WRAP,
      }}>
        {beat.on_screen}
      </div>
    </div>
  );
};

// -------------------------------------------------------------------- log

export const Log: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const fit = fitScale(beat.items, 30);
  return (
  <div style={{
    width: "100%", background: "#0f1115", border: `1px solid ${theme.dim}`,
    borderRadius: 14, overflow: "hidden", boxShadow: "0 18px 44px #00000055",
  }}>
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
      borderBottom: `1px solid ${theme.dim}`, background: "#151920",
    }}>
      {["#e06c63", "#e0b463", "#7fb069"].map((dot) => (
        <span key={dot} style={{width: 11, height: 11, borderRadius: "50%", background: dot}} />
      ))}
      <span style={{fontFamily: font(theme, {...of(skin), mono: true}), fontSize: theme.captionSize * 0.6,
        color: theme.dim, marginLeft: 10}}>
        {beat.on_screen}
      </span>
    </div>
    <div style={{padding: "20px 18px", display: "flex", flexDirection: "column", gap: 10}}>
      {beat.items.map((item, index) => {
        const shown = itemProgress(beat, now, index, beat.items.length);
        return (
          <div key={index} style={{
            ...WRAP_HARD,
            fontFamily: font(theme, {...of(skin), mono: true}),
            fontSize: theme.fontSize * 0.5 * of(skin).scale * fit,
            color: index === beat.items.length - 1 ? theme.accent : theme.ink,
            opacity: shown, transform: `translateX(${(1 - shown) * -12}px)`,
          }}>
            <span style={{color: theme.dim}}>{String(index + 1).padStart(2, "0")} </span>
            {item}
          </div>
        );
      })}
    </div>
  </div>
  );
};

// ------------------------------------------------------------------- flow

export const Flow: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const fit = fitScale(beat.items);
  return (
    <div style={{display: "flex", flexDirection: "column", gap: 18, width: "100%"}}>
      {beat.items.map((item, index) => {
        const shown = itemProgress(beat, now, index, beat.items.length);
        const last = index === beat.items.length - 1;
        return (
          <div key={index} style={{opacity: shown,
            transform: `translateY(${(1 - overshoot(shown)) * 26}px)`}}>
            <div style={{display: "flex", alignItems: "center", gap: 16,
              ...card(theme, s, last)}}>
              {index === 0 && beat.icon && s.icons ? (
                <Icon name={beat.icon} size={theme.fontSize * 0.9}
                  color={s.ink ? "#1d2027" : theme.accent} />
              ) : null}
              <span style={{fontFamily: font(theme, s),
                fontSize: theme.fontSize * 0.68 * s.scale * fit,
                fontWeight: s.weight, color: inkOf(theme, s), ...WRAP}}>
                {item}
              </span>
            </div>
            {!last ? (
              <div style={{color: theme.accent, fontSize: theme.fontSize * 0.5,
                textAlign: "center", lineHeight: 1, marginTop: 4}}>↓</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

// ------------------------------------------------------------------ stack

export const Stack: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const fit = fitScale(beat.items);
  const live = beat.items.findIndex(
    (_, index) => itemProgress(beat, now, index, beat.items.length) > 0
      && itemProgress(beat, now, index + 1, beat.items.length) === 0,
  );
  return (
    <div style={{display: "flex", flexDirection: "column", gap: 14, width: "100%"}}>
      {beat.items.map((item, index) => {
        const shown = itemProgress(beat, now, index, beat.items.length);
        const current = index === live;
        return (
          <div key={index} style={{
            display: "flex", alignItems: "center", gap: 18,
            opacity: 0.25 + shown * 0.75,
            transform: `translateX(${(1 - shown) * -20}px) scale(${current ? 1.02 : 1})`,
            transformOrigin: "left center",
          }}>
            <span style={{
              flex: "none", width: 56 * fit, height: 56 * fit, borderRadius: s.radius * 0.7,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: current ? theme.accent : "transparent",
              border: `2px solid ${current ? theme.accent : dimOf(theme, s)}`,
              color: current ? (s.ink || theme.bg) : dimOf(theme, s),
              fontFamily: font(theme, s), fontSize: 27 * fit, fontWeight: 800,
              transform: s.tilt ? `rotate(${s.tilt * 2}deg)` : undefined,
            }}>
              {index + 1}
            </span>
            <span style={{
              fontFamily: font(theme, s), fontSize: theme.fontSize * 0.68 * s.scale * fit,
              fontWeight: s.weight, ...WRAP,
              color: current ? inkOf(theme, s) : dimOf(theme, s), lineHeight: 1.2,
            }}>
              {item}
            </span>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- compare

export const Compare: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  // Two columns means half the width each, so it crowds twice as fast.
  const fit = fitScale(beat.items, 14);
  const left = itemProgress(beat, now, 0, 2);
  const right = itemProgress(beat, now, 1, 2);
  const cell = (text: string, shown: number, hot: boolean) => (
    <div style={{
      flex: 1, ...card(theme, s, hot),
      opacity: shown,
      transform: `${card(theme, s, hot).transform || ""} scale(${0.94 + shown * 0.06})`,
    }}>
      <div style={{fontFamily: font(theme, s), fontSize: theme.captionSize * 0.62,
        color: dimOf(theme, s), marginBottom: 10, letterSpacing: 1}}>
        {hot ? "СТАЛО" : "БЫЛО"}
      </div>
      <div style={{fontFamily: font(theme, s), fontSize: theme.fontSize * 0.72 * s.scale * fit,
        fontWeight: s.weight, color: inkOf(theme, s), lineHeight: 1.15, ...WRAP}}>
        {text}
      </div>
    </div>
  );
  return (
    <div style={{display: "flex", alignItems: "stretch", gap: 16, width: "100%"}}>
      {cell(beat.items[0] || "", left, false)}
      <div style={{alignSelf: "center", color: theme.accent,
        fontSize: theme.fontSize * 0.7, opacity: right}}>→</div>
      {cell(beat.items[1] || "", right, true)}
    </div>
  );
};

// ------------------------------------------------------------------- stat

export const Stat: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const digits = (beat.items[0] || beat.on_screen || "").match(/[\d.,\s]+/);
  const target = parseFloat((digits ? digits[0] : "").replace(/\s/g, "").replace(",", "."));
  const t = Math.max(0, Math.min(1, (now - beat.start) / 1.1));
  const value = Number.isFinite(target) ? target * overshoot(t) : null;
  const caption = beat.items[1] || beat.on_screen;

  return (
    <div style={{width: "100%", display: "flex", alignItems: "center", gap: 26}}>
      {beat.icon && s.icons ? (
        <Icon name={beat.icon} size={theme.fontSize * 1.6} color={theme.accent}
          strokeWidth={1.6} />
      ) : null}
      <div>
        <div style={{
          fontFamily: font(theme, s), fontSize: theme.fontSize * 1.9 * s.scale, fontWeight: 900,
          color: theme.accent, lineHeight: 0.95, letterSpacing: -2,
          fontVariantNumeric: "tabular-nums",
        }}>
          {value === null ? (beat.items[0] || "") : Math.round(value).toLocaleString("ru-RU")}
        </div>
        <div style={{fontFamily: font(theme, s), fontSize: theme.fontSize * 0.5 * s.scale,
          color: theme.ink, marginTop: 10, opacity: t}}>
          {caption}
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ alert

export const Alert: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const {event} = density(now, beat.start, beat.words.map((w) => w.start));
  const bad = "#d16b6b";
  return (
    <div style={{
      width: "100%", padding: "30px 26px", borderRadius: 14,
      border: `2px solid ${bad}`, background: `${bad}14`,
      transform: `translateX(${Math.sin(now * 30) * event * 4}px)`,
    }}>
      <div style={{display: "flex", alignItems: "center", gap: 16}}>
        <Icon name="alert" size={theme.fontSize * 0.9} color={bad} strokeWidth={2.2} />
        <span style={{fontFamily: font(theme, s), fontSize: theme.captionSize * 0.7,
          color: bad, letterSpacing: 1, fontWeight: 700}}>
          {beat.on_screen}
        </span>
      </div>
      <div style={{
        ...WRAP_HARD,
        fontFamily: font(theme, {...s, mono: true}), fontSize: theme.fontSize * 0.52 * s.scale,
        color: theme.ink, marginTop: 16, lineHeight: 1.35,
      }}>
        {beat.items[0] || ""}
      </div>
    </div>
  );
};

// -------------------------------------------------------------------- art

export const ArtScene: React.FC<SceneProps> = ({beat, theme, now, skin}) => {
  const s = of(skin);
  const t = Math.max(0, Math.min(1, (now - beat.start) / 0.7));
  // No illustration for this icon: the line scene says the same thing without
  // pretending there is a picture.
  if (!hasArt(beat.icon)) return <Line beat={beat} theme={theme} now={now} skin={skin} />;
  return (
    <div style={{width: "100%", display: "flex", flexDirection: "column",
      alignItems: "center", gap: 26}}>
      <div style={{
        width: "100%",
        opacity: t,
        // Arrives with a small rise and keeps drifting, so a still drawing is
        // not a still frame.
        transform: `translateY(${(1 - overshoot(t)) * 30}px) `
          + `scale(${1 + Math.sin((now - beat.start) * 0.6) * 0.012})`,
      }}>
        <Illustration icon={beat.icon} theme={theme} height={640} />
      </div>
      <div style={{
        fontFamily: font(theme, s), fontSize: theme.fontSize * 0.62 * s.scale,
        fontWeight: s.weight, color: theme.ink, textAlign: "center", opacity: t, ...WRAP,
      }}>
        {beat.items[0] || beat.on_screen}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ photo

export const Photo: React.FC<SceneProps> = ({beat, theme, now, src, skin}) => {
  const s = of(skin);
  const t = Math.max(0, Math.min(1, (now - beat.start) / 0.6));
  // No picture came with the post: fall back rather than show a hole.
  if (!src) return <Line beat={beat} theme={theme} now={now} skin={skin} />;
  return (
    <div style={{width: "100%", opacity: t}}>
      <img src={src} style={{
        width: "100%", maxHeight: 900, objectFit: "cover", borderRadius: 14,
        // A slow push, so a still photograph is not a still frame.
        transform: `scale(${1.02 + (now - beat.start) * 0.004})`,
        border: s.card === "paper" ? "4px solid #1d2027" : `1px solid ${theme.dim}`,
      }} />
      <div style={{fontFamily: font(theme, s), fontSize: theme.captionSize * 0.8,
        color: theme.dim, marginTop: 12}}>
        {beat.items[0] || beat.on_screen}
      </div>
    </div>
  );
};

export const SCENES: Record<string, React.FC<SceneProps>> = {
  line: Line, art: ArtScene, log: Log, flow: Flow, stack: Stack,
  compare: Compare, stat: Stat, alert: Alert, photo: Photo,
};
