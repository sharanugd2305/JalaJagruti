import React from "react";
import { createRoot } from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "./styles.css";
import App from "./App.jsx";
import { ThemeProvider } from "./ThemeContext.jsx";

createRoot(document.getElementById("root")).render(<ThemeProvider><App /></ThemeProvider>);
