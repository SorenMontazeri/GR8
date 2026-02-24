import { useState } from 'react'
import './App.css'
import SearchButton from './components/Searchbutton'
import TextSearch from './components/TextSearch.jsx'

function App() {
  // Vi håller namnet här så att båda komponenterna kan prata med det
  const [name, setName] = useState("");

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen">
      <h1 className="text-3xl font-bold text-gray-800">GR8</h1>

      {/* Update the state as the user types. */}
      <TextSearch name={name} setName={setName} />

      {/* Send name to database */}
      <SearchButton id={name} />

    </div>
   )
}

export default App