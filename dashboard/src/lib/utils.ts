import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Every panel that floats over the map: the `glass` utility (index.css), clickable through the overlay. */
export function floating(...inputs: ClassValue[]) {
  return cn("glass pointer-events-auto", inputs);
}
