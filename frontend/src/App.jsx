
import { useState } from "react";
import Home from "./Home.jsx";
import Analys from "./Analys.jsx";

function App() {
  const [currentPage, setCurrentPage] = useState("home");

  return (
    <div className="App">
      {currentPage === "home" ? (
        <Home onAnalysClick={() => setCurrentPage("analys")} />
      ) : (
        <Analys goHome={() => setCurrentPage("home")} />
      )}
    </div>
  );
}

export default App;
