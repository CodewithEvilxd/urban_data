module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        heat: {
          low: "#ffeda0",
          moderate: "#feb24c",
          high: "#f03b20",
          critical: "#800026",
        },
      },
    },
  },
  plugins: [],
};
