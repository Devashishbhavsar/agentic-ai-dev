// web/dashboard/app.js — Enterprise Light v2 shell
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { StatusBar } from "./components/StatusBar.js";
import { TabNav }    from "./components/TabNav.js";
import { Overview }    from "./components/Overview.js";
import { useDashboard } from "./hooks/useDashboard.js";

const h = React.createElement;

function Placeholder({ name }) {
  return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__icon" }, "🔧"),
      h("div", { className: "empty-state__title" }, `${name} tab`),
      h("div", { className: "empty-state__body" }, "Coming soon"),
    )
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const { data } = useDashboard();

  function renderTab() {
    if (activeTab === "overview") return React.createElement(Overview, { data });
    return h(Placeholder, { name: activeTab });
  }

  return h(React.Fragment, null,
    h(StatusBar, {}),
    h(TabNav, { activeTab, onTabChange: setActiveTab }),
    renderTab(),
  );
}

createRoot(document.getElementById("root")).render(React.createElement(App, {}));
