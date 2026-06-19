import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        alpine: {
          50:  "#f0f7f4",
          100: "#dceee6",
          500: "#2d6a4f",
          700: "#1b4332",
          900: "#081c10",
        },
      },
    },
  },
  plugins: [],
};

export default config;
