// Кинематографичный: one line at a time, and the frame reacts to it.
//
// Where the talk pack lets you read ahead, this one refuses to: only the
// current phrase is on screen. That is what makes a beat land as a beat — the
// cut, the flash and the slow push are doing the work the text is not.

import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {SCENES} from "../scenes";
import {SKINS, type Beat, type Theme} from "../types";

// The phrase being spoken, and only it: words are grouped into lines of a few,
// so the reader always has a whole thought and never a wall.
const phraseAt = (beat: Beat, now: number, per: number) => {
  const groups: typeof beat.words[] = [];
  for (let i = 0; i < beat.words.length; i += per) {
    groups.push(beat.words.slice(i, i + per));
  }
  const live = groups.findIndex(
    (group) => now >= group[0].start && now < group[group.length - 1].end,
  );
  const index = live >= 0 ? live : Math.max(0, groups.findIndex(
    (group) => now < group[0].start,
  ) - 1);
  return {group: groups[index >= 0 ? index : groups.length - 1], index, count: groups.length};
};

export const Cinema: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps + beat.start;

  // Scenes here are stripped of their frames — this pack shows one thing at a
  // time, and a border around it would be one thing too many.
  if (beat.scene !== "line") {
    const Scene = SCENES[beat.scene] ?? SCENES.line;
    const flashIn = Math.max(0, 1 - (now - beat.start) / 0.3);
    return (
      <div style={{width: "100%", position: "relative"}}>
        <div style={{position: "absolute", inset: -60, background: "#ffffff",
          opacity: flashIn * 0.35, mixBlendMode: "screen", pointerEvents: "none"}} />
        <Scene beat={beat} theme={theme} now={now} skin={SKINS.cinema} src={beat.photo} />
      </div>
    );
  }

  const {group, index} = phraseAt(beat, now, 5);
  const text = (group || []).map((word) => word.text).join(" ");
  const since = group ? now - group[0].start : 0;

  // Every new phrase gets a flash and a nudge — the flash covers the cut, the
  // nudge keeps the frame from being static while the voice runs.
  const flash = interpolate(since, [0, 0.08, 0.34], [0.5, 0.16, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const arrive = spring({fps, frame: Math.round(since * fps),
    config: {damping: 18, mass: 0.8}, durationInFrames: Math.round(fps * 0.5)});
  const push = 1 + (now - beat.start) * 0.006; // a slow, barely noticed zoom

  return (
    <div style={{width: "100%", height: "100%", position: "relative",
      display: "flex", alignItems: "center"}}>
      <div style={{
        position: "absolute", inset: -40,
        background: "#ffffff", opacity: flash, mixBlendMode: "screen",
        pointerEvents: "none",
      }} />

      <div style={{
        transform: `scale(${push}) translateY(${(1 - arrive) * 26}px)`,
        opacity: 0.15 + arrive * 0.85,
        width: "100%",
      }}>
        <div style={{
          fontFamily: `"${theme.font}", system-ui, sans-serif`,
          fontSize: theme.fontSize * 1.05,
          fontWeight: 900,
          lineHeight: 1.06,
          letterSpacing: -1,
          color: theme.ink,
          overflowWrap: "break-word",
          textShadow: "0 10px 40px #000000aa",
        }}>
          {text}
        </div>

        <div style={{
          marginTop: 30, height: 3, width: 120,
          background: theme.accent,
          transform: `scaleX(${arrive})`, transformOrigin: "left center",
        }} />
      </div>

      {/* which phrase of the beat this is — a quiet sense of progress */}
      <div style={{
        position: "absolute", right: -18, top: "50%",
        transform: "translateY(-50%)",
        display: "flex", flexDirection: "column", gap: 10,
      }}>
        {Array.from({length: Math.min(8, Math.ceil(beat.words.length / 5))}).map((_, i) => (
          <span key={i} style={{
            width: 6, height: i === index ? 26 : 6, borderRadius: 3,
            background: i === index ? theme.accent : theme.dim,
          }} />
        ))}
      </div>
    </div>
  );
};
