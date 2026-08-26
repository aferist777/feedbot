// Цифры: the number is the picture.
//
// Posts that carry a figure — five thousand stars, forty minutes of CI, sixty
// dollars — lose it when it is read out loud in the middle of a sentence. Here
// the figure is pulled out of the beat and counted up on screen while the
// sentence carries on underneath.

import React from "react";
import {interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {SCENES} from "../scenes";
import {SKINS, type Beat, type Theme} from "../types";

// Digits first, because the caption is written for the eye; the voice-over
// spells numbers out in words on purpose, so it is the worse source.
const DIGITS = /(\d[\d\s.,]*)\s*([a-zA-Zа-яА-Я%$₽+kKмМ]*)/;

type Figure = {value: number; suffix: string; raw: string};

const findFigure = (beat: Beat): Figure | null => {
  for (const text of [beat.on_screen, beat.words.map((w) => w.text).join(" ")]) {
    const hit = DIGITS.exec(text || "");
    if (!hit) continue;
    const clean = hit[1].replace(/\s/g, "").replace(",", ".");
    const value = parseFloat(clean);
    if (!Number.isFinite(value)) continue;
    return {value, suffix: (hit[2] || "").slice(0, 6), raw: hit[1].trim()};
  }
  return null;
};

const format = (value: number, target: number) => {
  const decimals = String(target).includes(".") ? 1 : 0;
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

export const Numbers: React.FC<{beat: Beat; theme: Theme}> = ({beat, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps + beat.start;
  const figure = findFigure(beat);

  // A beat that named its own scene gets it — stat is this pack's own scene
  // anyway, and the rest arrive with numbers already inside them.
  if (beat.scene !== "line" && beat.scene !== "stat") {
    const Scene = SCENES[beat.scene] ?? SCENES.line;
    return <Scene beat={beat} theme={theme} now={now} skin={SKINS.numbers} src={beat.photo} />;
  }

  // The count runs over the first second and a bit, then holds — long enough
  // to read, short enough not to become the whole beat.
  const roll = spring({fps, frame, config: {damping: 30, mass: 1.2},
    durationInFrames: Math.round(fps * 1.1)});
  const shown = figure ? figure.value * roll : 0;

  const said = beat.words.filter((word) => now >= word.start).map((w) => w.text).join(" ");
  const rest = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <div style={{width: "100%", minWidth: 0, overflow: "hidden", display: "flex",
      flexDirection: "column", alignItems: "flex-start", gap: 28}}>
      {figure ? (
        <div style={{display: "flex", alignItems: "baseline", gap: 12}}>
          <span style={{
            fontFamily: `"${theme.font}", system-ui, sans-serif`,
            fontSize: theme.fontSize * 2.1,
            fontWeight: 900,
            lineHeight: 0.95,
            color: theme.accent,
            fontVariantNumeric: "tabular-nums",
            letterSpacing: -2,
          }}>
            {format(shown, figure.value)}
          </span>
          {figure.suffix ? (
            <span style={{
              fontFamily: `"${theme.font}", system-ui, sans-serif`,
              fontSize: theme.fontSize * 0.9, fontWeight: 800, color: theme.ink,
            }}>
              {figure.suffix}
            </span>
          ) : null}
        </div>
      ) : (
        // No figure in this beat: the line itself becomes the headline, so the
        // pack never renders an empty frame.
        <div style={{
          fontFamily: `"${theme.font}", system-ui, sans-serif`,
          fontSize: theme.fontSize * 0.95, fontWeight: 800, color: theme.ink,
          lineHeight: 1.15,
        }}>
          {beat.on_screen}
        </div>
      )}

      <div style={{height: 4, width: `${Math.round(roll * 100)}%`,
        background: theme.accent, opacity: 0.5, borderRadius: 2}} />

      <div style={{
        fontFamily: `"${theme.font}", system-ui, sans-serif`,
        fontSize: theme.fontSize * 0.5,
        fontWeight: 500,
        lineHeight: 1.35,
        color: theme.ink,
        overflowWrap: "break-word",
        maxWidth: "100%",
        opacity: rest * 0.92,
      }}>
        {said}
      </div>
    </div>
  );
};
