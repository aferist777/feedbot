// Icon names from catalog.json, resolved against lucide.
//
// The catalogue speaks kebab-case because that is what the model is shown and
// what reads well in a JSON file; lucide exports PascalCase. One conversion,
// one table of exceptions, and a null when a name does not resolve — a missing
// icon must never take a frame down with it.

import * as lucide from "lucide-react";
import React from "react";

const EXCEPTIONS: Record<string, string> = {
  // lucide renamed this one; the catalogue keeps the word people actually use
  alert: "TriangleAlert",
};

const pascal = (name: string) =>
  name.split("-").map((part) => part[0].toUpperCase() + part.slice(1)).join("");

export const Icon: React.FC<{
  name: string;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: React.CSSProperties;
}> = ({name, size = 64, color = "currentColor", strokeWidth = 2, style}) => {
  if (!name) return null;
  const key = EXCEPTIONS[name] ?? pascal(name);
  const Glyph = (lucide as unknown as Record<string, React.ElementType>)[key];
  if (!Glyph) return null;
  return <Glyph size={size} color={color} strokeWidth={strokeWidth} style={style} />;
};
