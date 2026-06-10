/// <reference types="vite/client" />

declare module "*?raw" {
  const content: string;
  export default content;
}

declare module "world-atlas/*.json" {
  const topology: unknown;
  export default topology;
}
