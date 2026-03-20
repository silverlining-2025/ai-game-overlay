export interface AppConfig {
  game: "maplestory" | "palworld" | "general";
  character: "nozomi" | "robot" | "cat" | "ghost" | "fox" | "slime";
  interval: number;
  position: "top-right" | "top-left" | "bottom-right" | "bottom-left";
  chattiness: number;
  locale: "ko" | "en";
  tier?: "free" | "basic" | "pro" | "streamer";
  apiMode?: "managed" | "byok";
}

export interface CompanionReaction {
  text: string;
  face: string;
  mood: "excited" | "curious" | "worried" | "chill" | "amused" | "thinking";
  cycle: number;
  elapsedMs: number;
  costEstimate: string;
}
