import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

async function start() {
  if (import.meta.env.MODE === "demo") {
    // демо-режим: данные-примеры прямо в браузере (только для предпросмотра, в продакшене не используется)
    const { installMock } = await import("./services/mock");
    installMock();
  }
  createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
}
start();
