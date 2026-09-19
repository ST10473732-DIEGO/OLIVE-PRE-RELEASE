import { createRoot } from "react-dom/client";
import App from "./app/App";
import "./design/tokens.css";
import "./design/app.css";
import "./design/workspaces.css";
document.addEventListener("visibilitychange", () => {
  document.documentElement.dataset.hidden = String(document.hidden);
});
createRoot(document.getElementById("root")!).render(<App />);
