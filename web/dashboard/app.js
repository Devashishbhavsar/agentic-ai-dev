// web/dashboard/app.js — Enterprise Light v2 complete
import React, { useState } from "react";
import { createRoot }    from "react-dom/client";
import { StatusBar }  from "./components/StatusBar.js";
import { TabNav }     from "./components/TabNav.js";
import { Overview }   from "./components/Overview.js";
import { Agents }     from "./components/Agents.js";
import { OrgChart }   from "./components/OrgChart.js";
import { Workflows }  from "./components/Workflows.js";
import { History }    from "./components/History.js";
import { System }     from "./components/System.js";
import { Settings }   from "./components/Settings.js";
import { Analytics }  from "./components/Analytics.js";
import { useDashboard } from "./hooks/useDashboard.js";

function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const { data, streamState } = useDashboard();
  const agents = data?.active_agents || [];

  const tab = () => {
    switch (activeTab) {
      case "overview":  return React.createElement(Overview,  { data, streamState });
      case "agents":    return React.createElement(Agents,    { activeAgents: agents });
      case "orgchart":  return React.createElement(OrgChart,  { data, activeAgents: agents });
      case "workflows": return React.createElement(Workflows, { data });
      case "history":   return React.createElement(History,   { data });
      case "analytics": return React.createElement(Analytics, {});
      case "system":    return React.createElement(System,    {});
      case "settings":  return React.createElement(Settings,  {});
      default:          return null;
    }
  };

  return React.createElement(React.Fragment, null,
    React.createElement(StatusBar, {}),
    React.createElement(TabNav, { activeTab, onTabChange: setActiveTab }),
    tab(),
  );
}

createRoot(document.getElementById("root")).render(React.createElement(App));
