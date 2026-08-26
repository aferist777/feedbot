// The contract between the Python side and this one. Everything the reel needs
// arrives as props: no file reading, no fetching, nothing to guess.

export type Word = {
  text: string;
  start: number; // seconds, already divided by tempo
  end: number;
};

export type Beat = {
  index: number;
  start: number;
  end: number;
  on_screen: string;
  keys: string[];
  scene: string;      // which scene the model asked for, already validated
  icon: string;       // a name from catalog.json, or empty
  items: string[];    // the scene's contents, already trimmed to five
  photo?: string;     // file name in public/, when the post carried an image
  words: Word[];
};

export type Theme = {
  bg: string;
  ink: string;      // text that has been spoken
  dim: string;      // text not yet reached
  accent: string;   // the word being spoken right now
  font: string;
  fontSize: number;
  captionSize: number;
  safeTop: number;    // room for the platform's own interface
  safeBottom: number;
  showCaption: boolean;
  wordEnter: number;  // seconds a word takes to arrive
  background: "flat" | "gradient" | "vignette";
};

// How a pack dresses the shared scenes. Eight scenes times five packs would be
// forty components; eight scenes plus five skins is thirteen, and they cannot
// drift apart.
export type Skin = {
  mono: boolean;        // monospace type — machines and logs
  card: "outline" | "solid" | "paper" | "bare";
  radius: number;
  tilt: number;         // degrees, for things that should look hand-placed
  weight: number;       // font weight of scene text
  icons: boolean;       // whether icons are drawn at all
  scale: number;        // multiplies every text size in the scene
  ink: string;          // text colour inside cards (paper needs a dark one)
};

export const SKINS: Record<string, Skin> = {
  talk:    {mono: false, card: "outline", radius: 14, tilt: 0, weight: 700,
            icons: true, scale: 1, ink: ""},
  tech:    {mono: true, card: "outline", radius: 12, tilt: 0, weight: 700,
            icons: true, scale: 1, ink: ""},
  numbers: {mono: false, card: "solid", radius: 16, tilt: 0, weight: 800,
            icons: true, scale: 1.08, ink: ""},
  toon:    {mono: false, card: "paper", radius: 26, tilt: -1.5, weight: 900,
            icons: true, scale: 1, ink: "#1d2027"},
  cinema:  {mono: false, card: "bare", radius: 0, tilt: 0, weight: 900,
            icons: false, scale: 1.12, ink: ""},
};

export type ReelProps = {
  pack: string;
  theme: Theme;
  beats: Beat[];
  audio: {file: string; tempo: number; seconds: number} | null;
  fps: number;
  width: number;
  height: number;
};

export const DEFAULT_THEME: Theme = {
  bg: "#14161a",
  ink: "#e6e9ee",
  dim: "#3a3f48",
  accent: "#d8a657",
  font: "Segoe UI",
  fontSize: 84,
  captionSize: 44,
  safeTop: 260,
  safeBottom: 340,
  showCaption: true,
  wordEnter: 0.22,
  background: "gradient",
};

export const DEFAULT_PROPS: ReelProps = {
  pack: "talk",
  theme: DEFAULT_THEME,
  beats: [],
  audio: null,
  fps: 30,
  width: 1080,
  height: 1920,
};
