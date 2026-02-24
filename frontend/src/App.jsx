import { useState } from "react";
import "./App.css";
import SearchButton from "./components/Searchbutton";
import TextSearch from "./components/TextSearch.jsx";
import Image from "./components/Image.jsx";

function App() {
  const [name, setName] = useState("");          // what user types
  const [submittedName, setSubmittedName] = useState(null); // what backend sees

  function handleSearch() {
    setSubmittedName(name.trim());
  }

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen gap-4">
      <h1 className="text-3xl font-bold text-gray-800">GR8</h1>

      <TextSearch name={name} setName={setName} />

      <SearchButton id={name} onClick={handleSearch} />

      {/* This is the connection */}
      <Image name={submittedName} />
    </div>
  );
}

export default App;