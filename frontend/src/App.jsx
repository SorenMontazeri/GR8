import { useEffect, useRef, useState } from "react";
//import "./App.css";
import SearchButton from "./components/Searchbutton";
import TextSearch from "./components/TextSearch.jsx";
import Image from "./components/Image.jsx";

const API_BASE_URL = "http://127.0.0.1:8000";

/*
  Main application component which handles user input and displays results
*/
function App() {
  const [searchString, setString] = useState("");          // what user types
  const [submittedString, setSubmittedString] = useState(null); // stores the submitted string 
  const didRunStartupFetch = useRef(false);

  useEffect(() => {
    if (didRunStartupFetch.current) return;
    didRunStartupFetch.current = true;

    let cancelled = false;

    async function fetchStartupEvent(attempt = 1) {
      try {
        const debugQuery = "person";
        const res = await fetch(`${API_BASE_URL}/api/event/${encodeURIComponent(debugQuery)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        console.log("startup /api/event response:", data);
      } catch (error) {
        if (attempt < 10 && !cancelled) {
          setTimeout(() => {
            fetchStartupEvent(attempt + 1);
          }, 1000);
          return;
        }
        console.error("startup /api/event failed:", error);
      }
    }

    fetchStartupEvent();
    return () => {
      cancelled = true;
    };
  }, []);

  /* Called when the user clicks the search button and calls 
  images.jsx to show an image at the UI 
   */
  function handleSearch() {
    setSubmittedString(searchString.trim());
  }

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen gap-4">
      <h1 className="text-3xl font-bold text-gray-800">GR8</h1>

      <TextSearch searchString={searchString} setString={setString} />

      <SearchButton id={searchString} onClick={handleSearch} />

      {/* This is the connection */}
      <Image searchString={submittedString} />
    </div>
  );
}

export default App;
