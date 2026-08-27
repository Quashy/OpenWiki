import { heroui } from "@heroui/react";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}", "./node_modules/@heroui/theme/dist/**/*.{js,ts,jsx,tsx}"],
  plugins: [heroui()],
};
