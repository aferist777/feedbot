// Мультяшный: the words behave like drawings.
//
// Everything here is drawn in code rather than pulled from an icon pack: the
// wobble, the marker underline, the speech bubble. Nothing to download, no
// licence to track, and it stays sharp at 1080x1920.

import React from "react";
import {interpolate, random, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {SCENES} from "../scenes";
import {SKINS, type Beat, type Theme} from "../types";

const bare = (text: string) => text.toLowerCase().replace(/[^\wа-яё-]/gi, "");

// Which words make up the beat's key phrase. Marking the phrase where it is
// said beats drawing a line at the bottom of the card: the mark then means
// something instead of being decoration.
const keyRange = (beat: Beat): Set<number> => {
  const phrase = (beat.keys[0] || "").split(/\s+/).map(bare).filter(Boolean);
  const marked = new Set<number>();
  if (!phrase.length) return marked;
  const words = beat.words.map((word) => bare(word.text));
  for (let start = 0; start + phrase.length <= words.length; start++) {
    if (phrase.every((token, offset) => words[start + offset] === token)) {
      phrase.forEach((_, offset) => marked.add(start + offset));
      break;
    }
  }
  return marked;
};

export const Toon: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps + beat.start;

  // Scenes come dressed as paper: white cards, thick outline, slight tilt.
  if (beat.scene !== "line") {
    const Scene = SCENES[beat.scene] ?? SCENES.line;
    return <Scene beat={beat} theme={theme} now={now} skin={SKINS.toon} src={beat.photo} />;
  }

  const marked = keyRange(beat);
  const bulk = beat.words.reduce((sum, word) => sum + word.text.length + 1, 0);
  const size = Math.max(theme.fontSize * 0.5,
    Math.min(theme.fontSize * 0.95, theme.fontSize * (130 / Math.max(bulk, 40))));

  const bubble = spring({fps, frame, config: {damping: 11, mass: 0.7}});

  return (
    <div style={{
      width: "100%",
      background: "#ffffff",
      borderRadius: 34,
      padding: "40px 38px 46px",
      // The whole bubble arrives with a bounce and sits very slightly askew,
      // which is what keeps it from reading as a plain white card.
      transform: `scale(${0.9 + bubble * 0.1}) rotate(${(1 - bubble) * -2}deg)`,
      boxShadow: `14px 16px 0 ${theme.accent}`,
      border: "5px solid #1d2027",
      position: "relative",
    }}>
      <div style={{display: "flex", flexWrap: "wrap", alignItems: "flex-end",
        gap: `${size * 0.16}px ${size * 0.26}px`, minWidth: 0, overflow: "hidden"}}>
        {beat.words.map((word, index) => {
          const live = now >= word.start && now < word.end;
          const said = now >= word.start;
          // Seeded per word, so the wobble is different everywhere but the
          // same on every re-render of this reel.
          const tilt = (random(`${beat.index}-${index}`) - 0.5) * 6;
          const pop = spring({
            fps, frame: frame - (word.start - beat.start) * fps,
            config: {damping: 9, mass: 0.5},
            durationInFrames: Math.max(1, Math.round(theme.wordEnter * fps)),
          });
          // The highlight sweeps in behind the word as it is spoken, the way
          // a marker is dragged across a line rather than switched on.
          const swept = marked.has(index) && said
            ? Math.min(1, (now - word.start) / 0.28)
            : 0;
          return (
            <span key={index} style={{
              fontFamily: `"${theme.font}", system-ui, sans-serif`,
              fontSize: size,
              fontWeight: 900,
              lineHeight: 1.05,
              color: said ? "#1d2027" : "#c9ccd3",
              transform: `rotate(${tilt}deg) scale(${said ? 0.85 + pop * 0.15 : 0.85})`
                + `${live ? " translateY(-6px)" : ""}`,
              transformOrigin: "bottom center",
              display: "inline-block",
              position: "relative",
              overflowWrap: "break-word",
              maxWidth: "100%",
              padding: marked.has(index) ? "0 6px" : undefined,
            }}>
              {swept > 0 ? (
                <span style={{
                  position: "absolute", left: 0, right: 0,
                  bottom: size * 0.04, height: size * 0.42,
                  background: theme.accent,
                  opacity: 0.55,
                  borderRadius: 4,
                  transform: `scaleX(${swept})`,
                  transformOrigin: "left center",
                  zIndex: -1,
                }} />
              ) : null}
              {word.text}
            </span>
          );
        })}
      </div>

      {/* the tail of the speech bubble */}
      <div style={{
        position: "absolute", bottom: -34, left: 64,
        width: 0, height: 0,
        borderLeft: "34px solid transparent",
        borderRight: "12px solid transparent",
        borderTop: "36px solid #1d2027",
      }} />
    </div>
  );
};
