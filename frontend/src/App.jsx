

import { useState } from "react";
import Home from "./Home.jsx";
import Analys from "./Analys.jsx";

function App() {
  const [currentPage, setCurrentPage] = useState("home");

  // Detta state sparar allt så att det inte försvinner när du byter sida
  const [persistedData, setPersistedData] = useState({
    searchString: "",      // Det man skriver i fältet
    submittedString: null, // Det man faktiskt har sökt på
    eventData: null,       // Svaret från API:et (bilderna)
    ratings: {             // Alla betyg/stjärnor
      full_frame: 0,
      snapshot: 0,
      uniform: 0,
      varied: 0,
    }
  });

  return (
    <div className="App">
      {currentPage === "home" ? (
        <Home 
          data={persistedData} 
          setData={setPersistedData} 
          onAnalysClick={() => setCurrentPage("analys")} 
        />
      ) : (
        <Analys goHome={() => setCurrentPage("home")} />
      )}
    </div>
  );
}

export default App;
