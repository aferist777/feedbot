// Разговорный: the words themselves are the picture.
//
// Every word of the beat is on screen at once, so the eye can read ahead — but
// only what has been said is lit, and the word being spoken right now carries
// the accent. That is what makes it read as speech rather than as a subtitle.

import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {SCENES} from "../scenes";
import {SKINS, type Beat, type Theme} from "../types";

export const Talk: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps + beat.start; // frames are relative to the sequence

  // When the beat has something to show, show it — and keep the spoken words
  // running underneath, small, because that is what this pack is for.
  if (beat.scene !== "line") {
    const Scene = SCENES[beat.scene] ?? SCENES.line;
    // Only the last few words: the whole beat in small type is unreadable
    // anyway, and it was what ran past the right edge of the frame.
    const said = beat.words.filter((word) => now >= word.start).slice(-9);
    return (
      <div style={{width: "100%", minWidth: 0, display: "flex",
        flexDirection: "column", gap: 30, overflow: "hidden"}}>
        <Scene beat={beat} theme={theme} now={now} skin={SKINS.talk} src={beat.photo} />
        <div style={{
          fontFamily: `"${theme.font}", system-ui, sans-serif`,
          fontSize: theme.fontSize * 0.42, lineHeight: 1.3, color: theme.dim,
          overflowWrap: "break-word", maxWidth: "100%",
        }}>
          {/* A real space between the words, not a margin: without one the
              line is a single unbroken inline run, and the browser has to
              split a word to wrap it at all. */}
          {said.map((word, index) => (
            <React.Fragment key={index}>
              <span style={{color: now < word.end ? theme.accent : theme.ink}}>
                {word.text}
              </span>
              {index < said.length - 1 ? " " : null}
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  }

  // Long beats need smaller type or they run off the frame. Counted in
  // characters rather than words: "самостоятельный" is not one word wide.
  const bulk = beat.words.reduce((sum, word) => sum + word.text.length + 1, 0);
  const size = Math.max(
    theme.fontSize * 0.55,
    Math.min(theme.fontSize, theme.fontSize * (150 / Math.max(bulk, 40))),
  );

  return (
    <div style={{display: "flex", flexWrap: "wrap", alignContent: "center",
      gap: `${size * 0.22}px ${size * 0.28}px`, width: "100%", height: "100%",
      minWidth: 0, overflow: "hidden"}}>
      {beat.words.map((word, index) => {
        const said = now >= word.start;
        const live = now >= word.start && now < word.end;
        const enter = spring({
          fps,
          frame: frame - (word.start - beat.start) * fps,
          config: {damping: 16, mass: 0.6},
          durationInFrames: Math.max(1, Math.round(theme.wordEnter * fps)),
        });
        return (
          <span
            key={index}
            style={{
              fontFamily: `"${theme.font}", system-ui, sans-serif`,
              fontSize: size,
              fontWeight: 800,
              lineHeight: 1.1,
              overflowWrap: "break-word",
              maxWidth: "100%",
              color: live ? theme.accent : said ? theme.ink : theme.dim,
              opacity: said ? 1 : 0.3,
              transform: `translateY(${(1 - (said ? enter : 0)) * size * 0.45}px) `
                + `scale(${live ? 1.05 : 1})`,
              transformOrigin: "center bottom",
            }}
          >
            {word.text}
          </span>
        );
      })}
    </div>
  );
};

// The line that has to work with the sound off.
export const Caption: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (!theme.showCaption || !beat.on_screen) return null;
  return (
    <div style={{
      fontFamily: `"${theme.font}", system-ui, sans-serif`,
      fontSize: theme.captionSize,
      fontWeight: 600,
      color: theme.accent,
      opacity: appear,
      transform: `translateY(${(1 - appear) * 14}px)`,
      letterSpacing: 0.4,
    }}>
      {beat.on_screen}
    </div>
  );
};
